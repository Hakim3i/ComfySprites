"""ORM rows → JSON dicts for API responses."""

from __future__ import annotations


from typing import Any


from ..services.design import attributes as char_attrs

from ..db.models import Animation, DesignEntity, Lora, Style, View

from ..services.catalog.controlnet_types import normalize_controlnets_map


def lora_summary(lora: Lora | None) -> dict[str, Any] | None:

    if lora is None:
        return None

    return {
        "id": lora.id,
        "kind": lora.kind,
        "filename": lora.filename,
        "name": lora.name,
        "trigger": lora.trigger,
        "caption_trigger": lora.caption_trigger,
        "strength": lora.strength,
        "url": lora.url,
        "download_url": lora.download_url,
        "download_fallback_url": lora.download_fallback_url,
        "model_id": lora.model_id,
        "version_id": lora.version_id,
        "comment": lora.comment,
    }


def design_entity_to_dict(c: DesignEntity) -> dict[str, Any]:
    """Monster, object, or other non-character design entity."""

    return {
        "id": c.id,
        "slug": c.slug,
        "display_name": c.display_name,
        "name_tag": c.name_tag,
        "entity_type": c.entity_type,
        "comment": c.comment,
        "image_path": c.image_path,
        "identity_core": char_attrs.identity_core_tags(c),
        "lora": lora_summary(c.character_lora),
    }


def character_to_dict(c: DesignEntity) -> dict[str, Any]:

    structured = {a.key: getattr(c, a.key) for a in char_attrs.ATTRIBUTES}

    for a in char_attrs.ATTRIBUTES:
        if a.multi:
            structured[a.key] = list(structured[a.key] or [])

    return {
        "id": c.id,
        "slug": c.slug,
        "display_name": c.display_name,
        "name_tag": c.name_tag,
        "comment": c.comment,
        "image_path": c.image_path,
        "identity_core": char_attrs.identity_core_tags(c),
        "outfit_head": list(c.outfit_head or []),
        "outfit_upper": list(c.outfit_upper or []),
        "outfit_lower": list(c.outfit_lower or []),
        "outfit_extra": list(c.outfit_extra or []),
        "lora": lora_summary(c.character_lora),
        "video_prompt": c.video_prompt,
        **structured,
    }


def animation_to_dict(a: Animation) -> dict[str, Any]:

    sdxl_lora = lora_summary(a.lora)

    return {
        "id": a.id,
        "slug": a.slug,
        "menu_name": a.menu_name,
        "subject_type": a.subject_type or "character",
        "comment": a.comment,
        "image_path": a.image_path,
        "controlnets": normalize_controlnets_map(a.controlnets or {}),
        "tags": list(a.tags or []),
        "framings": list(a.framings or []),
        "orientation": a.orientation,
        "lora": sdxl_lora,
        "sdxl_lora": sdxl_lora,
        "ltx_lora": lora_summary(a.ltx_lora),
        "wan_high_lora": lora_summary(a.wan_high_lora),
        "wan_low_lora": lora_summary(a.wan_low_lora),
        "qwen_edit_lora": lora_summary(a.qwen_edit_lora),
        "qwen_edit_prompt": a.qwen_edit_prompt,
        "video_prompt": a.video_prompt,
    }



def view_to_dict(v: View) -> dict[str, Any]:

    return {
        "id": v.id,
        "key": v.key,
        "kind": v.kind,
        "label": v.label,
        "position": v.position,
        "comment": v.comment,
        "framing_clause": v.framing_clause,
    }


def style_to_dict(s: Style) -> dict[str, Any]:

    from ..services.catalog.style_defaults import new_style_defaults

    ns = new_style_defaults()

    return {
        "id": s.id,
        "slug": s.slug,
        "name": s.name,
        "filename": s.filename or "",
        "base_model": s.base_model or ns.base_model,
        "civitai_url": s.civitai_url,
        "model_id": s.model_id,
        "version_id": s.version_id,
        "download_url": s.download_url,
        "sampler": s.sampler or ns.sampler,
        "scheduler": s.scheduler,
        "steps": s.steps if s.steps is not None else ns.steps,
        "cfg_scale": s.cfg_scale if s.cfg_scale is not None else ns.cfg_scale,
        "clip_skip": s.clip_skip if s.clip_skip is not None else ns.clip_skip,
        "width": s.width if s.width is not None else ns.width,
        "height": s.height if s.height is not None else ns.height,
        "denoise_strength": s.denoise_strength,
        "prefix": s.prefix or "",
        "negative": s.negative or "",
        "video_register": s.video_register,
        "ltx_video_negative": s.ltx_video_negative,
        "ltx_audio_negative": s.ltx_audio_negative,
        "wan_negative": s.wan_negative,
        "comment": s.comment,
        "image_path": s.image_path,
        "lora": lora_summary(s.lora),
        "sdxl_lora": lora_summary(s.lora),
        "ltx_lora": lora_summary(s.ltx_lora),
        "wan_high_lora": lora_summary(s.wan_high_lora),
        "wan_low_lora": lora_summary(s.wan_low_lora),
    }


def background_to_dict(bg: DesignEntity) -> dict[str, Any]:
    return {
        "id": bg.id,
        "key": bg.key,
        "display_name": bg.display_name or bg.key,
        "tags": list(bg.tags or []),
        "video_prompt": bg.video_prompt,
        "image_path": bg.image_path,
    }
