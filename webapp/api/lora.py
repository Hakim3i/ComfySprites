"""Inline LoRA helpers shared across entity routes."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from ..services.design.forms import apply_inline_lora
from ..db import Lora, session_scope
from ..revision import bump_revision
from .router import router
from .schemas import LoraIn, LoraStrengthPatch
from .serializers import lora_summary


def apply_lora_payload(session, kind: str, lora_in: LoraIn | None, existing_id: int | None) -> int | None:
    if lora_in is None:
        return None
    return apply_inline_lora(
        session,
        kind=kind,
        existing_id=existing_id,
        filename=lora_in.filename,
        name=lora_in.name or lora_in.filename,
        trigger=lora_in.trigger,
        caption_trigger=lora_in.caption_trigger,
        strength=lora_in.strength,
        url=lora_in.url,
        download_url=lora_in.download_url,
        download_fallback_url=lora_in.download_fallback_url,
        model_id=lora_in.model_id,
        version_id=lora_in.version_id,
        comment=lora_in.comment,
    )


def has_field(payload: BaseModel, field: str) -> bool:
    return field in payload.model_fields_set


@router.patch("/loras/{lora_id}")
def api_loras_patch_strength(lora_id: int, payload: LoraStrengthPatch) -> dict[str, Any]:
    """Update LoRA strength only (Photo / Video Lab disk save)."""
    with session_scope() as session:
        row = session.get(Lora, lora_id)
        if row is None:
            raise HTTPException(status_code=404, detail="lora not found")
        row.strength = float(payload.strength)
        session.flush()
        out = lora_summary(row)
    bump_revision()
    return out
