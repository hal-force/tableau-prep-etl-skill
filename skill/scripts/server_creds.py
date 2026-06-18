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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Bootstrap tflb_lib + auto_refine import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401


REQUIRED = ("TABLEAU_SERVER_URL", "TABLEAU_SERVER_PAT_NAME", "TABLEAU_SERVER_PAT_SECRET")
OPTIONAL = ("TABLEAU_SERVER_SITE",)  # empty string OK for default site on Server

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
}


@dataclass
class StorageOption:
    label: str
    description: str
    setup_commands: list[str] = field(default_factory=list)
    recommended: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


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


# === Platform-aware suggestions =====================================

def _macos_suggestions() -> list[StorageOption]:
    return [
        StorageOption(
            label="macOS Keychain (recommended)",
            description=(
                "Encrypted at rest via your login keychain. No plaintext on "
                "disk. Auto-unlocks on login; survives reboots. The skill "
                "auto-loads via `security` on every server-bound call."
            ),
            setup_commands=[
                "security add-generic-password -s tableau-prep-etl -a url -U "
                "-w 'https://YOUR-SERVER.online.tableau.com'",
                "security add-generic-password -s tableau-prep-etl -a pat-name -U "
                "-w 'YOUR_PAT_NAME'",
                "security add-generic-password -s tableau-prep-etl -a pat-secret -U "
                "-w 'YOUR_PAT_SECRET'",
                "security add-generic-password -s tableau-prep-etl -a site -U "
                "-w 'YOUR_SITE_CONTENT_URL'",
                "# Verify:",
                "python3 -m skill.scripts.server_creds --check",
            ],
            recommended=True,
        ),
        StorageOption(
            label="1Password / Bitwarden CLI",
            description=(
                "Strongest option for shared secrets across teammates or "
                "devices. Fetched per-shell with `op read` / `bw get`."
            ),
            setup_commands=[
                "# 1Password example:",
                "op item create --category=login --title='tableau-prep-etl' \\",
                "  url='https://YOUR-SERVER.online.tableau.com' username='YOUR_PAT_NAME' \\",
                "  password='YOUR_PAT_SECRET' site='YOUR_SITE'",
                "# Then in your shell init:",
                "export TABLEAU_SERVER_URL=$(op read 'op://Personal/tableau-prep-etl/url')",
                "export TABLEAU_SERVER_PAT_NAME=$(op read 'op://Personal/tableau-prep-etl/username')",
                "export TABLEAU_SERVER_PAT_SECRET=$(op read 'op://Personal/tableau-prep-etl/password')",
                "export TABLEAU_SERVER_SITE=$(op read 'op://Personal/tableau-prep-etl/site')",
            ],
        ),
        StorageOption(
            label="Local config file (~/.tableau-prep-etl/server.json)",
            description=(
                "Plaintext on disk, chmod 600. Easiest to set up but "
                "weaker - never commit, never copy to shared drives."
            ),
            setup_commands=[
                "python3 -m skill.scripts.server_creds --save \\",
                "  --url 'https://YOUR-SERVER.online.tableau.com' \\",
                "  --pat-name 'YOUR_PAT_NAME' --pat-secret 'YOUR_PAT_SECRET' \\",
                "  --site 'YOUR_SITE'",
            ],
        ),
    ]


