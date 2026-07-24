"""Platform-aware secure-storage suggestions for Tableau Server creds.

Extracted from `server_creds.py` so the credentials module stays focused
on the actual discovery / load / save pipeline. This module is pure
data — three lists of `StorageOption`s selected by platform. No I/O,
no env-mutation, no side effects.

Public surface:
    suggestions_for(sysname: str) -> list[StorageOption]

`sysname` is `platform.system()`'s output ("Darwin" | "Linux" | "Windows"
| anything else — falls back to Linux).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field, asdict


@dataclass
class StorageOption:
    label: str
    description: str
    setup_commands: list[str] = field(default_factory=list)
    recommended: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


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


def suggestions_for(sysname: str) -> list[StorageOption]:
    """Return storage suggestions ranked recommended-first for the
    given `platform.system()` string. Unknown platforms get Linux
    suggestions (the closest generic set)."""
    if sysname == "Darwin":
        opts = _macos_suggestions()
    elif sysname == "Windows":
        opts = _windows_suggestions()
    else:
        opts = _linux_suggestions()
    return sorted(opts, key=lambda o: (not o.recommended, o.label))
