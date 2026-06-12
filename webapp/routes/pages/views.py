"""Taxonomy editors: views (camera framings).

Backgrounds live under ``/backgrounds`` (see ``routes.backgrounds``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from ...services.design.forms import parse_int
from ...db import VIEW_KINDS, VIEW_KIND_SHOT, View, session_scope
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
        {
            "active": "views",
            "grouped": grouped,
            "kinds": list(VIEW_KINDS),
            "kind": kind,
            **embed_context(request),
        },
    )


@router.get("/views/new", response_class=HTMLResponse)
def views_new(request: Request):
    blank = View(key="", kind=VIEW_KIND_SHOT, label="", position=0)
    blank.id = None
    return request.app.state.templates.TemplateResponse(
        request,
        "views/form.html",
        {
            "active": "views",
            "view": blank,
            "kinds": list(VIEW_KINDS),
            **embed_context(request),
        },
    )


@router.post("/views", response_class=HTMLResponse)
async def views_create(request: Request):
    form = await request.form()
    key = (form.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "Key is required.")
    with session_scope() as s:
        if s.scalar(select(View.id).where(View.key == key)) is not None:
            raise HTTPException(
                400, f"Choose a different key — '{key}' is already in use."
            )
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
        {
            "active": "views",
            "view": v,
            "kinds": list(VIEW_KINDS),
            **embed_context(request),
        },
    )


@router.post("/views/{key:path}", response_class=HTMLResponse)
async def views_update(request: Request, key: str):
    form = await request.form()
    new_key = (form.get("key") or "").strip() or key
    with session_scope() as s:
        v = s.scalar(select(View).where(View.key == key))
        if v is None:
            raise HTTPException(404, "view not found")
        if (
            new_key != key
            and s.scalar(select(View.id).where(View.key == new_key)) is not None
        ):
            raise HTTPException(
                400, f"Choose a different key — '{new_key}' is already in use."
            )
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
