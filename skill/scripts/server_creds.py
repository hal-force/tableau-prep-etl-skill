"""
Tableau Server credential discovery + platform-aware storage guidance.

Discovery order (most secure -> least):
  1. Environment variables already set in the process. Preferred for
     production / CI / scheduled runs where a secret manager injects
     them at process start.
  2. macOS Keychain (Darwin only) via `security find-generic-password`.
     Lookup is service="tableau-prep-etl", account in
     {url, pat-name, pat-secret, site}. No plaintext on disk.
  3. Linux secret-tool (libsecret) when the binary is present.
     Same service/account scheme.
  4. ~/.tableau-prep-etl/server.json - local dev fallback. chmod 600.
     Never published.

When discovery fails, return a CredsResult describing what's missing
AND a platform-tailored suggestion list the orchestrator surfaces to
the user via AskUserQuestion. The point: never silently fail a
server-bound run, never persist secrets in code paths the user didn't
authorize.

Public surface:
    discover()        -> CredsResult        # auto-load + return status
    is_configured()   -> bool                # cheap env-only check
    suggestions()     -> list[StorageOption] # platform-aware tips
    secrets_in_spec(spec_dict) -> bool       # does this spec need them?

CLI:
    python3 -m skill.scripts.server_creds --check
    python3 -m skill.scripts.server_creds --suggest
    python3 -m skill.scripts.server_creds --load   # tries Keychain etc.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Bootstrap tflb_lib + auto_refine import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401

# Storage-option data (static help text per platform) lives in a sibling
# module so this file can stay focused on discovery / load / save.
from skill.scripts._creds_suggestions import (
    StorageOption,
    suggestions_for as _suggestions_for,
)


REQUIRED = ("TABLEAU_SERVER_URL", "TABLEAU_SERVER_PAT_NAME", "TABLEAU_SERVER_PAT_SECRET")
OPTIONAL = ("TABLEAU_SERVER_SITE",)  # empty string OK for default site on Server

# Tableau Prep CLI v2026.1 only accepts username/password in its
# credentials JSON - PATs are explicitly rejected by the deserializer.
# These are OPTIONAL on the env-var side but REQUIRED to run a flow
# locally via prep-cli when the flow has any internal_published_ds
# source. Same Keychain service, separate accounts.
CLI_AUTH = ("TABLEAU_SERVER_USERNAME", "TABLEAU_SERVER_PASSWORD")

CONFIG_DIR = Path(os.environ.get(
    "TABLEAU_PREP_ETL_CONFIG_DIR",
    str(Path.home() / ".tableau-prep-etl"),
))
SERVER_CONFIG_FILE = CONFIG_DIR / "server.json"

# Same scheme on every backend so the loader script and Python discovery agree.
KEYCHAIN_SERVICE = "tableau-prep-etl"
_FIELD_TO_ACCOUNT = {
    "TABLEAU_SERVER_URL": "url",
    "TABLEAU_SERVER_PAT_NAME": "pat-name",
    "TABLEAU_SERVER_PAT_SECRET": "pat-secret",
    "TABLEAU_SERVER_SITE": "site",
    # Required for local prep-cli runs of flows that include
    # internal_published_ds sources. Tableau Prep CLI v2026.1 does
    # NOT accept PATs in its credentials JSON - product gap.
    "TABLEAU_SERVER_USERNAME": "tableau-username",
    "TABLEAU_SERVER_PASSWORD": "tableau-password",
}


@dataclass
class CredsResult:
    """Outcome of a discovery attempt.

    `status`:
      - "configured": all REQUIRED vars present in os.environ. Caller
        proceeds with server work.
      - "needs_user_decision": one or more REQUIRED vars are missing.
        Caller surfaces `suggestions` via AskUserQuestion.
    """
    status: str
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    source: str = ""  # "env" | "keychain" | "secret-tool" | "file" | ""
    suggestions: list[StorageOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "present": list(self.present),
            "missing": list(self.missing),
            "source": self.source,
            "suggestions": [s.to_dict() for s in self.suggestions],
        }


def is_configured(env: Optional[dict] = None) -> bool:
    env = env or os.environ
    return all((env.get(k, "") or "").strip() for k in REQUIRED)


def _missing_required(env: Optional[dict] = None) -> list[str]:
    env = env or os.environ
    return [k for k in REQUIRED if not (env.get(k, "") or "").strip()]


# === Auto-load paths =================================================

def _load_from_keychain() -> dict[str, str]:
    """macOS only. Returns dict of present env vars (may be partial)."""
    if platform.system() != "Darwin":
        return {}
    sec = shutil.which("security")
    if not sec:
        return {}
    out: dict[str, str] = {}
    for env_name, account in _FIELD_TO_ACCOUNT.items():
        try:
            res = subprocess.run(
                [sec, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
                capture_output=True, text=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if res.returncode == 0:
            val = (res.stdout or "").rstrip("\n")
            # site can legitimately be "" for default site on Server
            if val or env_name == "TABLEAU_SERVER_SITE":
                out[env_name] = val
    return out


def _load_from_secret_tool() -> dict[str, str]:
    """Linux libsecret. Same service/account scheme as macOS Keychain."""
    if platform.system() != "Linux":
        return {}
    bin_path = shutil.which("secret-tool")
    if not bin_path:
        return {}
    out: dict[str, str] = {}
    for env_name, account in _FIELD_TO_ACCOUNT.items():
        try:
            res = subprocess.run(
                [bin_path, "lookup", "service", KEYCHAIN_SERVICE, "account", account],
                capture_output=True, text=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if res.returncode == 0:
            val = (res.stdout or "").rstrip("\n")
            if val or env_name == "TABLEAU_SERVER_SITE":
                out[env_name] = val
    return out


def _load_from_file() -> dict[str, str]:
    """Plaintext fallback at ~/.tableau-prep-etl/server.json. Local dev only."""
    if not SERVER_CONFIG_FILE.exists():
        return {}
    try:
        cfg = json.loads(SERVER_CONFIG_FILE.read_text())
    except Exception:
        return {}
    out: dict[str, str] = {}
    mapping = {
        "TABLEAU_SERVER_URL": ("url",),
        "TABLEAU_SERVER_PAT_NAME": ("pat_name", "pat-name"),
        "TABLEAU_SERVER_PAT_SECRET": ("pat_secret", "pat-secret"),
        "TABLEAU_SERVER_SITE": ("site",),
    }
    for env_name, keys in mapping.items():
        for k in keys:
            if k in cfg and cfg[k] is not None:
                out[env_name] = str(cfg[k])
                break
    return out


def save_server_config(values: dict[str, str]) -> Path:
    """Write the local-dev config with chmod 600. LOCAL DEV USE ONLY."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, stat.S_IRWXU)
    except Exception:
        pass
    existing: dict = {}
    if SERVER_CONFIG_FILE.exists():
        try:
            existing = json.loads(SERVER_CONFIG_FILE.read_text())
        except Exception:
            existing = {}
    existing.update({k: v for k, v in values.items() if v is not None})
    SERVER_CONFIG_FILE.write_text(json.dumps(existing, indent=2))
    try:
        os.chmod(SERVER_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    return SERVER_CONFIG_FILE


def suggestions() -> list[StorageOption]:
    """Platform-aware secure-storage suggestions, recommended-first."""
    return _suggestions_for(platform.system())


def discover(env: Optional[dict] = None) -> CredsResult:
    """Discover Tableau Server creds. Mutates os.environ on success."""
    env = env if env is not None else os.environ

    if is_configured(env):
        return CredsResult(
            status="configured",
            present=list(REQUIRED) + ([OPTIONAL[0]] if env.get(OPTIONAL[0]) else []),
            source="env",
        )

    for loader_name, loader in (
        ("keychain", _load_from_keychain),
        ("secret-tool", _load_from_secret_tool),
        ("file", _load_from_file),
    ):
        loaded = loader()
        if not loaded:
            continue
        for k, v in loaded.items():
            if not (env.get(k, "") or "").strip():
                env[k] = v
        if is_configured(env):
            return CredsResult(
                status="configured",
                present=list(REQUIRED) + ([OPTIONAL[0]] if env.get(OPTIONAL[0]) else []),
                source=loader_name,
            )

    missing = _missing_required(env)
    return CredsResult(
        status="needs_user_decision",
        present=[k for k in REQUIRED if (env.get(k, "") or "").strip()],
        missing=missing,
        source="",
        suggestions=suggestions(),
    )


def has_cli_auth(env: Optional[dict] = None) -> bool:
    """True iff TABLEAU_SERVER_USERNAME + _PASSWORD are non-empty.
    Used by run_loop to decide whether to synthesize a credentials.json
    for prep-cli."""
    env = env or os.environ
    return all((env.get(k, "") or "").strip() for k in CLI_AUTH)


def synthesize_cli_credentials_json(tfl_path,
                                    out_path,
                                    env: Optional[dict] = None) -> dict:
    """Read sqlproxy connections from a .tfl and write a credentials.json
    matching prep-cli's expected schema (`{inputConnections: [{...}]}`).

    Tableau Prep CLI v2026.1 only accepts username/password in this file -
    PATs are explicitly rejected. This is a Tableau product gap, not a
    skill choice. The PAT path remains primary for publish/scan/metadata.

    The output file is written with chmod 600. The caller is responsible
    for deleting it after the CLI run.

    Returns a dict summarizing what was written; or {"status": "skipped",
    "reason": "..."} when no sqlproxy connections were found OR username
    /password aren't configured.
    """
    import json
    import zipfile
    from pathlib import Path
    env = env if env is not None else os.environ

    tfl_path = Path(tfl_path)
    out_path = Path(out_path)

    if not has_cli_auth(env):
        return {
            "status": "skipped",
            "reason": ("TABLEAU_SERVER_USERNAME / TABLEAU_SERVER_PASSWORD not set. "
                       "Required for prep-cli runs of flows with internal_published_ds "
                       "sources. Add via:\n"
                       "  security add-generic-password -s tableau-prep-etl -a tableau-username -U -w '<user>'\n"
                       "  security add-generic-password -s tableau-prep-etl -a tableau-password -U -w '<pass>'"),
        }

    try:
        with zipfile.ZipFile(tfl_path) as z:
            with z.open("flow") as f:
                flow = json.load(f)
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "message": str(e)}

    sqlproxy_conns: list[dict] = []
    for cid, c in (flow.get("connections") or {}).items():
        ca = (c.get("connectionAttributes") or {})
        if ca.get("class") == "sqlproxy":
            sqlproxy_conns.append({
                "id": cid,
                "server": ca.get("server", "").rstrip("/"),
                "siteUrlName": ca.get("siteUrlName", ""),
                "port": ca.get("port", "443"),
            })

    if not sqlproxy_conns:
        return {"status": "skipped",
                "reason": "no sqlproxy connections found in .tfl"}

    username = env.get("TABLEAU_SERVER_USERNAME", "").strip()
    password = env.get("TABLEAU_SERVER_PASSWORD", "").strip()

    input_connections = []
    for sc in sqlproxy_conns:
        try:
            port_int = int(sc["port"])
        except (TypeError, ValueError):
            port_int = 443
        input_connections.append({
            "hostname": sc["server"],
            "contentUrl": sc["siteUrlName"],
            "port": port_int,
            "username": username,
            "password": password,
        })

    creds = {"inputConnections": input_connections}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(creds, indent=2))
    try:
        os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

    return {
        "status": "ok",
        "path": str(out_path),
        "connection_count": len(input_connections),
    }


