"""Animate tab API (scaffold)."""

from __future__ import annotations

from typing import Any

from .router import router


@router.get("/animate/history")
def api_animate_history(limit: int = 25) -> dict[str, Any]:
    """Placeholder until video generation persistence exists."""
    _ = min(max(1, limit), 25)
    return {"items": []}
