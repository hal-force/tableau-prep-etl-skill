"""
LLM gateway/model configuration for the tableau-prep-etl skill.

Discovery order:
  1. Environment variables (LLM_GATEWAY_URL, LLM_GATEWAY_KEY,
     LLM_GATEWAY_MODEL) — preferred for production / CI / Tableau
     Server scheduling, where credentials must come from a secret
     store, not files.
  2. Local-only config at ~/.tableau-prep-etl/config.json — used
     ONLY for local dev/testing. NEVER ship this file or its contents
     to Tableau Server, GitHub, or any deployed artifact.

The skill never embeds creds into rendered Python scripts. Rendered
scripts read os.environ at runtime, so a published .tfl can be run
on a server where LLM_GATEWAY_KEY comes from the server's secret
manager.

Public API:
    load_llm_config(prompt_if_missing: bool = True) -> dict
    save_llm_config(cfg: dict) -> Path
    require_env_for_publish() -> None  # raises if config came from file
"""
from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path(os.environ.get(
    "TABLEAU_PREP_ETL_CONFIG_DIR",
    str(Path.home() / ".tableau-prep-etl"),
))
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class LLMConfig:
    url: str
    key: str
    model: str
    source: str   # "env" | "file" | "prompt"

    def to_env(self) -> dict[str, str]:
        return {
            "LLM_GATEWAY_URL": self.url,
            "LLM_GATEWAY_KEY": self.key,
            "LLM_GATEWAY_MODEL": self.model,
        }


def _from_env() -> Optional[LLMConfig]:
    url = os.environ.get("LLM_GATEWAY_URL", "").strip()
    key = os.environ.get("LLM_GATEWAY_KEY", "").strip()
    model = os.environ.get("LLM_GATEWAY_MODEL", "claude-sonnet-4-6").strip()
    if url and key and "your-gateway.example.com" not in url:
        return LLMConfig(url=url, key=key, model=model, source="env")
    return None


def _from_file() -> Optional[LLMConfig]:
    if not CONFIG_FILE.exists():
        return None
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except Exception:
        return None
    url = (cfg.get("url") or "").strip()
    key = (cfg.get("key") or "").strip()
    model = (cfg.get("model") or "claude-sonnet-4-6").strip()
    if not (url and key):
        return None
    return LLMConfig(url=url, key=key, model=model, source="file")


def _prompt() -> Optional[LLMConfig]:
    """Interactive first-run prompt. Skipped if not on a TTY."""
    if not sys.stdin.isatty():
        return None
    print("=" * 60, file=sys.stderr)
    print("LLM gateway not configured.", file=sys.stderr)
    print("This is for LOCAL DEV ONLY — production must use env vars", file=sys.stderr)
    print("(LLM_GATEWAY_URL, LLM_GATEWAY_KEY, LLM_GATEWAY_MODEL).", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    try:
        url = input("Gateway URL (e.g. https://your-gateway/chat/completions): ").strip()
        key = input("Bearer key: ").strip()
        model = input("Model [claude-sonnet-4-6]: ").strip() or "claude-sonnet-4-6"
    except (EOFError, KeyboardInterrupt):
        return None
    if not (url and key):
        return None
    cfg = LLMConfig(url=url, key=key, model=model, source="prompt")
    save_llm_config({"url": url, "key": key, "model": model})
    return cfg


def save_llm_config(cfg: dict) -> Path:
    """Write config to ~/.tableau-prep-etl/config.json with chmod 600.
    LOCAL DEV USE ONLY. Never ship this file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    return CONFIG_FILE


def load_llm_config(prompt_if_missing: bool = True) -> Optional[LLMConfig]:
    """Discover LLM config from env, then file, then optional prompt.
    Returns None if no config can be discovered (e.g. no-LLM mode)."""
    return _from_env() or _from_file() or (_prompt() if prompt_if_missing else None)


def require_env_for_publish() -> None:
    """Guardrail: if you're about to publish a flow to Tableau Server,
    the LLM config must come from env vars. File-sourced creds risk
    leaking onto the server."""
    cfg = load_llm_config(prompt_if_missing=False)
    if cfg is None:
        return
    if cfg.source != "env":
        raise RuntimeError(
            "LLM gateway is configured from a local file. "
            "Set LLM_GATEWAY_URL / LLM_GATEWAY_KEY / LLM_GATEWAY_MODEL "
            "as environment variables before publishing — local config "
            "files must NEVER ship to Tableau Server."
        )


if __name__ == "__main__":
    cfg = load_llm_config(prompt_if_missing=True)
    if cfg is None:
        print("no LLM config (will run in no-LLM mode if requested)", file=sys.stderr)
        sys.exit(2)
    print(f"source={cfg.source} model={cfg.model} url={cfg.url[:40]}...")
