"""Shared ComfyUI WebSocket prompt-id filtering."""

from __future__ import annotations

from typing import Any


def matches_prompt_id(data: dict[str, Any], prompt_id: str) -> bool:
    """True when *data* belongs to *prompt_id* (missing id matches all)."""
    pid = data.get("prompt_id")
    if pid is None:
        return True
    return str(pid) == prompt_id
