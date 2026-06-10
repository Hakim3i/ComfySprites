"""Animation CRUD — SDXL tags, framings, orientation, ControlNet."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select

from ...db import Animation, View, session_scope
from ...db.models import (
    LORA_KIND_ANIMATION,
    LORA_KIND_ANIMATION_LTX,
    LORA_KIND_ANIMATION_WAN_HIGH,
    LORA_KIND_ANIMATION_WAN_LOW,
)
from ...revision import bump_revision
from ...services.design.animation_fields import (
    ANIMATION_SUBJECT_TYPE_LABELS,
    animation_orientations,
    animation_subject_type_options,
    normalize_animation_framings,
    normalize_animation_subject_type,
    parse_framings_form,
)
from ...services.catalog.controlnet_types import (
    all_controlnet_type_specs,
    controlnet_defaults_for_type,
    normalize_controlnets_map,
)
from ...services.design.forms import (
    apply_inline_lora,
    clear_uploaded_image,
    joined,
    lora_form_fields,
    parse_bool,
    parse_inline_lora_form,
    parse_taglist,
    save_uploaded_image,
)
from ...services.design.embed import embed_context, embed_redirect

router = APIRouter()


def _animation_lora_contexts(animation: Animation) -> dict[str, dict[str, str]]:
    return {
        "animation_lora": lora_form_fields(animation.lora),
        "animation_ltx_lora": lora_form_fields(animation.ltx_lora),
        "animation_wan_high_lora": lora_form_fields(animation.wan_high_lora),
        "animation_wan_low_lora": lora_form_fields(animation.wan_low_lora),
    }


def _views_grouped(s) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {
        "shot": [],
        "angle": [],
        "pov": [],
        "focus": [],
    }
    for v in s.scalars(select(View).order_by(View.kind, View.position, View.key)).all():
        out.setdefault(v.kind, []).append({"key": v.key, "label": v.label or v.key})
    return out


def _controlnet_form_context(animation: Animation) -> list[dict]:
    stored = normalize_controlnets_map(animation.controlnets or {})
    rows: list[dict] = []
    for spec in all_controlnet_type_specs():
        entry = stored.get(spec.key, {})
        defaults = controlnet_defaults_for_type(spec.key)
        rows.append(
            {
                "key": spec.key,
                "label": spec.label,
                "image_path": entry.get("image_path"),
                "strength": entry.get("strength", defaults["strength"]),
                "start_percent": entry.get("start_percent", defaults["start_percent"]),
                "end_percent": entry.get("end_percent", defaults["end_percent"]),
            }
        )
    return rows


@router.get("", response_class=HTMLResponse)
def animations_list(request: Request, q: str = Query("")):
    with session_scope() as s:
        query = select(Animation).order_by(Animation.slug)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(Animation.slug.ilike(like), Animation.menu_name.ilike(like))
            )
        rows = s.scalars(query).all()
        for row in rows:
            _ = row.lora
    return request.app.state.templates.TemplateResponse(
        request,
        "animations/list.html",
        {
            "active": "animations",
            "rows": rows,
            "q": q,
            "subject_type_labels": ANIMATION_SUBJECT_TYPE_LABELS,
            **embed_context(request),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def animations_new(request: Request):
    blank = Animation(
        slug="",
        menu_name="",
        tags=[],
        framings=[],
        orientation="portrait",
        subject_type="character",
        controlnets={},
    )
    blank.id = None
    with session_scope() as s:
        ctx = {"views_grouped": _views_grouped(s)}
    return request.app.state.templates.TemplateResponse(
        request,
        "animations/form.html",
        {
            "active": "animations",
            "animation": blank,
            "joined": joined,
            "orientation_options": animation_orientations(),
            "subject_type_options": animation_subject_type_options(),
            **_animation_lora_contexts(blank),
            "controlnet_types": _controlnet_form_context(blank),
            **ctx,
            **embed_context(request),
        },
    )


@router.post("", response_class=HTMLResponse)
async def animations_create(request: Request):
    form = await request.form()
    slug = (form.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "Slug is required.")
    with session_scope() as s:
        if s.scalar(select(Animation.id).where(Animation.slug == slug)) is not None:
            raise HTTPException(400, f"Slug '{slug}' is already in use.")
        animation = Animation(
            slug=slug, menu_name=slug, tags=[], framings=[], controlnets={}
        )
        s.add(animation)
        s.flush()
        _apply_form(s, animation, form)
    bump_revision()
    return embed_redirect(request, f"/animations/{slug}", form=form)


@router.get("/{slug}", response_class=HTMLResponse)
def animations_edit(request: Request, slug: str):
    with session_scope() as s:
        animation = s.scalar(select(Animation).where(Animation.slug == slug))
        if animation is None:
            raise HTTPException(404, "animation not found")
        _ = animation.lora
        ctx = {
            "views_grouped": _views_grouped(s),
            **_animation_lora_contexts(animation),
            "controlnet_types": _controlnet_form_context(animation),
        }
    return request.app.state.templates.TemplateResponse(
        request,
        "animations/form.html",
        {
            "active": "animations",
            "animation": animation,
            "joined": joined,
            "orientation_options": animation_orientations(),
            "subject_type_options": animation_subject_type_options(),
            **ctx,
            **embed_context(request),
        },
    )


@router.post("/{slug}", response_class=HTMLResponse)
async def animations_update(request: Request, slug: str):
    form = await request.form()
    with session_scope() as s:
        animation = s.scalar(select(Animation).where(Animation.slug == slug))
        if animation is None:
            raise HTTPException(404, "animation not found")
        new_slug = (form.get("slug") or slug).strip()
        if (
            new_slug != slug
            and s.scalar(select(Animation.id).where(Animation.slug == new_slug))
            is not None
        ):
            raise HTTPException(400, f"Slug '{new_slug}' is already in use.")
        _apply_form(s, animation, form)
        slug = animation.slug
    bump_revision()
    return embed_redirect(request, f"/animations/{slug}", form=form)


@router.post("/{slug}/delete", response_class=HTMLResponse)
def animations_delete(slug: str):
    with session_scope() as s:
        animation = s.scalar(select(Animation).where(Animation.slug == slug))
        if animation is not None:
            clear_uploaded_image(animation.image_path)
            for entry in (animation.controlnets or {}).values():
                if isinstance(entry, dict):
                    clear_uploaded_image(entry.get("image_path"))
            s.delete(animation)
    bump_revision()
    return RedirectResponse("/animations", status_code=303)


def _parse_float_form(form, key: str, default: float) -> float:
    raw = form.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _apply_controlnets_form(animation: Animation, form) -> None:
    current = normalize_controlnets_map(animation.controlnets or {})
    updated: dict[str, dict] = dict(current)

    for spec in all_controlnet_type_specs():
        key = spec.key
        clear_key = f"clear_controlnet_{key}"
        upload_key = f"controlnet_{key}_image"
        defaults = controlnet_defaults_for_type(key)

        if parse_bool(form.get(clear_key)):
            old = updated.pop(key, None)
            if isinstance(old, dict):
                clear_uploaded_image(old.get("image_path"))
            continue

        upload = form.get(upload_key)
        existing = updated.get(key, {})
        image_path = existing.get("image_path") if isinstance(existing, dict) else None

        if upload:
            image_path = save_uploaded_image(
                upload,
                entity=f"animations/controlnet/{key}",
                slug=animation.slug,
                existing=image_path,
            )

        if not image_path:
            updated.pop(key, None)
            continue

        had_entry = key in current
        strength = _parse_float_form(
            form,
            f"controlnet_{key}_strength",
            float(existing.get("strength", defaults["strength"]))
            if had_entry
            else defaults["strength"],
        )
        start_percent = _parse_float_form(
            form,
            f"controlnet_{key}_start",
            float(existing.get("start_percent", defaults["start_percent"]))
            if had_entry
            else defaults["start_percent"],
        )
        end_percent = _parse_float_form(
            form,
            f"controlnet_{key}_end",
            float(existing.get("end_percent", defaults["end_percent"]))
            if had_entry
            else defaults["end_percent"],
        )
        updated[key] = {
            "image_path": image_path,
            "strength": strength,
            "start_percent": start_percent,
            "end_percent": end_percent,
        }

    animation.controlnets = normalize_controlnets_map(updated)


def _apply_form(session, animation: Animation, form) -> None:
    animation.slug = (form.get("slug") or animation.slug).strip()
    animation.menu_name = (form.get("menu_name") or animation.slug).strip()
    animation.comment = (form.get("comment") or "").strip() or None
    animation.tags = parse_taglist(form.get("tags"))
    animation.framings = normalize_animation_framings(
        session, parse_framings_form(form)
    )
    orient = (form.get("orientation") or "portrait").strip().lower()
    animation.orientation = (
        orient if orient in ("portrait", "landscape", "both") else "portrait"
    )
    animation.subject_type = normalize_animation_subject_type(form.get("subject_type"))
    if form.get("image"):
        animation.image_path = save_uploaded_image(
            form.get("image"),
            entity="animations",
            slug=animation.slug,
            existing=animation.image_path,
        )
    lora_fields = parse_inline_lora_form(form, "lora_")
    animation.lora_id = apply_inline_lora(
        session,
        kind=LORA_KIND_ANIMATION,
        existing_id=animation.lora_id,
        **lora_fields,
    )
    ltx_fields = parse_inline_lora_form(form, "lora_ltx_")
    animation.ltx_lora_id = apply_inline_lora(
        session,
        kind=LORA_KIND_ANIMATION_LTX,
        existing_id=animation.ltx_lora_id,
        **ltx_fields,
    )
    wan_high_fields = parse_inline_lora_form(form, "lora_wan_high_")
    animation.wan_high_lora_id = apply_inline_lora(
        session,
        kind=LORA_KIND_ANIMATION_WAN_HIGH,
        existing_id=animation.wan_high_lora_id,
        **wan_high_fields,
    )
    wan_low_fields = parse_inline_lora_form(form, "lora_wan_low_")
    animation.wan_low_lora_id = apply_inline_lora(
        session,
        kind=LORA_KIND_ANIMATION_WAN_LOW,
        existing_id=animation.wan_low_lora_id,
        **wan_low_fields,
    )
    _apply_controlnets_form(animation, form)
