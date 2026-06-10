"""Load JSON config files from dataset/ (workspace copy, then shipped template)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_object(*paths: Path) -> dict[str, Any] | None:
    """Return the first readable JSON object among ``paths``, or ``None``."""
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            return data
    return None


def require_json_object(label: str, *paths: Path) -> dict[str, Any]:
    data = read_json_object(*paths)
    if data is None:
        tried = ", ".join(str(p) for p in paths)
        raise FileNotFoundError(f"{label} not found. Tried: {tried}")
    return data