def _linux_suggestions() -> list[StorageOption]:
    has_secret_tool = shutil.which("secret-tool") is not None
    opts: list[StorageOption] = []
    if has_secret_tool:
        opts.append(StorageOption(
            label="GNOME Keyring / KWallet (recommended)",
            description=(
                "libsecret-backed credential store. Encrypted at rest. "
                "Skill auto-loads via `secret-tool lookup` on server calls."
            ),
            setup_commands=[
                "secret-tool store --label='tableau-prep-etl url' "
                "service tableau-prep-etl account url",
                "secret-tool store --label='tableau-prep-etl pat-name' "
                "service tableau-prep-etl account pat-name",
                "secret-tool store --label='tableau-prep-etl pat-secret' "
                "service tableau-prep-etl account pat-secret",
                "secret-tool store --label='tableau-prep-etl site' "
                "service tableau-prep-etl account site",
            ],
            recommended=True,
        ))
    opts.append(StorageOption(
        label="direnv per-project .envrc",
        description=(
            "Auto-loads env vars when you `cd` into the project dir. "
            "Plaintext file - chmod 600 mandatory. Add .envrc to .gitignore."
        ),
        setup_commands=[
            "brew install direnv  # or apt/dnf",
            "cat > .envrc <<'EOF'",
            "export TABLEAU_SERVER_URL='https://YOUR-SERVER.online.tableau.com'",
            "export TABLEAU_SERVER_PAT_NAME='YOUR_PAT_NAME'",
            "export TABLEAU_SERVER_PAT_SECRET='YOUR_PAT_SECRET'",
            "export TABLEAU_SERVER_SITE='YOUR_SITE'",
            "EOF",
            "chmod 600 .envrc && direnv allow",
        ],
        recommended=not has_secret_tool,
    ))
    opts.append(StorageOption(
        label="HashiCorp Vault / cloud secret manager",
        description=(
            "Production path. Fetch at process start via your CI/secrets "
            "agent and inject as env vars. Never write secrets to disk."
        ),
        setup_commands=[
            "export TABLEAU_SERVER_PAT_SECRET=$(vault kv get -field=pat_secret secret/tableau)",
        ],
    ))
    return opts


def _windows_suggestions() -> list[StorageOption]:
    return [
        StorageOption(
            label="Windows Credential Manager (recommended)",
            description=(
                "DPAPI-encrypted per-user credential store. Persistent "
                "across sessions. Read with `cmdkey` or PowerShell."
            ),
            setup_commands=[
                "cmdkey /add:tableau-prep-etl-url /user:url /pass:'https://YOUR-SERVER.online.tableau.com'",
                "cmdkey /add:tableau-prep-etl-pat-name /user:pat-name /pass:'YOUR_PAT_NAME'",
                "cmdkey /add:tableau-prep-etl-pat-secret /user:pat-secret /pass:'YOUR_PAT_SECRET'",
                "cmdkey /add:tableau-prep-etl-site /user:site /pass:'YOUR_SITE'",
            ],
            recommended=True,
        ),
        StorageOption(
            label="PowerShell SecureString in profile",
            description=(
                "Use $env: at session start with values pulled from a "
                "DPAPI-protected file (Export-Clixml / Import-Clixml)."
            ),
            setup_commands=[
                "Get-Credential | Export-Clixml -Path $HOME\\.tableau-prep-etl\\creds.xml",
                "$c = Import-Clixml $HOME\\.tableau-prep-etl\\creds.xml",
                "$env:TABLEAU_SERVER_PAT_NAME = $c.UserName",
                "$env:TABLEAU_SERVER_PAT_SECRET = $c.GetNetworkCredential().Password",
            ],
        ),
        StorageOption(
            label="Local config file (%USERPROFILE%\\.tableau-prep-etl\\server.json)",
            description=(
                "Plaintext fallback. Restrict ACLs to your user (icacls)."
            ),
            setup_commands=[
                "python -m skill.scripts.server_creds --save ^",
                "  --url \"https://YOUR-SERVER.online.tableau.com\" ^",
                "  --pat-name \"YOUR_PAT_NAME\" --pat-secret \"YOUR_PAT_SECRET\" ^",
                "  --site \"YOUR_SITE\"",
                "icacls \"%USERPROFILE%\\.tableau-prep-etl\\server.json\" /inheritance:r /grant:r \"%USERNAME%:F\"",
            ],
        ),
    ]


def suggestions() -> list[StorageOption]:
    sysname = platform.system()
    if sysname == "Darwin":
        opts = _macos_suggestions()
    elif sysname == "Linux":
        opts = _linux_suggestions()
    elif sysname == "Windows":
        opts = _windows_suggestions()
    else:
        opts = _linux_suggestions()
    return sorted(opts, key=lambda o: (not o.recommended, o.label))


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
