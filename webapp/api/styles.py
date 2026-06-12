"""Style CRUD and reference images."""

from __future__ import annotations

from typing import Any

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from ..services.design.forms import clear_uploaded_image
from ..services.catalog.style_defaults import (
    new_style_defaults,
    normalize_sampler,
    normalize_scheduler,
)
from ..db import Style, session_scope
from ..db.models import (
    LORA_KIND_STYLE,
    LORA_KIND_STYLE_LTX,
    LORA_KIND_STYLE_WAN_HIGH,
    LORA_KIND_STYLE_WAN_LOW,
)
from ..revision import bump_revision
from .images import attach_upload_image
from .lora import apply_lora_payload, has_field
from .router import router
from .schemas import StyleIn
from .serializers import style_to_dict


def _apply_style_payload(session, st: Style, payload: StyleIn) -> None:
    ns = new_style_defaults()
    st.slug = payload.slug
    st.display_name = payload.name or payload.slug
    st.filename = payload.filename or ""
    st.base_model = (payload.base_model or ns.base_model).lower()
    st.civitai_url = payload.civitai_url
    st.model_id = payload.model_id
    st.version_id = payload.version_id
    st.download_url = payload.download_url
    st.sampler = normalize_sampler(payload.sampler or ns.sampler)
    st.scheduler = normalize_scheduler(payload.scheduler or ns.scheduler)
    st.steps = int(payload.steps) if payload.steps is not None else ns.steps
    st.cfg_scale = (
        float(payload.cfg_scale) if payload.cfg_scale is not None else ns.cfg_scale
    )
    st.clip_skip = (
        int(payload.clip_skip) if payload.clip_skip is not None else ns.clip_skip
    )
    st.width = int(payload.width) if payload.width is not None else ns.width
    st.height = int(payload.height) if payload.height is not None else ns.height
    st.denoise_strength = (
        float(payload.denoise_strength)
        if payload.denoise_strength is not None
        else None
    )
    st.prefix = payload.prefix or ""
    st.negative = payload.negative or ""
    st.video_register = (payload.video_register or "").strip() or None
    st.ltx_video_negative = (payload.ltx_video_negative or "").strip() or None
    st.ltx_audio_negative = (payload.ltx_audio_negative or "").strip() or None
    st.wan_negative = (payload.wan_negative or "").strip() or None
    st.comment = payload.comment
    if has_field(payload, "lora"):
        st.lora_id = apply_lora_payload(
            session, LORA_KIND_STYLE, payload.lora, st.lora_id
        )
    if has_field(payload, "ltx_lora"):
        st.ltx_lora_id = apply_lora_payload(
            session, LORA_KIND_STYLE_LTX, payload.ltx_lora, st.ltx_lora_id
        )
    if has_field(payload, "wan_high_lora"):
        st.wan_high_lora_id = apply_lora_payload(
            session,
            LORA_KIND_STYLE_WAN_HIGH,
            payload.wan_high_lora,
            st.wan_high_lora_id,
        )
    if has_field(payload, "wan_low_lora"):
        st.wan_low_lora_id = apply_lora_payload(
            session,
            LORA_KIND_STYLE_WAN_LOW,
            payload.wan_low_lora,
            st.wan_low_lora_id,
        )


def _touch_style_loras(st: Style) -> None:
    _ = (
        st.lora,
        st.ltx_lora,
        st.wan_high_lora,
        st.wan_low_lora,
    )


@router.get("/styles")
def api_styles_list() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.scalars(select(Style).order_by(Style.slug)).all()
        for st in rows:
            _touch_style_loras(st)
        return [style_to_dict(r) for r in rows]


@router.post("/styles", status_code=201)
def api_styles_create(payload: StyleIn) -> dict[str, Any]:
    with session_scope() as s:
        if s.scalar(select(Style.id).where(Style.slug == payload.slug)) is not None:
            raise HTTPException(409, f"slug {payload.slug!r} already in use")
        st = Style(slug=payload.slug, display_name=payload.slug)
        s.add(st)
        s.flush()
        _apply_style_payload(s, st, payload)
        s.flush()
        _touch_style_loras(st)
        out = style_to_dict(st)
    bump_revision()
    return out


@router.get("/styles/{slug}")
def api_styles_get(slug: str) -> dict[str, Any]:
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        _touch_style_loras(st)
        return style_to_dict(st)


@router.put("/styles/{slug}")
def api_styles_update(slug: str, payload: StyleIn) -> dict[str, Any]:
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        if payload.slug != slug:
            if (
                s.scalar(
                    select(Style.id).where(
                        Style.slug == payload.slug, Style.id != st.id
                    )
                )
                is not None
            ):
                raise HTTPException(409, f"slug {payload.slug!r} already in use")
        _apply_style_payload(s, st, payload)
        s.flush()
        _touch_style_loras(st)
        out = style_to_dict(st)
    bump_revision()
    return out


@router.delete("/styles/{slug}", status_code=204)
def api_styles_delete(slug: str) -> Response:
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        clear_uploaded_image(st.image_path)
        s.delete(st)
    bump_revision()
    return Response(status_code=204)


@router.post("/styles/{slug}/image")
async def api_styles_image(slug: str, file: UploadFile = File(...)) -> dict[str, Any]:
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        attach_upload_image(st, file=file, entity_dir="styles", slug=st.slug)
        out = {"slug": st.slug, "image_path": st.image_path}
    bump_revision()
    return out


@router.delete("/styles/{slug}/image", status_code=204)
def api_styles_image_delete(slug: str) -> Response:
    with session_scope() as s:
        st = s.scalar(select(Style).where(Style.slug == slug))
        if st is None:
            raise HTTPException(404, "style not found")
        clear_uploaded_image(st.image_path)
        st.image_path = None
    bump_revision()
    return Response(status_code=204)
