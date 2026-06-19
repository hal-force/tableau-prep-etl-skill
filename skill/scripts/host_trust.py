"""
Host trust: first-time-host approval for external data pulls.

Modeled on Claude Code's per-domain trust mechanism. The skill records
every external host it has reached in `~/.tableau-prep-etl/known_hosts.json`.
On the first sighting of a new host, an LLM-backed pre-flight evaluation
scores the host (typosquat-likelihood, unusual TLD, plausibility as a
public-data source) and surfaces the verdict to the operator. Approval
is one-shot — subsequent runs skip the prompt for that host.

Modes (TPE_HOST_APPROVAL env var):
  - "interactive" (default on a TTY): prompt for unknown hosts.
  - "auto-trust-known": no prompt; trust only previously-approved hosts.
                       Unknown hosts cause a hard failure.
  - "deny-unknown": same as auto-trust-known (CI-strict alias).
  - "trust-all": skip the trust gate entirely. ONLY for local dev / tests.

Internal-trust (suffix match against `TABLEAU_SERVER_URL` host or
`internal_hosts.txt` lines) bypasses the prompt — see spec_validation.

Public surface:
    extract_hosts(spec_dict) -> list[str]
    ensure_hosts_approved(hosts, *, asker=None, evaluator=None) -> list[ApprovalDecision]
    record_approval(host, *, source, verdict)
    is_host_known(host) -> bool

The `asker` callback (defaults to print + input on TTY, falls back to
auto-deny otherwise) and `evaluator` callback (defaults to a minimal
heuristic — the LLM call is wired in by callers that already have a
gateway client) are injectable so tests can run hermetically.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse

from skill.scripts.spec_validation import _host_matches_internal_trust


CONFIG_DIR = Path(os.environ.get(
    "TABLEAU_PREP_ETL_CONFIG_DIR",
    str(Path.home() / ".tableau-prep-etl"),
))
KNOWN_HOSTS_FILE = CONFIG_DIR / "known_hosts.json"


# === Data shapes ====================================================

@dataclass
class HostEvaluation:
    """LLM (or heuristic) verdict surfaced to the operator."""
    host: str
    risk_score: int                      # 0 (low risk) - 100 (high risk)
    verdict: str                         # "looks-legitimate", "suspicious", "unknown"
    reasons: list[str] = field(default_factory=list)
    typosquat_of: Optional[str] = None   # e.g. "data.gov" if host=="data-gov.com"


@dataclass
class ApprovalDecision:
    host: str
    approved: bool
    source: str                          # "internal-trust" | "known" | "user-approved"
                                         # | "denied" | "auto-mode-skipped"
    evaluation: Optional[HostEvaluation] = None


# === Persistence =====================================================

def _load_known() -> dict:
    if not KNOWN_HOSTS_FILE.exists():
        return {"hosts": {}}
    try:
        d = json.loads(KNOWN_HOSTS_FILE.read_text())
    except Exception:
        return {"hosts": {}}
    if not isinstance(d, dict) or "hosts" not in d:
        return {"hosts": {}}
    return d


def _save_known(d: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    KNOWN_HOSTS_FILE.write_text(json.dumps(d, indent=2, sort_keys=True))


def is_host_known(host: str) -> bool:
    if not host:
        return False
    return host.lower().strip() in _load_known().get("hosts", {})


def record_approval(host: str, *, source: str, verdict: Optional[HostEvaluation] = None) -> None:
    """Persist a host as approved. `source` is a tag — 'user-approved',
    'imported', 'internal-trust' — kept for audit."""
    h = host.lower().strip()
    d = _load_known()
    d.setdefault("hosts", {})[h] = {
        "source": source,
        "verdict": asdict(verdict) if verdict else None,
    }
    _save_known(d)


# === Spec → host extraction =========================================

def extract_hosts(spec_dict: dict) -> list[str]:
    """Pull every external host out of spec.sources[*].url.

    Returns a deduplicated, lowercased list. Sources with no URL
    (local_folder, internal_published_ds, etc.) contribute nothing."""
    seen: set[str] = set()
    out: list[str] = []
    for s in (spec_dict.get("sources") or []):
        url = (s.get("url") or "").strip() if isinstance(s, dict) else ""
        if not url:
            continue
        try:
            host = (urlparse(url).hostname or "").strip().lower()
        except Exception:
            continue
        if host and host not in seen:
            seen.add(host)
            out.append(host)
    return out


# === Heuristic evaluator (fallback when no LLM is wired) ============

# Public-data hosts the skill already trusts as legitimate. Used as
# anchors for typosquat detection — anything edit-distance-1 from one
# of these gets a high suspicion score.
_KNOWN_LEGITIMATE_ANCHORS = (
    "data.gov", "data.ca.gov", "api.data.gov",
    "github.com", "api.github.com",
    "tableau.com", "online.tableau.com",
    "gov.bc.ca", "europa.eu",
    "fda.gov", "cdc.gov", "cms.gov", "epa.gov", "fema.gov",
    "nasa.gov", "noaa.gov", "usaspending.gov",
    "googleapis.com", "google.com",
)

# TLDs that are statistically over-represented in malicious infra.
# Not auto-deny — just bumps the risk score so the operator sees it.
_SUS_TLDS = (".tk", ".top", ".cf", ".ml", ".gq", ".pw", ".click")


def _edit_distance(a: str, b: str) -> int:
    """Tiny Levenshtein. Used only on short hostnames so quadratic is fine."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


