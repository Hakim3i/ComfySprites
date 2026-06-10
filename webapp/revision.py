"""Monotonic dataset revision counter.

The ComfyUI-ComfySprites node caches ``/api/dropdowns`` keyed on this counter;
every mutating API endpoint calls :func:`bump_revision` so the next
``/api/dropdowns`` hit returns a fresh number and downstream caches
invalidate. Nothing here knows about content -- it is literally a
process-local incrementing integer.
"""

from __future__ import annotations

from itertools import count
from pathlib import Path
from threading import Lock

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_lock = Lock()
_counter = count(1)
_current = next(_counter)


def bump_revision() -> int:
    """Advance the counter and return the new value."""
    global _current
    with _lock:
        _current = next(_counter)
        return _current


def current_revision() -> int:
    """Return the latest revision number without advancing it."""
    return _current


def asset_revision() -> str:
    """Query-string token for ``/static`` assets."""
    latest = 0.0
    if _STATIC_DIR.is_dir():
        for path in _STATIC_DIR.rglob("*"):
            if path.is_file():
                latest = max(latest, path.stat().st_mtime)
    return f"{_current}-{int(latest)}"


__all__ = ["asset_revision", "bump_revision", "current_revision"]
