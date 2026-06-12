"""Compose LTX natural-language captions from catalog rows."""

from __future__ import annotations

from typing import Any

from ...db.models import Animation, DesignEntity, Lora, Style
from .fragments import (
    character_segment_text,
    location_fragment,
    scene_opener_text,
    style_register_fragment,
)
from .text import format_cue, format_ltx_negative, sanitize_positive


def _lora_dict(lora: Lora | None, *, role: str | None = None) -> dict[str, Any] | None:
    if lora is None or not (lora.filename or "").strip():
        return None
    return {
        "id": lora.id,
        "kind": role or lora.kind,
        "filename": lora.filename,
        "name": lora.name,
        "trigger": lora.trigger,
        "caption_trigger": lora.caption_trigger,
        "strength": float(lora.strength or 1.0),
    }


VIDEO_LORA_ROLES = ("ltx", "wan_high", "wan_low")
_VIDEO_LORA_ROLE_SET = frozenset(VIDEO_LORA_ROLES)


def is_animate_video_lora_kind(kind: str | None) -> bool:
    """True for motion LoRA slots used by Animate (never SDXL / still-image LoRAs)."""
    key = str(kind or "").strip().lower()
    if not key:
        return False
    if key in _VIDEO_LORA_ROLE_SET:
        return True
    for prefix in ("style_", "animation_"):
        if key.startswith(prefix):
            return key[len(prefix) :] in _VIDEO_LORA_ROLE_SET
    return False

_VIDEO_LORA_ATTR = {
    "ltx": "ltx_lora",
    "wan_high": "wan_high_lora",
    "wan_low": "wan_low_lora",
}


def _video_lora_on(obj: Style | Animation | None, role: str) -> Lora | None:
    attr = _VIDEO_LORA_ATTR.get(role)
    if not attr or obj is None:
        return None
    lora = getattr(obj, attr, None)
    if lora is not None and (lora.filename or "").strip():
        return lora
    return None


def resolve_style_video_lora(style: Style | None, role: str) -> Lora | None:
    return _video_lora_on(style, role)


def resolve_animation_video_lora(animation: Animation | None, role: str) -> Lora | None:
    return _video_lora_on(animation, role)


def resolve_animate_lora(
    style: Style | None,
    animation: Animation | None,
    role: str,
) -> Lora | None:
    """Legacy helper — style video LoRA wins; animation is the fallback."""
    hit = resolve_style_video_lora(style, role)
    if hit is not None:
        return hit
    return resolve_animation_video_lora(animation, role)


def weave_animation_trigger(animation_text: str, lora: Lora | None) -> str:
    motion = sanitize_positive(animation_text or "").strip().rstrip(".")
    trigger = sanitize_positive((lora.caption_trigger if lora else "") or "").strip().rstrip(".")
    if trigger and motion:
        if trigger.lower() in motion.lower():
            return format_cue(motion)
        return format_cue(f"{trigger}. {motion}")
    if trigger:
        return format_cue(trigger)
    if motion:
        return format_cue(motion)
    return ""


def render_ltx_caption(
    *,
    style: Style | None,
    character: DesignEntity | None,
    location: DesignEntity | None,
    animation: Animation | None,
) -> str:
    segments: list[str] = []

    if style and (style.video_register or "").strip():
        reg = style_register_fragment(style.video_register or "")
        if reg:
            segments.append(reg)

    char_text = ""
    if character:
        char_text = character_segment_text(
            character.display_name or character.slug,
            character.video_prompt or "",
        )
    loc_text = ""
    if location and (location.video_prompt or "").strip():
        loc_text = location_fragment(location.video_prompt or "")
    scene = scene_opener_text(char_text, loc_text)
    if scene:
        segments.append(f"Video of {scene}")

    if animation:
        anim_clause = weave_animation_trigger(
            animation.video_prompt or "",
            resolve_animation_video_lora(animation, "ltx"),
        )
        if anim_clause:
            segments.append(anim_clause)

    return " ".join(segments).strip()


def render_ltx_negative_segments(
    *,
    style: Style | None,
) -> list[dict[str, str]]:
    segs: list[dict[str, str]] = []
    if style and (style.ltx_video_negative or "").strip():
        segs.append({
            "source": "style_ltx_video",
            "text": style.ltx_video_negative.strip(),
        })
    if style and (style.ltx_audio_negative or "").strip():
        segs.append({
            "source": "style_ltx_audio",
            "text": style.ltx_audio_negative.strip(),
        })
    return segs


def render_ltx_negative(*, style: Style | None) -> str:
    return format_ltx_negative(render_ltx_negative_segments(style=style))


def render_ltx_block(
    *,
    style: Style | None,
    character: DesignEntity | None,
    location: DesignEntity | None,
    animation: Animation | None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    caption = render_ltx_caption(
        style=style,
        character=character,
        location=location,
        animation=animation,
    )
    neg_segments = render_ltx_negative_segments(style=style)
    negative = format_ltx_negative(neg_segments)
    loras: list[dict[str, Any]] = []
    for role in VIDEO_LORA_ROLES:
        for slot, lora in (
            (f"style_{role}", resolve_style_video_lora(style, role)),
            (f"animation_{role}", resolve_animation_video_lora(animation, role)),
        ):
            entry = _lora_dict(lora, role=slot)
            if not entry:
                continue
            strength = (lora_strengths or {}).get(slot)
            if strength is None:
                strength = (lora_strengths or {}).get(role)
            if strength is not None:
                entry["strength"] = float(strength)
            loras.append(entry)
    return {
        "caption": caption,
        "positive": caption,
        "negative": negative,
        "negative_segments": neg_segments,
        "loras": loras,
    }
