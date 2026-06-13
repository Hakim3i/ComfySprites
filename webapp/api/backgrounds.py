"""Background JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from ..db.models import ENTITY_BACKGROUND, DesignEntity
from ..db import session_scope
from ..revision import bump_revision
from .images import attach_upload_image
from .router import router
from .schemas import BackgroundIn
from .serializers import background_to_dict


def _bg_query():
    return select(DesignEntity).where(DesignEntity.entity_type == ENTITY_BACKGROUND)


def _apply_background(entity: DesignEntity, payload: BackgroundIn) -> None:
    entity.slug = payload.key
    entity.display_name = payload.key
    entity.scene_tags = list(payload.tags)
    entity.video_prompt = (payload.video_prompt or "").strip() or None
    entity.negative = (payload.negative or "").strip()


@router.get("/backgrounds")
def api_backgrounds_list() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.scalars(_bg_query().order_by(DesignEntity.slug)).all()
        return [background_to_dict(r) for r in rows]


@router.get("/backgrounds/{key:path}")
def api_background_get(key: str) -> dict[str, Any]:
    with session_scope() as s:
        row = s.scalar(_bg_query().where(DesignEntity.slug == key))
        if row is None:
            raise HTTPException(404, "background not found")
        return background_to_dict(row)


@router.post("/backgrounds", status_code=201)
def api_backgrounds_create(payload: BackgroundIn) -> dict[str, Any]:
    with session_scope() as s:
        if s.scalar(_bg_query().where(DesignEntity.slug == payload.key)) is not None:
            raise HTTPException(409, f"key {payload.key!r} already in use")
        entity = DesignEntity(
            slug=payload.key,
            display_name=payload.key,
            entity_type=ENTITY_BACKGROUND,
        )
        s.add(entity)
        s.flush()
        _apply_background(entity, payload)
        out = background_to_dict(entity)
    bump_revision()
    return out


@router.put("/backgrounds/{key:path}")
def api_background_replace(key: str, payload: BackgroundIn) -> dict[str, Any]:
    with session_scope() as s:
        entity = s.scalar(_bg_query().where(DesignEntity.slug == key))
        if entity is None:
            raise HTTPException(404, "background not found")
        _apply_background(entity, payload)
        bump_revision()
        return background_to_dict(entity)


@router.delete("/backgrounds/{key:path}", status_code=204)
def api_background_delete(key: str) -> Response:
    with session_scope() as s:
        entity = s.scalar(_bg_query().where(DesignEntity.slug == key))
        if entity is None:
            raise HTTPException(404, "background not found")
        s.delete(entity)
    bump_revision()
    return Response(status_code=204)


@router.post("/backgrounds/{key:path}/image")
async def api_background_image(
    key: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    with session_scope() as s:
        entity = s.scalar(_bg_query().where(DesignEntity.slug == key))
        if entity is None:
            raise HTTPException(404, "background not found")
        attach_upload_image(
            entity, file=file, entity_dir="backgrounds", slug=entity.slug
        )
        out = {"key": entity.slug, "image_path": entity.image_path}
    bump_revision()
    return out
