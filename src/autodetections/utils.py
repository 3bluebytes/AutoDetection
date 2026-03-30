from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


def safe_read_text(path: Path, limit: int | None = None) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    if limit is None:
        return content
    return content[:limit]


def dump_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "unknown"


def first_present(mapping: dict, keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return str(value)
    return default


def unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
