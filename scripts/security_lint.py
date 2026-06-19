#!/usr/bin/env python3
"""Security linter for archived flow specs.

Walks `flows/*/v*/spec.json` (or any path passed on the CLI) and runs
each spec through `skill.scripts.spec_validation.validate_spec`. Any
violation is printed as `<spec_path>: <error>`. Exit 0 when clean,
1 when any spec failed.

Also reports any host in `spec.sources[*].url` not present in
`~/.tableau-prep-etl/known_hosts.json` and not under an
`~/.tableau-prep-etl/internal_hosts.txt` suffix — operator-facing
"have I approved this?" check that complements the runtime gate in
`host_trust.ensure_hosts_approved`.

Usage:
    python3 scripts/security_lint.py                # lint all flows/
    python3 scripts/security_lint.py path/to/spec.json [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the skill package is importable when invoked as a CLI from
# the repo root regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from skill.scripts import host_trust  # noqa: E402
from skill.scripts.spec_validation import (  # noqa: E402
    _host_matches_internal_trust,
    validate_spec,
)


def _iter_specs(args: list[str]) -> list[Path]:
    if args:
        out: list[Path] = []
        for a in args:
            p = Path(a)
            if p.is_dir():
                out.extend(sorted(p.rglob("spec.json")))
            else:
                out.append(p)
        return out
    return sorted((_REPO_ROOT / "flows").rglob("spec.json"))


def _lint_one(path: Path) -> list[str]:
    try:
        d = json.loads(path.read_text())
    except Exception as e:
        return [f"{path}: failed to parse JSON: {e}"]
    errs = list(validate_spec(d))
    out = [f"{path}: {e}" for e in errs]
    # Host-approval check: report any source URL host that isn't on the
    # internal-trust list and isn't recorded in known_hosts.json.
    for h in host_trust.extract_hosts(d):
        if _host_matches_internal_trust(h):
            continue
        if not host_trust.is_host_known(h):
            out.append(
                f"{path}: host {h!r} is not approved "
                f"(not in known_hosts.json, not internal-trust). "
                "Re-run intake or `record_approval` after vetting."
            )
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    specs = _iter_specs(argv)
    if not specs:
        print("no specs found; pass paths or run from repo root with flows/ present",
              file=sys.stderr)
        return 2
    bad = 0
    for sp in specs:
        for line in _lint_one(sp):
            print(line)
            bad += 1
    if bad:
        print(f"\nFAIL: {bad} violation(s) across {len(specs)} spec(s)",
              file=sys.stderr)
        return 1
    print(f"OK: {len(specs)} spec(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
