"""Build Qwen edit prompt block from a Make Lab source generation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ...db.models import Animation, EditGeneration, Generation, Lora


def _scene_dict(build: dict[str, Any]) -> dict[str, Any]:
    scene = build.get("scene")
    return scene if isinstance(scene, dict) else {}


def _lora_dict(lora: Lora | None) -> dict[str, Any] | None:
    if lora is None or not (lora.filename or "").strip():
        return None
    row: dict[str, Any] = {
        "id": lora.id,
        "kind": lora.kind,
        "filename": lora.filename,
        "name": lora.name,
        "trigger": lora.trigger,
        "caption_trigger": lora.caption_trigger,
        "strength": float(lora.strength or 1.0),
    }
    if lora.download_url:
        row["download_url"] = lora.download_url
    if lora.download_fallback_url:
        row["download_fallback_url"] = lora.download_fallback_url
    if lora.model_id is not None:
        row["model_id"] = lora.model_id
    if lora.version_id is not None:
        row["version_id"] = lora.version_id
    if lora.url:
        row["civitai_url"] = lora.url
    return row


def _load_animation(session: Session, slug: str | None) -> Animation | None:
    if not slug:
        return None
    return session.scalar(
        select(Animation)
        .where(Animation.slug == slug)
        .options(
            joinedload(Animation.qwen_edit_lora),
        )
    )


def _apply_animation_qwen_edit(
    build: dict[str, Any],
    animation: Animation | None,
    *,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    prompt = ""
    loras: list[dict[str, Any]] = []
    if animation:
        prompt = (animation.qwen_edit_prompt or "").strip()
        lora_row = _lora_dict(animation.qwen_edit_lora)
        if lora_row:
            strength = float((lora_strengths or {}).get("qwen_edit", lora_row["strength"]))
            lora_row = {**lora_row, "kind": "qwen_edit", "strength": strength}
            loras.append(lora_row)
    out = dict(build)
    out["qwen_edit"] = {"prompt": prompt, "loras": loras}
    return out


def build_qwen_edit_from_generation(
    session: Session,
    source: Generation,
    *,
    animation_slug: str | None = None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    build = dict(source.build_json or {})
    scene = _scene_dict(build)
    anim_slug = (animation_slug or "").strip() or None
    animation = _load_animation(session, anim_slug)

    out = _apply_animation_qwen_edit(
        build, animation, lora_strengths=lora_strengths
    )
    out["scene"] = {
        **scene,
        "animation": animation.slug if animation else anim_slug,
    }
    return out


def build_qwen_edit_from_edit(
    session: Session,
    source: EditGeneration,
    *,
    animation_slug: str | None = None,
    lora_strengths: dict[str, float] | None = None,
) -> dict[str, Any]:
    build = dict(source.build_json or {})
    scene = _scene_dict(build)
    anim_slug = (animation_slug or "").strip() or source.animation_slug or scene.get(
        "animation"
    )
    animation = _load_animation(session, anim_slug)
    out = _apply_animation_qwen_edit(
        build, animation, lora_strengths=lora_strengths
    )
    out["scene"] = {
        **scene,
        "animation": animation.slug if animation else anim_slug,
    }
    return out


def resolve_qwen_edit_fields(
    build: dict[str, Any],
    *,
    qwen_edit_prompt: str | None = None,
) -> dict[str, str | None]:
    qwen = build.get("qwen_edit") if isinstance(build.get("qwen_edit"), dict) else {}
    override = (qwen_edit_prompt or "").strip()
    prompt = override or str(qwen.get("prompt") or "").strip() or None
    return {"qwen_edit_prompt": prompt}
