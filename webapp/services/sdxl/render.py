from __future__ import annotations

from typing import Any, Iterable

from ..design import animation_fields
from ..design import attributes as char_attrs
from ..design.outfit import outfit_zone_segments
from ...db.models import ENTITY_CHARACTER, Animation, DesignEntity, Lora, Style
from .payload import BuildPayload, Scene

def _flatten_unique(groups: Iterable[Iterable[str]]) -> list[str]:
    """Concatenate tag groups preserving order, deduplicate case-insensitively."""
    out: list[str] = []
    seen: set[str] = set()
    for grp in groups:
        for raw in grp or ():
            tag = (raw or "").strip()
            if not tag:
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tag)
    return out


def _csv_split(s: str | None) -> list[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _character_adetailer_field_tags(
    character: DesignEntity,
    field_keys: tuple[str, ...],
    *,
    multi_keys: tuple[str, ...] = (),
) -> list[str]:
    from ..design.forms import parse_taglist

    tags: list[str] = []
    for key in field_keys:
        raw = getattr(character, key, None)
        if not raw:
            continue
        if key in multi_keys:
            tags.extend(char_attrs.parse_multi(raw))
        else:
            tags.extend(parse_taglist(str(raw)))
    return _flatten_unique([tags])


def _character_adetailer_payload(character: DesignEntity | None) -> dict[str, str]:
    """Per-region tag strings for Make Lab FaceDetailer prompts."""
    from ..design.forms import parse_taglist

    empty = {
        "face": "",
        "eyes": "",
        "hands": "",
        "feet": "",
        "penis": "",
        "pussy": "",
        "breasts": "",
        "anus": "",
    }
    if character is None:
        return dict(empty)

    face_tags = _character_adetailer_field_tags(
        character,
        ("eye_color", "eye_shape", "glasses", "makeup", "skin_tone"),
        multi_keys=("facial_marks",),
    )
    eye_tags = _character_adetailer_field_tags(
        character,
        ("eye_color", "eye_shape", "glasses"),
    )

    breast_tags: list[str] = []
    raw_breast = getattr(character, "breast_size", None)
    if raw_breast:
        breast_tags.extend(parse_taglist(str(raw_breast)))

    def _join(tags: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for raw in tags:
            tag = (raw or "").strip()
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                out.append(tag)
        return ", ".join(out)

    return {
        "face": _join(face_tags),
        "eyes": _join(eye_tags),
        "hands": "hands",
        "feet": "feet",
        "penis": "",
        "pussy": "",
        "breasts": _join(breast_tags),
        "anus": "",
    }


def _character_region_tags(c: DesignEntity | None) -> dict[str, list[str]]:
    """Return the four identity regions for a character, with structured
    detail fields merged in (eye_color, hair_style, etc.)."""
    if c is None:
        empty = {
            char_attrs.REGION_CORE: [],
            char_attrs.REGION_HEAD: [],
            char_attrs.REGION_UPPER: [],
            char_attrs.REGION_LOWER: [],
        }
        return empty
    return char_attrs.merge_into_region_lists(c)


def _style_checkpoint_payload(style: Style) -> dict[str, Any]:
    """Checkpoint file + sampler metadata for the build response."""
    return {
        "filename": style.filename,
        "name": style.name,
        "sampler": style.sampler,
        "scheduler": style.scheduler,
        "steps": int(style.steps or 25),
        "cfg_scale": float(style.cfg_scale or 5.0),
        "clip_skip": int(style.clip_skip or 2),
        "download_url": style.download_url,
        "download_fallback_url": style.download_fallback_url,
        "version_id": style.version_id,
        "model_id": style.model_id,
        "civitai_url": style.civitai_url,
    }


def _lora_strength_value(strength: float | None) -> float:
    """Resolve DB strength; ``None`` defaults to 1.0 (``0`` stays ``0``)."""
    if strength is None:
        return 1.0
    return float(strength)


def _prune_zero_strength_loras(loras: list[Any]) -> None:
    """Drop build LoRA rows whose effective strength is exactly 0."""
    kept: list[Any] = []
    for item in loras:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if _lora_strength_value(item.get("strength")) != 0.0:
            kept.append(item)
    loras[:] = kept


def _apply_lora_strength_overrides(
    build_result: dict[str, Any],
    overrides: dict[str, float] | None,
) -> None:
    """Apply Make spin-box strengths to build LoRA lists (saved or session)."""
    if not overrides:
        return
    for block_key in ("sdxl", "refine_sdxl"):
        block = build_result.get(block_key)
        if not isinstance(block, dict):
            continue
        loras = block.get("loras")
        if not isinstance(loras, list):
            continue
        for item in loras:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            if (
                block_key == "refine_sdxl"
                and kind == "style"
                and "refine_style" in overrides
            ):
                item["strength"] = float(overrides["refine_style"])
            elif kind in overrides and kind != "refine_style":
                item["strength"] = float(overrides[kind])
        _prune_zero_strength_loras(loras)


def _prune_zero_strength_loras_in_build(build_result: dict[str, Any]) -> None:
    """Remove strength-0 LoRAs from inference + refine lists (after overrides)."""
    for block_key in ("sdxl", "refine_sdxl"):
        block = build_result.get(block_key)
        if isinstance(block, dict) and isinstance(block.get("loras"), list):
            _prune_zero_strength_loras(block["loras"])


def _lora_to_payload(lora: Lora | None, *, kind: str) -> dict[str, Any] | None:
    """Serialize a linked LoRA row for the build response."""
    if lora is None or not (lora.filename or "").strip():
        return None
    strength = _lora_strength_value(lora.strength)
    out: dict[str, Any] = {
        "id": lora.id,
        "kind": kind,
        "filename": lora.filename,
        "strength": strength,
    }
    if lora.name:
        out["name"] = lora.name
    if lora.trigger:
        out["trigger"] = lora.trigger
    if lora.caption_trigger:
        out["caption_trigger"] = lora.caption_trigger
    if lora.url:
        out["url"] = lora.url
    if lora.download_url:
        out["download_url"] = lora.download_url
    if lora.download_fallback_url:
        out["download_fallback_url"] = lora.download_fallback_url
    if lora.model_id is not None:
        out["model_id"] = lora.model_id
    if lora.version_id is not None:
        out["version_id"] = lora.version_id
    return out


def _animation_lora_for(animation: Animation | None, side: str) -> Lora | None:
    if animation is None or side != "sdxl":
        return None
    loras = getattr(animation, "loras", None)
    if loras:
        link = next((l for l in animation.loras if l.kind == side), None)
        return link.lora if link else None
    return animation.lora


def _animation_visibility(animation: Any | None, attr: str) -> list[str] | None:
    """Visibility keys for act-driven SDXL region filtering.

    ``None`` keeps every region (no act, or the act row has no such field yet).
    An empty list means the act explicitly hides all regions for that slot.
    """
    if animation is None:
        return None
    if not hasattr(type(animation), attr):
        return None
    raw = getattr(animation, attr, None)
    if raw is None:
        return None
    return list(raw)


def _segment(source: str, label: str, tags: Iterable[str]) -> dict[str, Any]:
    from .segments import sdxl_segment_origin

    clean = [t.strip() for t in tags if (t or "").strip()]
    return {
        "source": source,
        "label": label,
        "tags": clean,
        "origin": sdxl_segment_origin(source),
    }


def _payload_inference(payload: BuildPayload) -> dict[str, Any]:
    """Map non-empty ``BuildPayload`` inference fields for SDXL render.

    Precedence: explicit payload values override the rolled style row for
    sampler, scheduler, steps, cfg_scale, width, and height. Empty or omitted
    payload fields are ignored so the style record supplies defaults.
    """
    out: dict[str, Any] = {}
    if payload.sampler:
        out["sampler"] = payload.sampler.strip()
    if payload.scheduler is not None and str(payload.scheduler).strip():
        out["scheduler"] = str(payload.scheduler).strip()
    if payload.steps is not None:
        out["steps"] = int(payload.steps)
    if payload.cfg_scale is not None:
        out["cfg_scale"] = float(payload.cfg_scale)
    if payload.width is not None:
        out["width"] = int(payload.width)
    if payload.height is not None:
        out["height"] = int(payload.height)
    return out


def _render_qwen_make(
    scene: Scene,
    *,
    inference: dict[str, Any] | None = None,
    style: Style | None = None,
    sdxl_render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the Qwen Image 2512 Make payload (prompts + sampling)."""
    from .payload import QWEN_MAKE_SHIFT_DEFAULT

    style = style if style is not None else scene.style
    if style is None:
        raise KeyError("no style available; create at least one /styles row")
    if sdxl_render is None:
        sdxl_render = _render_sdxl(scene, inference=inference, style=style)
    inf = inference or {}
    steps = int(inf["steps"]) if "steps" in inf else int(style.steps or 4)
    cfg = float(inf["cfg_scale"]) if "cfg_scale" in inf else float(style.cfg_scale or 1.0)
    shift = float(inf["shift"]) if "shift" in inf else QWEN_MAKE_SHIFT_DEFAULT
    return {
        "positive": sdxl_render["positive"],
        "negative": sdxl_render["negative"],
        "positive_segments": sdxl_render["positive_segments"],
        "negative_segments": sdxl_render["negative_segments"],
        "width": sdxl_render["width"],
        "height": sdxl_render["height"],
        "steps": steps,
        "cfg": cfg,
        "shift": shift,
        "engine": "qwen_image_2512",
    }


def _render_anima_make(
    scene: Scene,
    *,
    inference: dict[str, Any] | None = None,
    style: Style | None = None,
    sdxl_render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the Anima Make payload (prompts + sampling)."""
    style = style if style is not None else scene.style
    if style is None:
        raise KeyError("no style available; create at least one /styles row")
    if sdxl_render is None:
        sdxl_render = _render_sdxl(scene, inference=inference, style=style)
    inf = inference or {}
    steps = int(inf["steps"]) if "steps" in inf else int(style.steps or 40)
    cfg = float(inf["cfg_scale"]) if "cfg_scale" in inf else float(style.cfg_scale or 5.0)
    sampler = str(inf["sampler"]) if inf.get("sampler") else str(style.sampler or "er_sde")
    scheduler = (
        str(inf["scheduler"]) if inf.get("scheduler") else str(style.scheduler or "normal")
    )
    return {
        "positive": sdxl_render["positive"],
        "negative": sdxl_render["negative"],
        "positive_segments": sdxl_render["positive_segments"],
        "negative_segments": sdxl_render["negative_segments"],
        "width": sdxl_render["width"],
        "height": sdxl_render["height"],
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "engine": "anima",
    }


def _render_sdxl(
    scene: Scene,
    *,
    inference: dict[str, Any] | None = None,
    style: Style | None = None,
    for_refine: bool = False,
) -> dict[str, Any]:
    """Compose the SDXL payload purely by concatenation.

    When ``for_refine`` is true, act prompt tags/triggers/negative extras are
    kept but the act LoRA is omitted; refine stacks use style + character only.
    """
    style = style if style is not None else scene.style
    if style is None:
        raise KeyError("no style available; create at least one /styles row")
    inf = inference or {}
    eff_width = int(inf["width"]) if "width" in inf else style.width
    eff_height = int(inf["height"]) if "height" in inf else style.height
    if not eff_width or not eff_height:
        raise ValueError(
            f"style {style.slug!r} has no width/height; set them in the editor "
            f"before rolling SDXL prompts."
        )

    animation = scene.animation
    visible_char = _animation_visibility(animation, "visible_character")
    regions = _character_region_tags(scene.character)
    regions = animation_fields.filter_character_regions(regions, visible_char)

    char_lora = scene.character.character_lora if scene.character else None
    animation_sdxl_lora = _animation_lora_for(scene.animation, "sdxl")
    style_lora = style.lora

    trigger_loras = (char_lora, animation_sdxl_lora, style_lora)
    triggers = [l.trigger for l in trigger_loras if l and l.trigger]

    from .enforcement import enforce_sdxl_tags

    animation_tags = (
        enforce_sdxl_tags(scene.animation.tags or []) if scene.animation else []
    )
    location_tags = list(scene.location.tags or []) if scene.location else []
    view_tags = [v.key for v in scene.views if v.key]

    positive_segments: list[dict[str, Any]] = [
        _segment("style", "Style prefix", _csv_split(style.prefix)),
        _segment("triggers", "LoRA triggers", triggers),
        _segment("character_core", "Character — core", regions[char_attrs.REGION_CORE]),
        _segment("character_head", "Character — head", regions[char_attrs.REGION_HEAD]),
        _segment(
            "character_upper", "Character — upper", regions[char_attrs.REGION_UPPER]
        ),
        _segment(
            "character_lower", "Character — lower", regions[char_attrs.REGION_LOWER]
        ),
    ]
    if scene.character and scene.character.entity_type == ENTITY_CHARACTER:
        for source, label, tags in outfit_zone_segments(scene.character):
            positive_segments.append(_segment(source, label, tags))
    if scene.animation:
        positive_segments.append(
            _segment("animation", "Animation tags", animation_tags)
        )
    positive_segments.extend(
        [
            _segment("location", "Location", location_tags),
            _segment("view", "Camera view", view_tags),
        ]
    )

    neg_segments: list[dict[str, Any]] = [
        _segment("style", "Style negative", _csv_split(style.negative)),
    ]
    if scene.animation:
        for n in getattr(scene.animation, "negatives", []) or []:
            if n.kind == "sdxl_extra":
                neg_segments.append(
                    _segment(
                        "animation_extra",
                        "Animation SDXL negative extra",
                        _csv_split(n.value),
                    )
                )
    negative = ", ".join(
        _flatten_unique(seg["tags"] for seg in neg_segments if seg["tags"])
    )

    from .enforcement import filter_sdxl_tags_by_ban_keys, sdxl_tag_key

    ban_keys = {
        sdxl_tag_key(t)
        for seg in neg_segments
        for t in (seg.get("tags") or [])
        if sdxl_tag_key(t)
    }
    if ban_keys:
        for seg in positive_segments:
            seg["tags"] = filter_sdxl_tags_by_ban_keys(seg.get("tags") or [], ban_keys)
    positive = ", ".join(
        _flatten_unique(seg["tags"] for seg in positive_segments if seg["tags"])
    )

    # Resolution: swap if user asked for the opposite orientation.
    w, h = eff_width, eff_height
    if scene.orientation == "landscape" and h > w:
        w, h = h, w
    elif scene.orientation == "portrait" and w > h:
        w, h = h, w

    loras: list[dict[str, Any]] = []
    lora_entries = (
        ((char_lora, "character"), (style_lora, "style"))
        if for_refine
        else (
            (char_lora, "character"),
            (animation_sdxl_lora, "animation"),
            (style_lora, "style"),
        )
    )
    for lora, kind in lora_entries:
        payload = _lora_to_payload(lora, kind=kind)
        if payload:
            loras.append(payload)

    checkpoint = _style_checkpoint_payload(style)
    if inf.get("sampler"):
        checkpoint["sampler"] = inf["sampler"]
    if "scheduler" in inf:
        checkpoint["scheduler"] = inf["scheduler"]
    if "steps" in inf:
        checkpoint["steps"] = inf["steps"]
    if "cfg_scale" in inf:
        checkpoint["cfg_scale"] = inf["cfg_scale"]

    return {
        "positive": positive,
        "negative": negative,
        "positive_segments": positive_segments,
        "negative_segments": neg_segments,
        "width": w,
        "height": h,
        "loras": loras,
        "checkpoint": checkpoint,
    }
