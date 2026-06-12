from __future__ import annotations

import random
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import (
    ENTITY_BACKGROUND,
    Animation,
    DesignEntity,
    Style,
    View,
)
from .payload import (
    REFINE_SAME_AS_INFERENCE,
    BuildPayload,
    Scene,
    _slug_of,
)
from .roll import (
    _ensure_style_lora,
    _refine_sdxl_payload,
    _resolve_views,
    resolve_engine,
    resolve_refine_style,
    roll,
)
from .payload import MAKE_ENGINE_ANIMA, MAKE_ENGINE_QWEN, uses_illustrious_refine
from .render import (
    _apply_lora_strength_overrides,
    _character_adetailer_payload,
    _payload_inference,
    _prune_zero_strength_loras_in_build,
    _render_anima_make,
    _render_qwen_make,
    _render_sdxl,
)

def resolve_controlnets_for_build(
    animation: Animation | None,
    payload: BuildPayload,
    *,
    engine: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge animation defaults with Make toggles (enabled types only)."""
    if uses_illustrious_refine(engine):
        return {}
    from ..catalog.controlnet_types import (
        controlnet_defaults_for_type,
        normalize_controlnets_map,
    )

    stored = normalize_controlnets_map(
        (animation.controlnets or {}) if animation else {}
    )
    req = payload.controlnet
    if req is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, entry in stored.items():
        toggle = getattr(req, key, None)
        if toggle is None or not toggle.enabled:
            continue
        defaults = controlnet_defaults_for_type(key)
        out[key] = {
            "image_path": entry["image_path"],
            "strength": float(
                toggle.strength
                if toggle.strength is not None
                else entry.get("strength", defaults["strength"])
            ),
            "start_percent": float(
                toggle.start_percent
                if toggle.start_percent is not None
                else entry.get("start_percent", defaults["start_percent"])
            ),
            "end_percent": float(
                toggle.end_percent
                if toggle.end_percent is not None
                else entry.get("end_percent", defaults["end_percent"])
            ),
        }
    return out



def payload_from_stored_build(build: dict[str, Any]) -> BuildPayload:
    """Rebuild a :class:`BuildPayload` from a saved Make ``build_json``."""
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}

    def _slot(key: str) -> Any:
        if key in scene and scene[key] not in (None, ""):
            return scene[key]
        return request.get(key)

    views = scene.get("views")
    view = views[0] if isinstance(views, list) and views else request.get("view")
    seed = scene.get("seed")
    if seed is None:
        seed = request.get("seed")
    return BuildPayload(
        character=_slot("character"),
        animation=_slot("animation"),
        location=_slot("location"),
        style=_slot("style"),
        view=view,
        orientation=_slot("orientation"),
        seed=seed,
    )


def _row_by_slug(session: Session, model, slug: str | None):
    if not (slug or "").strip():
        return None
    return session.scalar(
        select(model).where(model.slug == str(slug).strip())  # type: ignore[attr-defined]
    )


def _location_by_key(session: Session, key: str | None) -> DesignEntity | None:
    if not (key or "").strip():
        return None
    return session.scalar(
        select(DesignEntity).where(
            DesignEntity.entity_type == ENTITY_BACKGROUND,
            DesignEntity.slug == str(key).strip(),
        )
    )


def scene_from_stored_build(session: Session, build: dict[str, Any]) -> Scene:
    """Reload the rolled scene rows by slug (no re-roll)."""
    stored = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    seed = stored.get("seed")
    if seed is None:
        seed = (build.get("request") or {}).get("seed")
    seed = int(seed or 0)
    animation = _row_by_slug(
        session, Animation, stored.get("animation")
    )
    views = _resolve_views(session, animation, None)
    view_keys = stored.get("views")
    if isinstance(view_keys, list) and view_keys:
        rows = session.scalars(select(View).where(View.key.in_(view_keys))).all()
        by_key = {v.key: v for v in rows}
        views = [by_key[k] for k in view_keys if k in by_key]
    character = _row_by_slug(session, DesignEntity, stored.get("character"))
    return Scene(
        seed=seed,
        character=character,
        animation=animation,
        style=_row_by_slug(session, Style, stored.get("style")),
        location=_location_by_key(session, stored.get("location")),
        views=views,
        orientation=(stored.get("orientation") or "portrait"),
    )


def build(
    session: Session,
    payload: BuildPayload,
    *,
    installed_checkpoints: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Resolve a scene and render SDXL + refine_sdxl payloads."""
    from ..generations import request_from_payload, resolve_request_from_build

    scene = roll(session, payload, installed_checkpoints=installed_checkpoints)
    _ensure_style_lora(session, scene.style)
    engine = resolve_engine(payload, scene.style)
    inference = _payload_inference(payload)
    if engine == MAKE_ENGINE_QWEN:
        if payload.shift is not None:
            inference = {**inference, "shift": float(payload.shift)}
    refine_rng = random.Random(scene.seed ^ 0xA91E5EED)
    refine_style = resolve_refine_style(
        session,
        refine_rng,
        payload,
        scene.style,
        installed_checkpoints=installed_checkpoints,
    )
    _ensure_style_lora(session, refine_style)
    refine_same = not uses_illustrious_refine(engine) and _slug_of(
        refine_style
    ) == _slug_of(scene.style)
    scene_summary = scene.summary()
    if refine_same:
        scene_summary["refine_style"] = REFINE_SAME_AS_INFERENCE
    else:
        scene_summary["refine_style"] = _slug_of(refine_style)
    enabled_controlnets = resolve_controlnets_for_build(
        scene.animation, payload, engine=engine
    )
    if enabled_controlnets:
        scene_summary["controlnets_enabled"] = list(enabled_controlnets.keys())
    scene_summary["engine"] = engine

    result: dict[str, Any] = {
        "request": request_from_payload(payload),
        "scene": scene_summary,
        "character_adetailer": _character_adetailer_payload(scene.character),
    }
    sdxl_render = _render_sdxl(scene, inference=inference or None)
    if engine == MAKE_ENGINE_QWEN:
        result["qwen_make"] = _render_qwen_make(
            scene, inference=inference or None, sdxl_render=sdxl_render
        )
    elif engine == MAKE_ENGINE_ANIMA:
        result["anima_make"] = _render_anima_make(
            scene, inference=inference or None, sdxl_render=sdxl_render
        )
    result["sdxl"] = sdxl_render
    refine_render = _render_sdxl(
        scene, inference=inference or None, style=refine_style, for_refine=True
    )
    refine_sdxl = _refine_sdxl_payload(refine_style, scene)
    refine_sdxl["positive"] = refine_render["positive"]
    refine_sdxl["negative"] = refine_render["negative"]
    refine_sdxl["positive_segments"] = refine_render["positive_segments"]
    refine_sdxl["negative_segments"] = refine_render["negative_segments"]
    from ...comfyui.make_lab.detailers import detailer_style_positive_from_render
    from ...comfyui.workflow import make_lab_refine_loras_from_build

    refine_sdxl["detailer_style_positive"] = detailer_style_positive_from_render(
        refine_render
    )
    refine_sdxl["loras"] = make_lab_refine_loras_from_build(refine_render, None)
    result["refine_sdxl"] = refine_sdxl
    _apply_lora_strength_overrides(result, payload.lora_strength_overrides)
    _prune_zero_strength_loras_in_build(result)
    if enabled_controlnets:
        result["controlnet"] = enabled_controlnets
    req = resolve_request_from_build(result["request"], result)
    req["engine"] = engine
    result["request"] = req
    return result
