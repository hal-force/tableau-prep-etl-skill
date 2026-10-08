"""
Tableau Server / Cloud publish + schedule wiring for the tableau-prep-etl
skill. Built on tableauserverclient (TSC) plus direct REST for the
Cloud-only endpoints TSC 0.38 doesn't wrap.

Public surface:
    config_from_env()               — load auth + URL/site from env vars
    sign_in()                       — authenticate via PAT
    find_project()                  — locate a project by exact name or id
    publish_flow()                  — upload .tfl into a project
    set_flow_description()          — REST PUT; TSC's flows.update() drops it
    list_scheduled_tasks()          — flow + extract tasks with parsed
                                      next-run times and fire hours
                                      (works on both Server and Cloud)
    score_load_by_hour()            — returns dict[hour:int -> count:int]
                                      across the next 7 days, summing flow
                                      and extract tasks. The signal we use
                                      to balance load.
    pick_balanced_hour()            — given a preferred fire hour and a
                                      tolerance window, return the
                                      lowest-load hour in [hour-tol, hour+tol]
    create_or_assign_schedule()     — top-level: dispatches to Server's
                                      shared-schedule path or Cloud's
                                      per-task path. Always returns a
                                      task id you can monitor.

Cloud vs. Server: Cloud has no shared schedules — each scheduled task
carries its own frequency. We branch on `_is_cloud(server)`. All Tableau
Cloud pods live under `*.online.tableau.com`.

Auth secret handling: the PAT secret is read once from env, passed to
TSC's auth helper, and never persisted. We only persist URL/site.

Reference:
  https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api.htm
  https://help.tableau.com/current/server/en-us/sched_add_flow.htm
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional

import tableauserverclient as TSC

_TS_NS = {"t": "http://tableau.com/api"}


@dataclass
class ServerConfig:
    """Connection params resolved from env vars at runtime."""
    url: str
    pat_name: str
    pat_secret: str
    site: str = ""  # site contentUrl; "" = default site on Server
    api_version: str = ""


@dataclass
class ScheduleSpec:
    """How the user wants this flow scheduled.

    cadence: "hourly" | "daily" | "weekly" | "monthly"
    hour:    0-23 in the SITE's local timezone — Tableau Cloud
        interprets <frequencyDetails start="HH:MM:SS"> as site-local
        even though the GET response surfaces nextRunAt as UTC. On
        Server, this is server-local time. Caller is responsible for
        translating UTC intent → site local if they care about an
        exact UTC fire hour.
    minute:  0/15/30/45 — Tableau snaps to 15-min granularity
    weekday: only for "weekly". Lowercase day name.
    day_of_month: only for "monthly". 1-31.
    name_hint: preferred schedule display name (Server) or task name hint.
    balance_tolerance_hours: shift the requested hour by up to this many
        hours either direction to land in a lower-load slot. 0 disables
        balancing. Default 2 — small enough to stay near the user's
        intent, big enough to dodge a spike.
    """
    cadence: str = "daily"
    hour: int = 6
    minute: int = 0
    weekday: str = "monday"
    day_of_month: int = 1
    name_hint: Optional[str] = None
    balance_tolerance_hours: int = 2


@dataclass
class ScheduledTask:
    """Normalized view of a flow or extract task across REST shapes."""
    kind: str             # "flow" | "extract"
    task_id: str
    next_run_utc: Optional[datetime]
    frequency: str        # "Hourly" | "Daily" | "Weekly" | "Monthly"
    schedule_id: Optional[str] = None
    schedule_name: Optional[str] = None


@dataclass
class PublishResult:
    """Returned by create_or_assign_schedule for the verification log."""
    flow_id: str
    flow_name: str
    project_id: str
    project_name: str
    schedule_id: Optional[str]
    schedule_name: Optional[str]
    task_id: Optional[str]
    fire_hour: int      # site-local hour as submitted (Cloud) / server-local (Server)
    fire_minute: int
    cadence: str
    web_url: str
    is_cloud: bool
    next_run_utc: Optional[str] = None   # ISO string from server, post-create


def config_from_env(env: Optional[dict] = None) -> ServerConfig:
    """Build a ServerConfig from env vars. Raises if any required value
    is missing — fail loudly rather than half-configure."""
    env = env or os.environ
    url = (env.get("TABLEAU_SERVER_URL", "") or "").strip().rstrip("/")
    name = (env.get("TABLEAU_SERVER_PAT_NAME", "") or "").strip()
    secret = (env.get("TABLEAU_SERVER_PAT_SECRET", "") or "").strip()
    site = (env.get("TABLEAU_SERVER_SITE", "") or "").strip()
    api = (env.get("TABLEAU_SERVER_API_VERSION", "") or "").strip()
    missing = [k for k, v in [
        ("TABLEAU_SERVER_URL", url),
        ("TABLEAU_SERVER_PAT_NAME", name),
        ("TABLEAU_SERVER_PAT_SECRET", secret),
    ] if not v]
    if missing:
        raise RuntimeError(
            f"Missing required env vars for Tableau publish: {', '.join(missing)}. "
            "Export them or load from .env before running."
        )
    return ServerConfig(url=url, pat_name=name, pat_secret=secret, site=site, api_version=api)


def _is_cloud(server: TSC.Server) -> bool:
    """TSC 0.38 has no is_tableau_cloud(); detect via URL pattern.
    Tableau Cloud pods all live under *.online.tableau.com."""
    return ".online.tableau.com" in (server.server_address or "").lower()


def sign_in(config: ServerConfig) -> TSC.Server:
    """Authenticate with PAT. Returns a live `Server`. Caller should
    `server.auth.sign_out()` when done (use a try/finally)."""
    auth = TSC.PersonalAccessTokenAuth(
        config.pat_name, config.pat_secret, site_id=config.site,
    )
    server = TSC.Server(config.url, use_server_version=True)
    if config.api_version:
        server.version = config.api_version
    server.auth.sign_in(auth)
    return server


def find_project(
    server: TSC.Server,
    name_or_id: str,
    parent_name_or_id: str = "",
) -> TSC.ProjectItem:
    """Locate a project by exact name or by id. Raises if ambiguous or
    missing. Names aren't unique site-wide (different parents can share
    names), so prefer ids when in doubt.

    When `parent_name_or_id` is set, the lookup is scoped to children
    of that parent — disambiguating same-named child projects under
    different parents (the common case in nested layouts like
    `Prep Agent / 01 - Federal Outlays`)."""
    if not name_or_id:
        raise RuntimeError("project name or id is required")
    all_projects = list(TSC.Pager(server.projects))
    parent_id_filter = ""
    if parent_name_or_id:
        parents = [p for p in all_projects
                   if p.id == parent_name_or_id or p.name == parent_name_or_id]
        if not parents:
            raise RuntimeError(
                f"Parent project {parent_name_or_id!r} not found on this site."
            )
        if len(parents) > 1:
            raise RuntimeError(
                f"Multiple projects named {parent_name_or_id!r}; "
                f"pass the parent project id instead."
            )
        parent_id_filter = parents[0].id
    pool = [p for p in all_projects
            if not parent_id_filter or p.parent_id == parent_id_filter]
    by_id = [p for p in pool if p.id == name_or_id]
    if by_id:
        return by_id[0]
    by_name = [p for p in pool if p.name == name_or_id]
    if not by_name:
        scope = f" under parent {parent_name_or_id!r}" if parent_name_or_id else ""
        raise RuntimeError(
            f"Project {name_or_id!r} not found on this site{scope}."
        )
    if len(by_name) > 1:
        raise RuntimeError(
            f"Multiple projects named {name_or_id!r}; pass the project id instead."
        )
    return by_name[0]


def list_projects(server: TSC.Server) -> list[TSC.ProjectItem]:
    """Return all projects on the connected site. Used by the publish
    picker UX to surface candidates the user can choose from before any
    upload is attempted.

    Paginate with TSC.Pager: `server.projects.get()` returns only the
    first page (default 100), which silently drops freshly-created
    projects on busy sites.
    """
    return list(TSC.Pager(server.projects))


def create_project(
    server: TSC.Server,
    name: str,
    description: str = "",
    parent_id: str = "",
) -> TSC.ProjectItem:
    """Create a project. Top-level by default; pass `parent_id` to
    create as a child of an existing project (nested-project layout).
    Used by the publish picker when the user opts to land the flow in
    a freshly-named bucket."""
    if not name:
        raise RuntimeError("project name is required")
    item = TSC.ProjectItem(
        name=name,
        description=description or None,
        parent_id=parent_id or None,
    )
    return server.projects.create(item)


def publish_flow(
    server: TSC.Server,
    flow_path: str,
    project_id: str,
    flow_name: Optional[str] = None,
    overwrite: bool = True,
    description: str = "",
) -> TSC.FlowItem:
    """Upload a .tfl into the named project. Overwrite by default so
    re-runs replace the previous version rather than failing. A
    `description` is applied after upload via `set_flow_description`."""
    new_flow = TSC.FlowItem(project_id=project_id, name=flow_name)
    mode = TSC.Server.PublishMode.Overwrite if overwrite else TSC.Server.PublishMode.CreateNew
    flow = server.flows.publish(new_flow, flow_path, mode)
    if description:
        set_flow_description(server, flow.id, description)
        flow.description = description
    return flow


def set_flow_description(server: TSC.Server, flow_id: str, description: str) -> None:
    """Set a flow's description. TSC 0.38's `flows.update()` serializes
    only name / project / owner, so `flow.description = ...; update()`
    returns 200 and silently changes nothing. PUT the REST body
    directly instead."""
    from xml.sax.saxutils import quoteattr
    _rest_put(server, f"flows/{flow_id}",
              f"<tsRequest><flow description={quoteattr(description)}/></tsRequest>")


def publish_hyper_as_datasource(
    server: TSC.Server,
    hyper_path: str,
    project_id: str,
    datasource_name: str,
    description: str = "",
    overwrite: bool = True,
) -> TSC.DatasourceItem:
    """Upload a local .hyper file as a published data source. The
    Cloud-friendly path for flows whose backgrounder run can't execute
    (e.g. script-bearing flows on Tableau Cloud): run the flow locally
    via prep-cli, then publish the resulting Hyper extract directly via
    TSC. Overwrite preserves the LUID on re-runs so existing dashboards
    stay wired up."""
    item = TSC.DatasourceItem(project_id=project_id, name=datasource_name)
    if description:
        item.description = description
    mode = TSC.Server.PublishMode.Overwrite if overwrite else TSC.Server.PublishMode.CreateNew
    return server.datasources.publish(item, hyper_path, mode)


def _rest_get(server: TSC.Server, path: str) -> ET.Element:
    """GET /api/{ver}/sites/{site}/{path} and parse XML."""
    url = f"{server.server_address}/api/{server.version}/sites/{server.site_id}/{path}"
    r = server._session.get(
        url, headers={"X-Tableau-Auth": server.auth_token, "Accept": "application/xml"},
    )
    r.raise_for_status()
    return ET.fromstring(r.text)


def _rest_post(server: TSC.Server, path: str, body: str) -> ET.Element:
    return _rest_send(server, "POST", path, body)


def _rest_put(server: TSC.Server, path: str, body: str) -> ET.Element:
    return _rest_send(server, "PUT", path, body)


def _rest_send(server: TSC.Server, method: str, path: str, body: str) -> ET.Element:
    url = f"{server.server_address}/api/{server.version}/sites/{server.site_id}/{path}"
    r = server._session.request(
        method, url, data=body,
        headers={"X-Tableau-Auth": server.auth_token,
                 "Content-Type": "application/xml",
                 "Accept": "application/xml"},
    )
    if not r.ok:
        # Surface server's error body so callers see Tableau's "summary"
        # and "detail" instead of just a status code.
        raise RuntimeError(f"Tableau {method} {path} → {r.status_code}: {r.text[:1500]}")
    return ET.fromstring(r.text) if r.text.strip() else ET.Element("empty")


def list_scheduled_tasks(server: TSC.Server) -> list[ScheduledTask]:
    """Pull flow + extract tasks via REST. Works on Cloud and Server.

    On Cloud, both endpoints expose `<schedule frequency=... nextRunAt=...>`
    inline. On Server, schedules are shared and tasks reference them by id.
    We normalize both into `ScheduledTask`."""
    out: list[ScheduledTask] = []

    # Flow tasks
    try:
        root = _rest_get(server, "tasks/runFlow")
        for task in root.findall(".//t:task", _TS_NS):
            fr = task.find(".//t:flowRun", _TS_NS)
            if fr is None:
                continue
            sched = fr.find("t:schedule", _TS_NS)
            out.append(ScheduledTask(
                kind="flow",
                task_id=fr.get("id", ""),
                next_run_utc=_parse_next_run(sched),
                frequency=(sched.get("frequency", "") if sched is not None else ""),
                schedule_id=(sched.get("id") if sched is not None else None),
                schedule_name=(sched.get("name") if sched is not None else None),
            ))
    except Exception:
        pass

    # Extract refresh tasks
    try:
        root = _rest_get(server, "tasks/extractRefreshes")
        for task in root.findall(".//t:task", _TS_NS):
            ext = task.find(".//t:extractRefresh", _TS_NS)
            if ext is None:
                continue
            sched = ext.find("t:schedule", _TS_NS)
            out.append(ScheduledTask(
                kind="extract",
                task_id=ext.get("id", ""),
                next_run_utc=_parse_next_run(sched),
                frequency=(sched.get("frequency", "") if sched is not None else ""),
                schedule_id=(sched.get("id") if sched is not None else None),
                schedule_name=(sched.get("name") if sched is not None else None),
            ))
    except Exception:
        pass

    return out


def _parse_next_run(sched_elem: Optional[ET.Element]) -> Optional[datetime]:
    if sched_elem is None:
        return None
    s = sched_elem.get("nextRunAt") or ""
    if not s:
        return None
    try:
        # ISO 8601 with 'Z'. Python <3.11 doesn't accept Z directly.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def score_load_by_hour(tasks: list[ScheduledTask]) -> dict[int, int]:
    """Bucket scheduled tasks by their next-run UTC hour.

    Returns a dict {hour: count} for hours 0..23. Tasks without a
    parseable nextRunAt are skipped (they don't contribute to load
    pressure on any specific hour). Both flow and extract tasks count
    equally — they share the same backgrounder pool."""
    counts = {h: 0 for h in range(24)}
    for t in tasks:
        if t.next_run_utc is None:
            continue
        counts[t.next_run_utc.hour] += 1
    return counts


def pick_balanced_hour(
    preferred_hour: int,
    load: dict[int, int],
    tolerance_hours: int = 2,
) -> tuple[int, int]:
    """Pick the lowest-load hour in [pref-tol, pref+tol], wrapping the
    24h clock. Returns (chosen_hour, load_at_chosen_hour). Ties broken
    in favor of hours closer to the preferred one."""
    if tolerance_hours <= 0:
        return preferred_hour, load.get(preferred_hour, 0)
    candidates: list[tuple[int, int, int]] = []
    for off in range(-tolerance_hours, tolerance_hours + 1):
        h = (preferred_hour + off) % 24
        candidates.append((load.get(h, 0), abs(off), h))
    candidates.sort()
    chosen = candidates[0]
    return chosen[2], chosen[0]


def create_or_assign_schedule(
    server: TSC.Server,
    flow: TSC.FlowItem,
    project_name: str,
    want: ScheduleSpec,
) -> PublishResult:
    """Top-level: schedule the flow per `want`, with load balancing.

    On Cloud: creates a per-task schedule via REST.
    On Server: prefers an existing shared schedule that matches the
    cadence; falls back to creating one if the user has admin rights.
    """
    is_cloud = _is_cloud(server)
    tasks = list_scheduled_tasks(server)
    load = score_load_by_hour(tasks)
    chosen_hour, _ = pick_balanced_hour(
        want.hour, load, want.balance_tolerance_hours,
    )
    balanced = ScheduleSpec(
        cadence=want.cadence, hour=chosen_hour, minute=want.minute,
        weekday=want.weekday, day_of_month=want.day_of_month,
        name_hint=want.name_hint,
        balance_tolerance_hours=0,
    )

    web_url = f"{server.server_address}/#/site/{server.site_id}/flows/{flow.id}"

    if is_cloud:
        task_id, next_run_utc, schedule_id = _create_cloud_task(
            server, flow.id, balanced,
        )
        return PublishResult(
            flow_id=flow.id, flow_name=flow.name,
            project_id=flow.project_id, project_name=project_name,
            schedule_id=schedule_id,
            schedule_name=balanced.name_hint or _default_schedule_name(balanced),
            task_id=task_id,
            fire_hour=balanced.hour, fire_minute=balanced.minute,
            cadence=balanced.cadence,
            web_url=web_url, is_cloud=True,
            next_run_utc=next_run_utc,
        )

    # Server path: prefer-existing then create-new.
    schedule = _server_pick_or_create(server, balanced)
    task_id = _server_assign(server, flow.id, schedule.id)
    return PublishResult(
        flow_id=flow.id, flow_name=flow.name,
        project_id=flow.project_id, project_name=project_name,
        schedule_id=schedule.id, schedule_name=schedule.name,
        task_id=task_id,
        fire_hour=balanced.hour, fire_minute=balanced.minute,
        cadence=balanced.cadence,
        web_url=web_url, is_cloud=False,
    )


def _server_pick_or_create(server: TSC.Server, want: ScheduleSpec) -> TSC.ScheduleItem:
    """Prefer an existing schedule that matches the cadence and falls
    in the chosen hour; create a new one if missing or admin-equivalent."""
    schedules = []
    try:
        items, _ = server.schedules.get()
        schedules = list(items)
    except Exception:
        pass
    matching = [s for s in schedules if _server_schedule_matches(s, want)]
    if matching:
        # Among matching schedules, prefer the one already serving the
        # fewest tasks. We approximate by preferring the lowest-name
        # ordering when task counts are unknown — Tableau doesn't expose
        # task counts on the schedule item directly.
        matching.sort(key=lambda s: (s.name or "").lower())
        return matching[0]
    return _server_create_schedule(server, want)


def _server_schedule_matches(s: TSC.ScheduleItem, want: ScheduleSpec) -> bool:
    freq = (getattr(s, "schedule_type", "") or "").lower()
    if want.cadence.lower() not in freq and freq not in want.cadence.lower():
        return False
    item = getattr(s, "interval_item", None)
    start = getattr(item, "start_time", None) if item else None
    return bool(start and start.hour == want.hour)


def _server_create_schedule(server: TSC.Server, want: ScheduleSpec) -> TSC.ScheduleItem:
    name = want.name_hint or _default_schedule_name(want)
    interval = _build_interval_item(want)
    new_schedule = TSC.ScheduleItem(
        name=name,
        priority=50,
        schedule_type=TSC.ScheduleItem.Type.Flow,
        execution_order=TSC.ScheduleItem.ExecutionOrder.Parallel,
        interval_item=interval,
    )
    return server.schedules.create(new_schedule)


def _server_assign(server: TSC.Server, flow_id: str, schedule_id: str) -> str:
    res = server.schedules.add_to_schedule(schedule_id, flow_id=flow_id)
    # add_to_schedule returns a list of items; pick the first id we can
    if isinstance(res, list) and res:
        for r in res:
            tid = getattr(r, "id", None) or getattr(getattr(r, "task", None), "id", None)
            if tid:
                return tid
    return ""


def _default_schedule_name(want: ScheduleSpec) -> str:
    h = f"{want.hour:02d}:{want.minute:02d}"
    return {
        "hourly": f"Skill — Hourly @ :{want.minute:02d}",
        "daily": f"Skill — Daily @ {h} UTC",
        "weekly": f"Skill — Weekly {want.weekday.title()} @ {h} UTC",
        "monthly": f"Skill — Monthly day {want.day_of_month} @ {h} UTC",
    }.get(want.cadence.lower(), f"Skill — {want.cadence} @ {h}")


def _build_interval_item(want: ScheduleSpec):
    """Translate ScheduleSpec to a TSC IntervalItem. TSC's interval
    classes are positional and (for Daily/Weekly) require explicit
    weekday strings — Cloud rejects a Daily schedule that doesn't
    enumerate all seven weekDays in <intervals>.
    """
    cadence = want.cadence.lower()
    start = dtime(want.hour, want.minute)
    all_days = ("Sunday", "Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday")
    if cadence == "hourly":
        # 1-hour interval, fire all 7 days.
        return TSC.HourlyInterval(start, start, 1, *all_days)
    if cadence == "daily":
        # Cloud requires the 7 weekday children; pass them as positional
        # interval_values so TSC emits them in the body.
        return TSC.DailyInterval(start, *all_days)
    if cadence == "weekly":
        day_const = getattr(TSC.IntervalItem.Day, want.weekday.title())
        return TSC.WeeklyInterval(start, day_const)
    if cadence == "monthly":
        return TSC.MonthlyInterval(start, want.day_of_month)
    raise ValueError(
        f"Unknown server_publish.cadence {cadence!r}. Tableau REST/TSC "
        f"only accept 'hourly' | 'daily' | 'weekly' | 'monthly'. Sub-daily "
        f"aliases (every_3_hours, every_6_hours) belong on top-level "
        f"`refresh_cadence` — set `server_publish.cadence: hourly` as the "
        f"scheduler match. See skill/reference/server_publishing.md."
    )


def _create_cloud_task(
    server: TSC.Server, flow_id: str, want: ScheduleSpec,
) -> tuple[str, Optional[str], Optional[str]]:
    """Cloud only. Create a scheduled runFlow task via REST.
    POST /api/{ver}/sites/{site}/tasks/flows  (API 3.22+)

    Body shape per Tableau REST docs:
        <tsRequest>
          <task><flowRun><flow id="..."/></flowRun></task>
          <schedule frequency="Daily">
            <frequencyDetails start="06:00:00">
              <intervals><interval hours="24"/></intervals>
            </frequencyDetails>
          </schedule>
        </tsRequest>

    Daily intervals must use `hours` (one of 2/4/6/8/12/24), NOT a list
    of weekDays — that's where TSC 0.38's RequestFactory.FlowTask emits
    a body Cloud rejects with 400.
    """
    body = _build_cloud_task_body(flow_id, want)
    root = _rest_post(server, "tasks/flows", body)
    fr = root.find(".//t:flowRun", _TS_NS)
    sched = root.find(".//t:schedule", _TS_NS)
    next_run = sched.get("nextRunAt") if sched is not None else None
    sched_id = sched.get("id") if sched is not None else None
    if fr is not None and fr.get("id"):
        return fr.get("id", ""), next_run, sched_id
    task_el = root.find(".//t:task", _TS_NS)
    if task_el is not None and task_el.get("id"):
        return task_el.get("id", ""), next_run, sched_id
    return "", next_run, sched_id


def _build_cloud_task_body(flow_id: str, want: ScheduleSpec) -> str:
    return (
        '<tsRequest>'
          '<task>'
            '<flowRun>'
              f'<flow id="{flow_id}"/>'
            '</flowRun>'
          '</task>'
          f'<schedule frequency="{_cloud_frequency(want)}">'
            f'<frequencyDetails start="{_hhmm_str(want)}"'
            f'{_cloud_end_attr(want)}>'
              f'{_cloud_intervals_xml(want)}'
            '</frequencyDetails>'
          '</schedule>'
        '</tsRequest>'
    )


def _cloud_end_attr(want: ScheduleSpec) -> str:
    """Cloud requires `end` whenever `<intervals>` carries an `hours`
    attribute — including Daily with `hours="24"` (despite docs reading
    otherwise). The end must be `start + hours` mod 24h. For hours=24
    this collapses back to `start`, which Cloud accepts.
    """
    cadence = want.cadence.lower()
    if cadence == "hourly":
        end_h = (want.hour + 1) % 24
        return f' end="{end_h:02d}:{want.minute:02d}:00"'
    if cadence == "daily":
        # hours=24 → end == start (full-day window).
        return f' end="{want.hour:02d}:{want.minute:02d}:00"'
    return ""


def _cloud_frequency(want: ScheduleSpec) -> str:
    return {"hourly": "Hourly", "daily": "Daily",
            "weekly": "Weekly", "monthly": "Monthly"}[want.cadence.lower()]


def _hhmm_str(want: ScheduleSpec) -> str:
    return f"{want.hour:02d}:{want.minute:02d}:00"


def _cloud_intervals_xml(want: ScheduleSpec) -> str:
    """Cloud's <intervals> child XML varies by cadence (per REST docs +
    empirical 0x5CE10192 errors observed in production):
      hourly  → <interval hours="1"/> + all 7 weekDay siblings
      daily   → <interval hours="24"/> + all 7 weekDay siblings
                (Cloud rejects daily without weekDay coverage even when
                 hours=24; rejects without hours when end is set)
      weekly  → single <interval weekDay="..."/>
      monthly → single <interval monthDay="N"/>  (1–31 or "LastDay")
    """
    cadence = want.cadence.lower()
    all_days = ("Sunday", "Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday")
    weekday_xml = "".join(f'<interval weekDay="{d}"/>' for d in all_days)
    if cadence == "hourly":
        return f'<intervals><interval hours="1"/>{weekday_xml}</intervals>'
    if cadence == "daily":
        return f'<intervals><interval hours="24"/>{weekday_xml}</intervals>'
    if cadence == "weekly":
        return f'<intervals><interval weekDay="{want.weekday.title()}"/></intervals>'
    if cadence == "monthly":
        return f'<intervals><interval monthDay="{want.day_of_month}"/></intervals>'
    raise ValueError(
        f"Unknown server_publish.cadence {cadence!r}. Tableau REST/TSC "
        f"only accept 'hourly' | 'daily' | 'weekly' | 'monthly'. Sub-daily "
        f"aliases (every_3_hours, every_6_hours) belong on top-level "
        f"`refresh_cadence` — set `server_publish.cadence: hourly` as the "
        f"scheduler match. See skill/reference/server_publishing.md."
    )
