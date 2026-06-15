"""
sys.path bootstrap so the skill's scripts can import tflb_lib without
the user setting PYTHONPATH.

Layout assumption: this file is at <repo_root>/skill/scripts/lib/__init__.py
and tflb_lib lives at <repo_root>/tflb_lib/. We add <repo_root> to sys.path.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
