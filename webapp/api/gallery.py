"""Gallery API — browse and manage Make Lab outputs."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..db import session_scope
from ..services.generations import delete_gallery_item, get_gallery_item
from .router import router


@router.get("/gallery/items/{prompt_id}")
def api_gallery_item(prompt_id: str) -> dict[str, Any]:
    """Single generation for preview and Make Lab handoff."""
    with session_scope() as session:
        item = get_gallery_item(session, prompt_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return item


@router.delete("/gallery/items/{prompt_id}")
def api_gallery_item_delete(prompt_id: str) -> dict[str, bool]:
    """Remove one generation row and its on-disk output file."""
    with session_scope() as session:
        deleted = delete_gallery_item(session, prompt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Generation not found")
    return {"deleted": True}
