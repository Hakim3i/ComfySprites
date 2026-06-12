"""Animate tab API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..comfyui.animate_generate import start_animate_generate
from ..comfyui.client import ComfyUIRequestError
from ..db import session_scope
from ..db.models import EditGeneration, Generation
from ..services.catalog.diffusion_models import diffusion_model_spec
from ..services.ltx.build import (
    build_ltx_from_edit,
    build_ltx_from_generation,
    resolve_ltx_fields,
    resolve_wan_fields,
)
from ..services.video_generations import list_recent_video_generations
from .router import router
from .schemas import AnimateGeneratePayload

_HISTORY_LIMIT = 25


def _build_animate_preview(
    session,
    *,
    source_prompt_id: str,
    source_kind: str,
    style_slug: str | None,
    animation_slug: str | None,
    model_id: str | None,
) -> dict[str, Any]:
    if source_kind == "edit":
        source = session.get(EditGeneration, source_prompt_id)
        if source is None:
            raise HTTPException(404, "source edit not found")
        build = build_ltx_from_edit(
            session,
            source,
            style_slug=style_slug,
            animation_slug=animation_slug,
        )
    else:
        source = session.get(Generation, source_prompt_id)
        if source is None:
            raise HTTPException(404, "source still not found")
        build = build_ltx_from_generation(
            session,
            source,
            style_slug=style_slug,
            animation_slug=animation_slug,
        )

    mid = (model_id or "").strip()
    spec = diffusion_model_spec(mid) if mid else None
    engine = spec.engine if spec else "ltx23"

    if engine == "wan22":
        wan = build.get("wan") if isinstance(build.get("wan"), dict) else {}
        fields = resolve_wan_fields(build)
        return {
            "source_prompt_id": source_prompt_id,
            "engine": engine,
            "positive": fields.get("positive") or "",
            "negative": fields.get("negative") or "",
            "ltx_caption": fields.get("ltx_caption") or "",
            "loras": list(wan.get("loras") or []),
            "build": build,
        }

    ltx = build.get("ltx") if isinstance(build.get("ltx"), dict) else {}
    fields = resolve_ltx_fields(build)
    return {
        "source_prompt_id": source_prompt_id,
        "engine": engine,
        "positive": fields.get("ltx_caption") or "",
        "negative": fields.get("ltx_video_negative") or "",
        "ltx_caption": fields.get("ltx_caption") or "",
        "ltx_video_negative": fields.get("ltx_video_negative") or "",
        "ltx_audio_negative": fields.get("ltx_audio_negative") or "",
        "loras": list(ltx.get("loras") or []),
        "build": build,
    }


@router.get("/animate/history")
def api_animate_history(limit: int = 25) -> dict[str, Any]:
    capped = min(max(1, limit), _HISTORY_LIMIT)
    with session_scope() as session:
        items = list_recent_video_generations(session, limit=capped)
    return {"items": items}


@router.get("/animate/prompt-preview")
def api_animate_prompt_preview(
    source_prompt_id: str,
    source_kind: str = "make",
    style_slug: str | None = None,
    animation_slug: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        return _build_animate_preview(
            session,
            source_prompt_id=source_prompt_id,
            source_kind=source_kind,
            style_slug=style_slug,
            animation_slug=animation_slug,
            model_id=model_id,
        )


@router.get("/animate/ltx-preview")
def api_animate_ltx_preview(
    source_prompt_id: str,
    source_kind: str = "make",
    style_slug: str | None = None,
    animation_slug: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        data = _build_animate_preview(
            session,
            source_prompt_id=source_prompt_id,
            source_kind=source_kind,
            style_slug=style_slug,
            animation_slug=animation_slug,
            model_id="ltx23_eros",
        )
        if data.get("engine") != "ltx23":
            raise HTTPException(400, "ltx-preview requires an LTX model")
        return {
            "source_prompt_id": data["source_prompt_id"],
            "ltx_caption": data.get("ltx_caption") or "",
            "ltx_video_negative": data.get("ltx_video_negative") or "",
            "ltx_audio_negative": data.get("ltx_audio_negative") or "",
            "loras": data.get("loras") or [],
            "build": data.get("build") or {},
        }


@router.post("/animate/generate")
def api_animate_generate(payload: AnimateGeneratePayload) -> dict[str, Any]:
    with session_scope() as session:
        try:
            return start_animate_generate(session, payload)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ComfyUIRequestError as exc:
            status = 400 if 400 <= exc.status_code < 500 else 502
            raise HTTPException(status_code=status, detail=exc.message) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=502, detail=f"ComfyUI unreachable: {exc}"
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
