"""Background (scene) CRUD at ``/backgrounds``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...services.design.forms import (
    clear_uploaded_image,
    joined,
    parse_bool,
    parse_taglist,
    save_uploaded_image,
)
from ...db import ENTITY_BACKGROUND, DesignEntity, session_scope
from ...services.design.embed import embed_context, embed_redirect
from ...revision import bump_revision

router = APIRouter()


def _apply_background_form(entity: DesignEntity, form) -> None:
    entity.slug = (form.get("key") or entity.slug).strip()
    entity.display_name = entity.slug
    entity.scene_tags = parse_taglist(form.get("tags"))
    entity.video_prompt = (form.get("video_prompt") or "").strip() or None
    entity.negative = (form.get("negative") or "").strip()
    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(entity.image_path)
        entity.image_path = None
    else:
        upload = form.get("image")
        entity.image_path = save_uploaded_image(
            upload, entity="backgrounds", slug=entity.key, existing=entity.image_path
        )


@router.get("", response_class=HTMLResponse, name="backgrounds_list")
def backgrounds_list(request: Request, q: str = Query("")):
    with session_scope() as s:
        query = (
            select(DesignEntity)
            .where(DesignEntity.entity_type == ENTITY_BACKGROUND)
            .order_by(DesignEntity.slug)
        )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(DesignEntity.slug.ilike(like))
        rows = s.scalars(query).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "design/backgrounds_list.html",
        {"active": "backgrounds", "rows": rows, "q": q},
    )


@router.get("/new", response_class=HTMLResponse, name="backgrounds_new")
def backgrounds_new(request: Request):
    blank = DesignEntity(
        slug="",
        display_name="",
        entity_type=ENTITY_BACKGROUND,
        scene_tags=[],
    )
    blank.id = None
    return request.app.state.templates.TemplateResponse(
        request,
        "design/background_form.html",
        {
            "active": "backgrounds",
            "loc": blank,
            "joined": joined,
            **embed_context(request),
        },
    )


@router.post("", response_class=HTMLResponse)
async def backgrounds_create(request: Request):
    form = await request.form()
    key = (form.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "Key is required.")
    with session_scope() as s:
        if (
            s.scalar(
                select(DesignEntity.id).where(
                    DesignEntity.entity_type == ENTITY_BACKGROUND,
                    DesignEntity.slug == key,
                )
            )
            is not None
        ):
            raise HTTPException(
                400, f"Choose a different key — '{key}' is already in use."
            )
        entity = DesignEntity(slug=key, display_name=key, entity_type=ENTITY_BACKGROUND)
        s.add(entity)
        s.flush()
        _apply_background_form(entity, form)
    bump_revision()
    return embed_redirect(request, f"/backgrounds/{key}", form=form)


@router.post("/{key:path}/delete", response_class=HTMLResponse)
def backgrounds_delete(key: str):
    with session_scope() as s:
        entity = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if entity is not None:
            clear_uploaded_image(entity.image_path)
            s.delete(entity)
    bump_revision()
    return RedirectResponse("/backgrounds", status_code=303)


@router.get("/{key:path}", response_class=HTMLResponse, name="backgrounds_edit")
def backgrounds_edit(request: Request, key: str):
    with session_scope() as s:
        entity = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if entity is None:
            raise HTTPException(404, "background not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "design/background_form.html",
        {
            "active": "backgrounds",
            "loc": entity,
            "joined": joined,
            **embed_context(request),
        },
    )


@router.post("/{key:path}", response_class=HTMLResponse)
async def backgrounds_update(request: Request, key: str):
    form = await request.form()
    new_key = (form.get("key") or "").strip() or key
    with session_scope() as s:
        entity = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if entity is None:
            raise HTTPException(404, "background not found")
        if (
            new_key != key
            and s.scalar(
                select(DesignEntity.id).where(
                    DesignEntity.entity_type == ENTITY_BACKGROUND,
                    DesignEntity.slug == new_key,
                )
            )
            is not None
        ):
            raise HTTPException(
                400, f"Choose a different key — '{new_key}' is already in use."
            )
        _apply_background_form(entity, form)
    bump_revision()
    return embed_redirect(request, f"/backgrounds/{new_key}", form=form)
