"""Health, dropdowns, build, and character-attribute discovery."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from ..services.design import attributes as char_attrs
from ..services.design.animation_fields import animation_orientations
from ..services.sdxl import composer
from ..services.design.scene import SceneCompatibilityError
from ..db.models import (
    ENTITY_BACKGROUND,
    ENTITY_CHARACTER,
    ROLE_MAIN,
    VIEW_KIND_SHOT,
    Animation,
    DesignEntity,
    Style,
    View,
)
from ..db import session_scope
from ..revision import current_revision
from ..services.catalog.style_defaults import (
    dimension_hints,
    new_style_defaults,
    sampler_hints,
    scheduler_hints,
)
from ..comfyui.client import check_comfyui_status
from ..comfyui.generate import composer_build_with_installed_checkpoints
from ..env_settings import load_comfyui_base_url
from .router import router


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "revision": current_revision()}


@router.get("/comfyui/status")
def api_comfyui_status() -> dict[str, Any]:
    return check_comfyui_status(load_comfyui_base_url())


@router.get("/dropdowns")
def api_dropdowns() -> dict[str, Any]:
    with session_scope() as s:
        characters = s.scalars(
            select(DesignEntity)
            .where(DesignEntity.entity_type == ENTITY_CHARACTER, DesignEntity.role == ROLE_MAIN)
            .order_by(DesignEntity.slug)
        ).all()
        animations = s.scalars(select(Animation).order_by(Animation.slug)).all()
        styles = s.scalars(select(Style).order_by(Style.slug)).all()
        backgrounds = s.scalars(
            select(DesignEntity)
            .where(DesignEntity.entity_type == ENTITY_BACKGROUND)
            .order_by(DesignEntity.slug)
        ).all()
        views = s.scalars(
            select(View).where(View.kind == VIEW_KIND_SHOT).order_by(View.position)
        ).all()
        ns = new_style_defaults()
        return {
            "characters": [c.slug for c in characters],
            "animations": [a.slug for a in animations],
            "styles": [s_.slug for s_ in styles],
            "backgrounds": [b.slug for b in backgrounds],
            "locations": [b.slug for b in backgrounds],
            "views": [v.key for v in views],
            "orientations": [key for key, _ in animation_orientations()],
            "sampler_hints": list(sampler_hints()),
            "scheduler_hints": list(scheduler_hints()),
            "dimension_hints": list(dimension_hints()),
            "style_defaults": {
                "sampler": ns.sampler,
                "scheduler": ns.scheduler,
                "steps": ns.steps,
                "cfg_scale": ns.cfg_scale,
                "width": ns.width,
                "height": ns.height,
            },
            "revision": current_revision(),
        }


@router.post("/build")
def api_build(payload: composer.BuildPayload) -> dict[str, Any]:
    with session_scope() as s:
        try:
            result = composer_build_with_installed_checkpoints(s, payload)
        except SceneCompatibilityError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/character-attributes")
def character_attributes() -> dict[str, Any]:
    return char_attrs.options_payload()

