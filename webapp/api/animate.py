"""Animate tab API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..comfyui.animate_generate import start_animate_generate
from ..comfyui.client import ComfyUIRequestError
from ..db import session_scope
from ..db.models import EditGeneration, Generation
from ..services.ltx.build import (
    build_ltx_from_edit,
    build_ltx_from_generation,
    resolve_ltx_fields,
)
from ..services.video_generations import list_recent_video_generations
from .router import router
from .schemas import AnimateGeneratePayload

_HISTORY_LIMIT = 25


@router.get("/animate/history")
def api_animate_history(limit: int = 25) -> dict[str, Any]:
    capped = min(max(1, limit), _HISTORY_LIMIT)
    with session_scope() as session:
        items = list_recent_video_generations(session, limit=capped)
    return {"items": items}


@router.get("/animate/ltx-preview")
def api_animate_ltx_preview(
    source_prompt_id: str,
    source_kind: str = "make",
    style_slug: str | None = None,
    animation_slug: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
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
        ltx = build.get("ltx") if isinstance(build.get("ltx"), dict) else {}
        fields = resolve_ltx_fields(build)
        return {
            "source_prompt_id": source_prompt_id,
            "ltx_caption": fields.get("ltx_caption") or "",
            "ltx_video_negative": fields.get("ltx_video_negative") or "",
            "ltx_audio_negative": fields.get("ltx_audio_negative") or "",
            "loras": list(ltx.get("loras") or []),
            "build": build,
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
