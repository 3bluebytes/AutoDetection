#!/usr/bin/env python3
"""
Shared helpers for the thin OpenClaw runtime wrappers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ensure project root is in sys.path for standard imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


# Standard imports for business logic modules
# Import these directly in wrapper scripts:
#   from openclaw_tools.tools.rule_match import classify_failure
#   from openclaw_tools.tools.version_identifier import extract_uvp_version
#   etc.

