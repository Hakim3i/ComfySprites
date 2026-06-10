"""Taxonomy editors: views (camera framings), locations.

Act categories have been removed — every act is self-contained now.
Partners are *not* a taxonomy — they live in ``Character`` rows with
``role='partner'`` and are managed via ``/partners`` (see
``routes.characters``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...services.design.forms import (
    clear_uploaded_image,
    joined,
    parse_bool,
    parse_int,
    parse_taglist,
    save_uploaded_image,
)
from ...db import (
    ENTITY_BACKGROUND,
    VIEW_KINDS,
    VIEW_KIND_SHOT,
    DesignEntity,
    View,
    session_scope,
)
from ...services.design.embed import embed_context, embed_redirect, is_embed
from ...revision import bump_revision

router = APIRouter()

# ---------------------------------------------------------------------------
# Views — camera framings (Danbooru-style: shot / angle / pov / focus)
# ---------------------------------------------------------------------------


@router.get("/views", response_class=HTMLResponse, name="views_list")
def views_list(request: Request, kind: str = Query("")):
    with session_scope() as s:
        query = select(View).order_by(View.kind, View.position, View.key)
        if kind:
            query = query.where(View.kind == kind)
        rows = s.scalars(query).all()
        grouped: dict[str, list[View]] = {k: [] for k in VIEW_KINDS}
        for v in rows:
            grouped.setdefault(v.kind, []).append(v)
    return request.app.state.templates.TemplateResponse(
        request,
        "views/list.html",
        {"active": "views", "grouped": grouped, "kinds": list(VIEW_KINDS), "kind": kind, **embed_context(request)},
    )


@router.get("/views/new", response_class=HTMLResponse)
def views_new(request: Request):
    blank = View(key="", kind=VIEW_KIND_SHOT, label="", position=0)
    blank.id = None
    return request.app.state.templates.TemplateResponse(
        request,
        "views/form.html",
        {"active": "views", "view": blank, "kinds": list(VIEW_KINDS), **embed_context(request)},
    )


@router.post("/views", response_class=HTMLResponse)
async def views_create(request: Request):
    form = await request.form()
    key = (form.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "Key is required.")
    with session_scope() as s:
        if s.scalar(select(View.id).where(View.key == key)) is not None:
            raise HTTPException(400, f"Choose a different key — '{key}' is already in use.")
        v = View(key=key, kind=VIEW_KIND_SHOT, label=key, position=0)
        s.add(v)
        s.flush()
        _apply_view_form(v, form)
    bump_revision()
    return embed_redirect(request, f"/views/{key}", form=form)


@router.post("/views/{key:path}/delete", response_class=HTMLResponse)
def views_delete(key: str):
    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))
        if v is not None:
            s.delete(v)
    bump_revision()
    return RedirectResponse("/views", status_code=303)


@router.get("/views/{key:path}", response_class=HTMLResponse, name="views_edit")
def views_edit(request: Request, key: str):
    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))
        if v is None:
            if is_embed(request):
                return HTMLResponse(
                    '<p class="help">Camera view not found. '
                    "Gaze tags like <code>looking at viewer</code> belong on the act "
                    "<strong>Tags</strong> tab, not Views.</p>",
                    status_code=404,
                )
            raise HTTPException(404, "view not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "views/form.html",
        {"active": "views", "view": v, "kinds": list(VIEW_KINDS), **embed_context(request)},
    )


@router.post("/views/{key:path}", response_class=HTMLResponse)
async def views_update(request: Request, key: str):
    form = await request.form()
    new_key = (form.get("key") or "").strip() or key
    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))
        if v is None:
            raise HTTPException(404, "view not found")
        if new_key != key and s.scalar(select(View.id).where(View.key == new_key)) is not None:
            raise HTTPException(400, f"Choose a different key — '{new_key}' is already in use.")
        _apply_view_form(v, form)
    bump_revision()
    return embed_redirect(request, f"/views/{new_key}", form=form)


def _apply_view_form(v: View, form) -> None:
    v.key = (form.get("key") or v.key).strip()
    kind = (form.get("kind") or VIEW_KIND_SHOT).strip()
    v.kind = kind if kind in VIEW_KINDS else VIEW_KIND_SHOT
    v.label = (form.get("label") or v.key).strip()
    v.position = parse_int(form.get("position"))
    v.comment = (form.get("comment") or "").strip() or None
    v.framing_clause = (form.get("framing_clause") or "").strip() or None


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


@router.get("/locations", response_class=HTMLResponse, name="locations_list")
def locations_list(request: Request, q: str = Query("")):
    with session_scope() as s:
        query = select(DesignEntity).where(DesignEntity.entity_type == ENTITY_BACKGROUND).order_by(DesignEntity.slug)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(DesignEntity.slug.ilike(like))
        rows = s.scalars(query).all()
    return request.app.state.templates.TemplateResponse(
        request,
        "design/backgrounds_list.html",
        {"active": "locations", "rows": rows, "q": q},
    )


@router.get("/locations/new", response_class=HTMLResponse)
def locations_new(request: Request):
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
            "active": "locations",
            "loc": blank,
            "joined": joined,
            **embed_context(request),
        },
    )


@router.post("/locations", response_class=HTMLResponse)
async def locations_create(request: Request):
    form = await request.form()
    key = (form.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "Key is required.")
    with session_scope() as s:
        if s.scalar(
            select(DesignEntity.id).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        ) is not None:
            raise HTTPException(400, f"Choose a different key — '{key}' is already in use.")
        l = DesignEntity(slug=key, display_name=key, entity_type=ENTITY_BACKGROUND)
        s.add(l)
        s.flush()
        _apply_location_form(l, form)
    bump_revision()
    return embed_redirect(request, f"/locations/{key}", form=form)


@router.post("/locations/{key:path}/delete", response_class=HTMLResponse)
def locations_delete(key: str):
    with session_scope() as s:
        l = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if l is not None:
            clear_uploaded_image(l.image_path)
            s.delete(l)
    bump_revision()
    return RedirectResponse("/locations", status_code=303)


@router.get("/locations/{key:path}", response_class=HTMLResponse, name="locations_edit")
def locations_edit(request: Request, key: str):
    with session_scope() as s:
        l = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if l is None:
            raise HTTPException(404, "location not found")
    return request.app.state.templates.TemplateResponse(
        request,
        "design/background_form.html",
        {
            "active": "locations",
            "loc": l,
            "joined": joined,
            **embed_context(request),
        },
    )


@router.post("/locations/{key:path}", response_class=HTMLResponse)
async def locations_update(request: Request, key: str):
    form = await request.form()
    new_key = (form.get("key") or "").strip() or key
    with session_scope() as s:
        l = s.scalar(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == key,
            )
        )
        if l is None:
            raise HTTPException(404, "location not found")
        if new_key != key and s.scalar(
            select(DesignEntity.id).where(
                DesignEntity.entity_type == ENTITY_BACKGROUND,
                DesignEntity.slug == new_key,
            )
        ) is not None:
            raise HTTPException(400, f"Choose a different key — '{new_key}' is already in use.")
        _apply_location_form(l, form)
    bump_revision()
    return embed_redirect(request, f"/locations/{new_key}", form=form)


def _apply_location_form(l: DesignEntity, form) -> None:
    l.slug = (form.get("key") or l.slug).strip()
    l.display_name = l.slug
    l.scene_tags = parse_taglist(form.get("tags"))
    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(l.image_path)
        l.image_path = None
    else:
        upload = form.get("image")
        l.image_path = save_uploaded_image(
            upload, entity="locations", slug=l.key, existing=l.image_path
        )
