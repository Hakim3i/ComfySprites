"""Build LTX prompt block from a Make Lab source generation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ...db.models import Animation, DesignEntity, EditGeneration, Generation, Style
from .render import render_ltx_block, render_wan_block
from .text import parse_ltx_negative_blocks


def _scene_dict(build: dict[str, Any]) -> dict[str, Any]:
    scene = build.get("scene")
    return scene if isinstance(scene, dict) else {}


def _load_style(session: Session, slug: str | None) -> Style | None:
    if not slug:
        return None
    return session.scalar(
        select(Style)
        .where(Style.slug == slug)
        .options(
            joinedload(Style.lora),
            joinedload(Style.ltx_lora),
            joinedload(Style.wan_high_lora),
            joinedload(Style.wan_low_lora),
        )
    )


def _load_entity(session: Session, slug: str | None) -> DesignEntity | None:
    if not slug:
        return None
    return session.scalar(
        select(DesignEntity)
        .where(DesignEntity.slug == slug)
        .options(joinedload(DesignEntity.lora))
    )


def _load_animation(session: Session, slug: str | None) -> Animation | None:
    if not slug:
        return None
    return session.scalar(
        select(Animation)
        .where(Animation.slug == slug)
        .options(
            joinedload(Animation.lora),
            joinedload(Animation.ltx_lora),
            joinedload(Animation.wan_high_lora),
            joinedload(Animation.wan_low_lora),
        )
    )


def _build_ltx_from_scene_build(
    session: Session,
    build: dict[str, Any],
    *,
    style_slug: str | None = None,
    animation_slug: str | None = None,
    fallback_animation_slug: str | None = None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    scene = _scene_dict(build)
    style_key = (style_slug or "").strip() or scene.get("style")
    style = _load_style(session, style_key)
    character = _load_entity(session, scene.get("character"))
    location = _load_entity(session, scene.get("location"))
    anim_slug = (
        (animation_slug or "").strip()
        or (fallback_animation_slug or "").strip()
        or scene.get("animation")
        or None
    )
    animation = _load_animation(session, anim_slug)

    ltx = render_ltx_block(
        style=style,
        character=character,
        location=location,
        animation=animation,
        lora_strengths=lora_strengths,
    )
    wan = render_wan_block(
        style=style,
        character=character,
        location=location,
        animation=animation,
        lora_strengths=lora_strengths,
    )
    out = dict(build)
    out["ltx"] = ltx
    out["wan"] = wan
    out["scene"] = {
        **scene,
        "style": style.slug if style else scene.get("style"),
        "character": character.slug if character else scene.get("character"),
        "location": location.slug if location else scene.get("location"),
        "animation": animation.slug if animation else anim_slug,
    }
    sdxl = out.get("sdxl") if isinstance(out.get("sdxl"), dict) else {}
    out["sdxl"] = sdxl
    return out


def build_ltx_from_generation(
    session: Session,
    source: Generation,
    *,
    style_slug: str | None = None,
    animation_slug: str | None = None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    return _build_ltx_from_scene_build(
        session,
        dict(source.build_json or {}),
        style_slug=style_slug,
        animation_slug=animation_slug,
        lora_strengths=lora_strengths,
    )


def build_ltx_from_edit(
    session: Session,
    source: EditGeneration,
    *,
    style_slug: str | None = None,
    animation_slug: str | None = None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    return _build_ltx_from_scene_build(
        session,
        dict(source.build_json or {}),
        style_slug=style_slug,
        animation_slug=animation_slug,
        fallback_animation_slug=source.animation_slug,
        lora_strengths=lora_strengths,
    )


def resolve_ltx_fields(
    build: dict[str, Any],
    *,
    ltx_caption: str | None = None,
    ltx_video_negative: str | None = None,
    ltx_audio_negative: str | None = None,
) -> dict[str, str | None]:
    ltx = build.get("ltx") if isinstance(build.get("ltx"), dict) else {}
    caption_override = (ltx_caption or "").strip()
    vid_override = (ltx_video_negative or "").strip()
    aud_override = (ltx_audio_negative or "").strip()

    caption = caption_override or str(ltx.get("caption") or ltx.get("positive") or "").strip() or None

    video = vid_override
    audio = aud_override
    if not video and not audio:
        neg = str(ltx.get("negative") or "").strip()
        if neg:
            video, audio = parse_ltx_negative_blocks(neg)
        else:
            segs = ltx.get("negative_segments")
            if isinstance(segs, list):
                for seg in segs:
                    if not isinstance(seg, dict):
                        continue
                    src = str(seg.get("source") or "")
                    text = str(seg.get("text") or "").strip()
                    if not text:
                        continue
                    if src == "style_ltx_video" and not video:
                        video = text
                    elif src == "style_ltx_audio" and not audio:
                        audio = text

    return {
        "ltx_caption": caption,
        "ltx_video_negative": video or None,
        "ltx_audio_negative": audio or None,
    }


def resolve_wan_fields(
    build: dict[str, Any],
    *,
    positive_override: str | None = None,
) -> dict[str, str | None]:
    wan = build.get("wan") if isinstance(build.get("wan"), dict) else {}
    override = (positive_override or "").strip()
    positive = override or str(wan.get("positive") or "").strip() or None
    negative = str(wan.get("negative") or "").strip() or None
    return {
        "positive": positive,
        "negative": negative,
        "ltx_caption": positive,
    }