def heuristic_evaluate(host: str) -> HostEvaluation:
    """Minimal default evaluator. Caller can swap this for a real LLM
    call by passing `evaluator=...` to `ensure_hosts_approved`.

    Score breakdown:
      +30 if TLD is in the suspicious set
      +40 if host is edit-distance-1 from a known-legitimate anchor
      +10 if no dot at all (bare hostname)
      +20 if hostname contains digits where a legit one wouldn't
    """
    h = (host or "").lower().strip()
    reasons: list[str] = []
    score = 0
    typosquat: Optional[str] = None

    if not h:
        return HostEvaluation(host=h, risk_score=100, verdict="unknown",
                              reasons=["empty host"])

    if "." not in h:
        score += 10
        reasons.append("hostname has no dot (bare label)")

    for sus in _SUS_TLDS:
        if h.endswith(sus):
            score += 30
            reasons.append(f"hostname ends in suspicious TLD {sus!r}")
            break

    # Typosquat check: for each anchor, compare last-two-labels.
    h_tail = ".".join(h.split(".")[-2:]) if h.count(".") >= 1 else h
    for anchor in _KNOWN_LEGITIMATE_ANCHORS:
        a_tail = ".".join(anchor.split(".")[-2:])
        if h_tail == a_tail:
            score = min(score, 5)  # exact match = legit
            reasons.append(f"matches known anchor {anchor!r}")
            break
        d = _edit_distance(h_tail, a_tail)
        if d == 1 and abs(len(h_tail) - len(a_tail)) <= 1:
            score += 40
            typosquat = anchor
            reasons.append(
                f"edit-distance 1 from known legitimate host {anchor!r} — "
                "possible typosquat"
            )
            break

    if re.search(r"[A-Za-z]\d{2,}|\d{2,}[A-Za-z]", h):
        score += 20
        reasons.append("hostname mixes letters and 2+ digits (atypical for public-data hosts)")

    score = max(0, min(100, score))
    if score >= 50:
        verdict = "suspicious"
    elif score >= 20:
        verdict = "unknown"
    else:
        verdict = "looks-legitimate"

    return HostEvaluation(
        host=h, risk_score=score, verdict=verdict,
        reasons=reasons or ["no risk signals matched"],
        typosquat_of=typosquat,
    )


# === Approval flow ===================================================

def _approval_mode() -> str:
    return (os.environ.get("TPE_HOST_APPROVAL") or "").strip().lower()


def _default_asker(host: str, ev: HostEvaluation) -> bool:
    """TTY prompt fallback. Returns True for approve, False for deny.

    Non-interactive environments: deny by default. Callers that have
    a richer UI (e.g. AskUserQuestion in a Claude Code session) can
    pass their own `asker` to override."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        return False
    print("=" * 60, file=sys.stderr)
    print(f"NEW EXTERNAL HOST: {host}", file=sys.stderr)
    print(f"  verdict: {ev.verdict} (risk score {ev.risk_score}/100)", file=sys.stderr)
    if ev.typosquat_of:
        print(f"  WARNING: possible typosquat of {ev.typosquat_of!r}", file=sys.stderr)
    for r in ev.reasons:
        print(f"  - {r}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("Approve this host for external data pulls? [y/N]: ",
          file=sys.stderr, end="")
    try:
        ans = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("y", "yes")


def ensure_hosts_approved(
    hosts: Iterable[str],
    *,
    asker: Optional[Callable[[str, HostEvaluation], bool]] = None,
    evaluator: Optional[Callable[[str], HostEvaluation]] = None,
) -> list[ApprovalDecision]:
    """For each host: skip if internal-trust covers it, skip if known,
    otherwise evaluate + ask. Returns one ApprovalDecision per host.

    Raises RuntimeError if any host is rejected — callers can catch and
    surface a structured "intake aborted" response without continuing
    to render code.
    """
    mode = _approval_mode()
    if mode == "trust-all":
        return [ApprovalDecision(host=h, approved=True, source="trust-all")
                for h in hosts]

    asker = asker or _default_asker
    evaluator = evaluator or heuristic_evaluate

    decisions: list[ApprovalDecision] = []
    rejected: list[str] = []

    seen: set[str] = set()
    for raw in hosts:
        h = (raw or "").strip().lower()
        if not h or h in seen:
            continue
        seen.add(h)

        if _host_matches_internal_trust(h):
            decisions.append(ApprovalDecision(
                host=h, approved=True, source="internal-trust",
            ))
            continue

        if is_host_known(h):
            decisions.append(ApprovalDecision(
                host=h, approved=True, source="known",
            ))
            continue

        ev = evaluator(h)

        if mode in ("auto-trust-known", "deny-unknown"):
            decisions.append(ApprovalDecision(
                host=h, approved=False, source="denied", evaluation=ev,
            ))
            rejected.append(h)
            continue

        approved = bool(asker(h, ev))
        if approved:
            record_approval(h, source="user-approved", verdict=ev)
            decisions.append(ApprovalDecision(
                host=h, approved=True, source="user-approved", evaluation=ev,
            ))
        else:
            decisions.append(ApprovalDecision(
                host=h, approved=False, source="denied", evaluation=ev,
            ))
            rejected.append(h)

    if rejected:
        raise RuntimeError(
            "Host approval denied for: " + ", ".join(rejected) +
            ". Either approve interactively, list the host's suffix in "
            "~/.tableau-prep-etl/internal_hosts.txt, or set "
            "TPE_HOST_APPROVAL=trust-all (local dev only)."
        )

    return decisions
