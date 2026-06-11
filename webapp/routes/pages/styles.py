"""Style CRUD with inline checkpoint identity + sampling + LoRA + image upload.

A *style* is everything needed to render: model file + sampler settings +
prompt templates + an optional inline LoRA. There is no separate
``Checkpoint`` entity; if two styles want the same base model file with
different LoRAs, they're two style rows that happen to share a
``filename`` value (intentional duplication).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...services.design.forms import (
    apply_inline_lora,
    clear_uploaded_image,
    parse_bool,
    parse_inline_lora_form,
    parse_int,
    parse_optional_float,
    save_uploaded_image,
)
from ...db import LORA_KIND_STYLE, Style, session_scope
from ...revision import bump_revision
from ...services.catalog.style_defaults import (
    base_model_options,
    new_style_defaults,
    normalize_sampler,
    normalize_scheduler,
    sampler_hints,
    scheduler_hints,
)

router = APIRouter()


def _form_context() -> dict[str, tuple[str, ...]]:
    return {
        "base_model_options": base_model_options(),
        "sampler_hints": sampler_hints(),
        "scheduler_hints": scheduler_hints(),
    }


def _style_lora_context(st: Style) -> dict[str, str]:
    from ...services.design.forms import lora_form_fields

    return lora_form_fields(st.lora)


@router.get("", response_class=HTMLResponse)
def styles_list(request: Request):
    with session_scope() as s:
        rows = s.scalars(select(Style).order_by(Style.slug)).all()
        for r in rows:
            _ = r.lora
    return request.app.state.templates.TemplateResponse(
        request, "styles/list.html", {"active": "styles", "rows": rows}
    )


@router.get("/new", response_class=HTMLResponse)
def styles_new(request: Request):
    ns = new_style_defaults()
    blank = Style(
        slug="",
        display_name="",
        filename="",
        base_model=ns.base_model,
        sampler=ns.sampler,
        scheduler=ns.scheduler,
        steps=ns.steps,
        cfg_scale=ns.cfg_scale,
        clip_skip=ns.clip_skip,
        width=ns.width,
        height=ns.height,
        prefix="",
        negative="",
    )
    blank.id = None
    return request.app.state.templates.TemplateResponse(
        request,
        "styles/form.html",
        {
            "active": "styles",
            "style": blank,
            "style_lora": _style_lora_context(blank),
            **_form_context(),
        },
    )


@router.post("", response_class=HTMLResponse)
async def styles_create(request: Request):
    form = await request.form()
    slug = (form.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "Slug is required.")
    with session_scope() as s:
        if s.scalar(select(Style.id).where(Style.slug == slug)) is not None:
            raise HTTPException(
                400, f"Choose a different slug — '{slug}' is already in use."
            )
        st = Style(slug=slug, display_name=slug)
        s.add(st)
        s.flush()
        _apply_style_form(s, st, form)
    bump_revision()
    return RedirectResponse(f"/styles/{slug}", status_code=303)


@router.get("/{slug}", response_class=HTMLResponse)
def styles_edit(request: Request, slug: str):
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        _ = st.lora
        ctx = _style_lora_context(st)
    return request.app.state.templates.TemplateResponse(
        request,
        "styles/form.html",
        {
            "active": "styles",
            "style": st,
            "style_lora": ctx,
            **_form_context(),
        },
    )


@router.post("/{slug}", response_class=HTMLResponse)
async def styles_update(request: Request, slug: str):
    form = await request.form()
    new_slug = (form.get("slug") or "").strip() or slug
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        if (
            new_slug != slug
            and s.scalar(select(Style.id).where(Style.slug == new_slug)) is not None
        ):
            raise HTTPException(
                400, f"Choose a different slug — '{new_slug}' is already in use."
            )
        _apply_style_form(s, st, form)
    bump_revision()
    return RedirectResponse(f"/styles/{new_slug}", status_code=303)


@router.post("/{slug}/delete", response_class=HTMLResponse)
def styles_delete(slug: str):
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is not None:
            clear_uploaded_image(st.image_path)
            s.delete(st)
    bump_revision()
    return RedirectResponse("/styles", status_code=303)


def _apply_style_form(s, st: Style, form) -> None:
    ns = new_style_defaults()
    st.slug = (form.get("slug") or st.slug).strip()
    st.display_name = (form.get("name") or st.slug).strip()

    # Checkpoint identity
    st.filename = (form.get("filename") or "").strip()
    st.base_model = (
        form.get("base_model") or ns.base_model
    ).strip().lower() or ns.base_model
    st.civitai_url = (form.get("civitai_url") or "").strip() or None
    st.download_url = (form.get("download_url") or "").strip() or None
    st.model_id = parse_int(form.get("model_id"), 0) or None
    st.version_id = parse_int(form.get("version_id"), 0) or None

    # Sampling settings
    try:
        st.sampler = normalize_sampler((form.get("sampler") or ns.sampler).strip())
        st.scheduler = normalize_scheduler(
            (form.get("scheduler") or ns.scheduler).strip()
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    st.steps = parse_int(form.get("steps"), st.steps or ns.steps)
    cfg = parse_optional_float(form.get("cfg_scale"))
    st.cfg_scale = cfg if cfg is not None else (st.cfg_scale or ns.cfg_scale)
    st.clip_skip = parse_int(
        form.get("clip_skip"),
        st.clip_skip if st.clip_skip is not None else ns.clip_skip,
    )
    st.width = parse_int(form.get("width"), st.width or ns.width)
    st.height = parse_int(form.get("height"), st.height or ns.height)
    st.denoise_strength = parse_optional_float(form.get("denoise_strength"))

    # Prompt templates + display
    st.prefix = (form.get("prefix") or "").strip()
    st.negative = (form.get("negative") or "").strip()
    st.video_register = (form.get("video_register") or "").strip() or None
    st.ltx_video_negative = (form.get("ltx_video_negative") or "").strip() or None
    st.ltx_audio_negative = (form.get("ltx_audio_negative") or "").strip() or None
    st.wan_negative = (form.get("wan_negative") or "").strip() or None
    st.comment = (form.get("comment") or "").strip() or None

    # Inline LoRA
    lora_fields = parse_inline_lora_form(form, "lora_")
    st.lora_id = apply_inline_lora(
        s,
        kind=LORA_KIND_STYLE,
        existing_id=st.lora_id,
        **lora_fields,
    )

    # Image upload
    if parse_bool(form.get("clear_image")):
        clear_uploaded_image(st.image_path)
        st.image_path = None
    else:
        upload = form.get("image")
        st.image_path = save_uploaded_image(
            upload, entity="styles", slug=st.slug, existing=st.image_path
        )