def secrets_in_spec(spec_dict: dict) -> bool:
    """True if this spec needs Tableau Server creds."""
    sources = spec_dict.get("sources") or []
    if any((s or {}).get("type") == "internal_published_ds" for s in sources):
        return True
    outputs = spec_dict.get("outputs") or []
    if any((o or {}).get("kind") == "published_data_source" for o in outputs):
        return True
    if (spec_dict.get("deployment") or "").lower() == "tableau_server":
        return True
    return False


def _print_suggestions(opts: list[StorageOption]) -> None:
    for i, o in enumerate(opts, 1):
        tag = " (recommended)" if o.recommended else ""
        print(f"\n[{i}] {o.label}{tag}")
        print(f"    {o.description}")
        if o.setup_commands:
            print("    Setup:")
            for cmd in o.setup_commands:
                print(f"      {cmd}")


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Tableau Server credential discovery + storage guidance.",
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true",
                     help="Print discovery result as JSON and exit 0/2.")
    grp.add_argument("--load", action="store_true",
                     help="Same as --check but try every secure store.")
    grp.add_argument("--suggest", action="store_true",
                     help="Print platform-aware secure-storage suggestions.")
    grp.add_argument("--save", action="store_true",
                     help="Write to ~/.tableau-prep-etl/server.json (plaintext, chmod 600).")
    ap.add_argument("--url", default=None)
    ap.add_argument("--pat-name", default=None)
    ap.add_argument("--pat-secret", default=None)
    ap.add_argument("--site", default=None)
    args = ap.parse_args(argv)

    if args.check:
        configured = is_configured()
        out = {
            "configured": configured,
            "present": [k for k in REQUIRED if (os.environ.get(k, "") or "").strip()],
            "missing": _missing_required(),
        }
        print(json.dumps(out, indent=2))
        return 0 if configured else 2

    if args.load:
        result = discover()
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status == "configured" else 2

    if args.suggest:
        opts = suggestions()
        print(f"Platform: {platform.system()}")
        _print_suggestions(opts)
        return 0

    if args.save:
        values = {
            "url": args.url, "pat_name": args.pat_name,
            "pat_secret": args.pat_secret, "site": args.site,
        }
        if not any(v for v in values.values()):
            print("--save requires at least one of --url/--pat-name/--pat-secret/--site",
                  file=sys.stderr)
            return 2
        path = save_server_config({k: v for k, v in values.items() if v is not None})
        print(f"wrote {path} (chmod 600). Local dev only - never commit.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
