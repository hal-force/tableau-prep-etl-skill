"""
Connector registry: cache + reuse rendered connector scripts across runs.

Public API:
    key_for(source) -> str
    lookup(source) -> CachedConnector | None
    store(source, rendered_path, defaults) -> CachedConnector

The registry lives at skill/connectors/. Each entry holds the rendered
Python step + a defaults.json. Subsequent runs whose source signature
matches reuse the cached connector instead of re-rendering.

Credentials are NEVER stored. Rendered scripts read os.environ at
runtime; only structural defaults (timeout_s, retry counts, headers,
URL patterns) live in defaults.json.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from skill.scripts.intake import Source


CONNECTORS_DIR = Path(__file__).resolve().parents[1] / "connectors"
INDEX_FILE = CONNECTORS_DIR / "index.json"


@dataclass
class CachedConnector:
    key: str
    source_signature: dict
    rendered_path: Path
    defaults: dict
    hit_count: int
    last_used_at: float


def _signature(source: Source) -> dict:
    """Stable signature of a source for cache keying. Path/host only —
    never includes secrets or per-run extras like dates."""
    if source.type == "local_folder":
        host = source.path or ""
    elif source.type == "native_connector":
        host = source.format or ""
    else:
        try:
            host = urlparse(source.url).hostname or ""
        except Exception:
            host = source.url
    return {
        "type": source.type,
        "host": host,
        "auth": source.auth,
        "format": source.format,
    }


def key_for(source: Source) -> str:
    sig = _signature(source)
    payload = "|".join(str(sig[k]) for k in ("type", "host", "auth", "format"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {"version": 1, "entries": {}}
    try:
        return json.loads(INDEX_FILE.read_text())
    except Exception:
        return {"version": 1, "entries": {}}


def _save_index(idx: dict) -> None:
    CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(idx, indent=2))


def lookup(source: Source) -> Optional[CachedConnector]:
    """Return a CachedConnector if a matching entry exists, else None."""
    key = key_for(source)
    idx = _load_index()
    entry = idx.get("entries", {}).get(key)
    if not entry:
        return None
    entry_dir = CONNECTORS_DIR / key
    rendered = entry_dir / "connector.py"
    defaults_file = entry_dir / "defaults.json"
    if not rendered.exists():
        return None
    defaults = {}
    if defaults_file.exists():
        try:
            defaults = json.loads(defaults_file.read_text())
        except Exception:
            defaults = {}
    return CachedConnector(
        key=key,
        source_signature=entry.get("signature", {}),
        rendered_path=rendered,
        defaults=defaults,
        hit_count=int(entry.get("hit_count", 0)),
        last_used_at=float(entry.get("last_used_at", 0.0)),
    )


def store(source: Source, rendered_path: Path,
          defaults: Optional[dict] = None) -> CachedConnector:
    """Cache a freshly-rendered connector. Returns the new CachedConnector."""
    key = key_for(source)
    sig = _signature(source)
    entry_dir = CONNECTORS_DIR / key
    entry_dir.mkdir(parents=True, exist_ok=True)
    cached_render = entry_dir / "connector.py"
    shutil.copyfile(rendered_path, cached_render)
    defaults = defaults or {}
    (entry_dir / "defaults.json").write_text(json.dumps(defaults, indent=2))
    (entry_dir / "manifest.json").write_text(json.dumps({
        "signature": sig,
        "stored_at": time.time(),
    }, indent=2))

    idx = _load_index()
    entries = idx.setdefault("entries", {})
    existing = entries.get(key, {})
    entries[key] = {
        "signature": sig,
        "hit_count": int(existing.get("hit_count", 0)) + 1,
        "last_used_at": time.time(),
    }
    _save_index(idx)
    return CachedConnector(
        key=key, source_signature=sig, rendered_path=cached_render,
        defaults=defaults, hit_count=entries[key]["hit_count"],
        last_used_at=entries[key]["last_used_at"],
    )


def touch(source: Source) -> None:
    """Bump hit count + last_used_at without re-rendering."""
    key = key_for(source)
    idx = _load_index()
    entry = idx.get("entries", {}).get(key)
    if not entry:
        return
    entry["hit_count"] = int(entry.get("hit_count", 0)) + 1
    entry["last_used_at"] = time.time()
    _save_index(idx)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="List all cached connectors")
    args = ap.parse_args()
    if args.list:
        idx = _load_index()
        print(json.dumps(idx, indent=2))
