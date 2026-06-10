"""Characters and design entities."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select

from ..services.design import attributes as char_attrs
from ..services.design.forms import clear_uploaded_image
from ..db import (
    LORA_KIND_CHARACTER,
    ROLE_MAIN,
    Character,
    session_scope,
)
from ..db.models import ENTITY_CHARACTER, ENTITY_MONSTER, ENTITY_OBJECT
from ..revision import bump_revision
from ..services.validate import raise_validation_errors, validate_character
from .images import attach_upload_image
from .lora import apply_lora_payload, has_field
from .router import router
from .schemas import CharacterIn
from .serializers import character_to_dict, design_entity_to_dict


def _list_characters(q: str = "") -> list[dict[str, Any]]:
    with session_scope() as s:
        query = (
            select(Character)
            .where(Character.role == ROLE_MAIN, Character.entity_type == ENTITY_CHARACTER)
            .order_by(Character.slug)
        )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    Character.slug.ilike(like),
                    Character.display_name.ilike(like),
                    Character.name_tag.ilike(like),
                )
            )
        rows = s.scalars(query).all()
        for c in rows:
            _ = c.character_lora
        return [character_to_dict(c) for c in rows]


def _apply_character_payload(session, c: Character, payload: CharacterIn) -> None:
    c.slug = payload.slug
    c.display_name = (payload.display_name or payload.slug).strip()
    c.name_tag = (payload.name_tag or payload.slug).strip()
    c.comment = payload.comment
    c.role = ROLE_MAIN
    c.identity_core = list(payload.identity_core)
    c.outfit_head = list(payload.outfit_head)
    c.outfit_upper = list(payload.outfit_upper)
    c.outfit_lower = list(payload.outfit_lower)
    c.outfit_extra = list(payload.outfit_extra)
    for attr in char_attrs.ATTRIBUTES:
        value = getattr(payload, attr.key, None)
        setattr(c, attr.key, char_attrs.coerce_physical_incoming(attr, value))
    if has_field(payload, "lora"):
        c.lora_id = apply_lora_payload(
            session, LORA_KIND_CHARACTER, payload.lora, c.lora_id
        )


def _get_character(session, slug: str) -> Character:
    c = session.scalar(
        select(Character).where(Character.slug == slug, Character.role == ROLE_MAIN)
    )
    if c is None:
        raise HTTPException(404, f"character {slug!r} not found")
    return c


def _create_character(payload: CharacterIn) -> dict[str, Any]:
    with session_scope() as s:
        if s.scalar(select(Character.id).where(Character.slug == payload.slug)) is not None:
            raise HTTPException(409, f"slug {payload.slug!r} already in use")
        c = Character(
            slug=payload.slug,
            display_name=payload.slug,
            name_tag=payload.slug,
            entity_type=ENTITY_CHARACTER,
            role=ROLE_MAIN,
        )
        _apply_character_payload(s, c, payload)
        s.add(c)
        s.flush()
        _ = c.character_lora
        raise_validation_errors(validate_character(s, c))
        out = character_to_dict(c)
    bump_revision()
    return out


def _update_character(slug: str, payload: CharacterIn) -> dict[str, Any]:
    with session_scope() as s:
        c = _get_character(s, slug)
        if payload.slug != slug:
            if s.scalar(select(Character.id).where(Character.slug == payload.slug, Character.id != c.id)) is not None:
                raise HTTPException(409, f"slug {payload.slug!r} already in use")
        _apply_character_payload(s, c, payload)
        s.flush()
        _ = c.character_lora
        raise_validation_errors(validate_character(s, c))
        out = character_to_dict(c)
    bump_revision()
    return out


def _delete_character(slug: str) -> Response:
    with session_scope() as s:
        c = _get_character(s, slug)
        clear_uploaded_image(c.image_path)
        s.delete(c)
    bump_revision()
    return Response(status_code=204)


def _upload_character_image(slug: str, file: UploadFile) -> dict[str, Any]:
    with session_scope() as s:
        c = _get_character(s, slug)
        attach_upload_image(c, file=file, entity_dir="characters", slug=c.slug)
        out = {"slug": c.slug, "image_path": c.image_path}
    bump_revision()
    return out


def _drop_character_image(slug: str) -> Response:
    with session_scope() as s:
        c = _get_character(s, slug)
        clear_uploaded_image(c.image_path)
        c.image_path = None
    bump_revision()
    return Response(status_code=204)


def _list_design_entities(entity_type: str, q: str = "") -> list[dict[str, Any]]:
    with session_scope() as s:
        query = (
            select(Character)
            .where(Character.entity_type == entity_type, Character.role == ROLE_MAIN)
            .order_by(Character.slug)
        )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    Character.slug.ilike(like),
                    Character.display_name.ilike(like),
                    Character.name_tag.ilike(like),
                )
            )
        rows = s.scalars(query).all()
        for c in rows:
            _ = c.character_lora
        return [design_entity_to_dict(c) for c in rows]


@router.get("/characters")
def api_characters_list(q: str = "") -> list[dict[str, Any]]:
    return _list_characters(q)


@router.get("/monsters")
def api_monsters_list(q: str = "") -> list[dict[str, Any]]:
    return _list_design_entities(ENTITY_MONSTER, q)


@router.get("/objects")
def api_objects_list(q: str = "") -> list[dict[str, Any]]:
    return _list_design_entities(ENTITY_OBJECT, q)


@router.post("/characters", status_code=201)
def api_characters_create(payload: CharacterIn) -> dict[str, Any]:
    return _create_character(payload)


@router.get("/characters/{slug}")
def api_characters_get(slug: str) -> dict[str, Any]:
    with session_scope() as s:
        c = _get_character(s, slug)
        _ = c.character_lora
        return character_to_dict(c)


@router.put("/characters/{slug}")
def api_characters_update(slug: str, payload: CharacterIn) -> dict[str, Any]:
    return _update_character(slug, payload)


@router.delete("/characters/{slug}", status_code=204)
def api_characters_delete(slug: str) -> Response:
    return _delete_character(slug)


@router.post("/characters/{slug}/image")
async def api_characters_image(slug: str, file: UploadFile = File(...)) -> dict[str, Any]:
    return _upload_character_image(slug, file=file)


@router.delete("/characters/{slug}/image", status_code=204)
def api_characters_image_delete(slug: str) -> Response:
    return _drop_character_image(slug)
