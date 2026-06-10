"""Animation JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select

from ..db import Animation, session_scope
from ..db.models import LORA_KIND_ANIMATION
from ..revision import bump_revision
from ..services.design.animation_fields import (
    normalize_animation_framings,
    normalize_animation_subject_type,
)
from .images import attach_upload_image
from .lora import apply_lora_payload, has_field
from .router import router
from .schemas import AnimationIn
from .serializers import animation_to_dict


@router.get("/animations")
def list_animations(q: str = "") -> list[dict[str, Any]]:
    with session_scope() as s:
        query = select(Animation).order_by(Animation.slug)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(Animation.slug.ilike(like), Animation.menu_name.ilike(like))
            )
        return [animation_to_dict(a) for a in s.scalars(query).all()]


@router.get("/animations/{slug}")
def get_animation(slug: str) -> dict[str, Any]:
    with session_scope() as s:
        row = s.scalar(select(Animation).where(Animation.slug == slug))
        if row is None:
            raise HTTPException(404, "animation not found")
        return animation_to_dict(row)


@router.post("/animations", status_code=201)
def create_animation(payload: AnimationIn) -> dict[str, Any]:
    with session_scope() as s:
        if (
            s.scalar(select(Animation.id).where(Animation.slug == payload.slug))
            is not None
        ):
            raise HTTPException(400, f"slug '{payload.slug}' already exists")
        row = Animation(slug=payload.slug, menu_name=payload.menu_name or payload.slug)
        _apply_payload(s, row, payload)
        s.add(row)
        s.flush()
        bump_revision()
        return animation_to_dict(row)


@router.put("/animations/{slug}")
def replace_animation(slug: str, payload: AnimationIn) -> dict[str, Any]:
    with session_scope() as s:
        row = s.scalar(select(Animation).where(Animation.slug == slug))
        if row is None:
            raise HTTPException(404, "animation not found")
        if payload.slug != slug and s.scalar(
            select(Animation.id).where(Animation.slug == payload.slug)
        ):
            raise HTTPException(400, f"slug '{payload.slug}' already exists")
        _apply_payload(s, row, payload)
        bump_revision()
        return animation_to_dict(row)


@router.delete("/animations/{slug}", status_code=204)
def delete_animation(slug: str) -> Response:
    with session_scope() as s:
        row = s.scalar(select(Animation).where(Animation.slug == slug))
        if row is None:
            raise HTTPException(404, "animation not found")
        s.delete(row)
    bump_revision()
    return Response(status_code=204)


@router.post("/animations/{slug}/image")
async def upload_animation_image(
    slug: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    with session_scope() as s:
        row = s.scalar(select(Animation).where(Animation.slug == slug))
        if row is None:
            raise HTTPException(404, "animation not found")
        attach_upload_image(row, file=file, entity_dir="animations", slug=row.slug)
        out = {"slug": row.slug, "image_path": row.image_path}
    bump_revision()
    return out


def _apply_payload(session, animation: Animation, payload: AnimationIn) -> None:
    animation.slug = payload.slug
    animation.menu_name = (payload.menu_name or payload.slug).strip()
    animation.comment = payload.comment
    animation.tags = list(payload.tags)
    animation.framings = normalize_animation_framings(session, payload.framings)
    orient = (payload.orientation or "portrait").strip().lower()
    if orient not in ("portrait", "landscape", "both"):
        raise HTTPException(400, "invalid orientation")
    animation.orientation = orient
    animation.subject_type = normalize_animation_subject_type(payload.subject_type)
    if has_field(payload, "controlnets"):
        from ..services.catalog.controlnet_types import normalize_controlnets_map

        animation.controlnets = normalize_controlnets_map(payload.controlnets)
    if has_field(payload, "lora"):
        animation.lora_id = apply_lora_payload(
            session, LORA_KIND_ANIMATION, payload.lora, animation.lora_id
        )
