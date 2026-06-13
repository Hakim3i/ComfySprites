"""Edit tab API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..comfyui.client import ComfyUIRequestError
from ..comfyui.edit_generate import (
    save_canvas_edit,
    start_edit_generate,
    start_edit_rmbg,
)
from ..db import session_scope
from ..db.models import EditGeneration, Generation
from ..services.edit_generations import list_recent_edit_generations
from ..services.generations import list_recent_make_generations
from ..services.qwen.build import (
    build_qwen_edit_from_edit,
    build_qwen_edit_from_generation,
    resolve_qwen_edit_fields,
)
from .router import router
from .schemas import EditCanvasSavePayload, EditGeneratePayload, EditRmbgPayload

_HISTORY_LIMIT = 25
_SOURCES_LIMIT = 60


@router.get("/edit/history")
def api_edit_history(limit: int = 25) -> dict[str, Any]:
    capped = min(max(1, limit), _HISTORY_LIMIT)
    with session_scope() as session:
        items = list_recent_edit_generations(session, limit=capped)
    return {"items": items}


@router.get("/edit/sources")
def api_edit_sources(limit: int = 60) -> dict[str, Any]:
    capped = min(max(1, limit), _SOURCES_LIMIT)
    with session_scope() as session:
        make_items = list_recent_make_generations(session, limit=capped)
        for item in make_items:
            item["source_kind"] = "make"
        edit_items = list_recent_edit_generations(session, limit=capped)
        for item in edit_items:
            item["source_kind"] = "edit"
        merged = make_items + edit_items
        merged.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return {"items": merged[:capped]}


@router.get("/edit/preview")
def api_edit_preview(
    source_prompt_id: str,
    source_kind: str = "make",
    animation_slug: str | None = None,
) -> dict[str, Any]:
    with session_scope() as session:
        if source_kind == "edit":
            source = session.get(EditGeneration, source_prompt_id)
            if source is None:
                raise HTTPException(404, "source edit not found")
            build = build_qwen_edit_from_edit(
                session,
                source,
                animation_slug=animation_slug,
            )
        else:
            source = session.get(Generation, source_prompt_id)
            if source is None:
                raise HTTPException(404, "source still not found")
            build = build_qwen_edit_from_generation(
                session,
                source,
                animation_slug=animation_slug,
            )
        qwen = build.get("qwen_edit") if isinstance(build.get("qwen_edit"), dict) else {}
        fields = resolve_qwen_edit_fields(build)
        return {
            "source_prompt_id": source_prompt_id,
            "source_kind": source_kind,
            "qwen_edit_prompt": fields.get("qwen_edit_prompt") or "",
            "qwen_edit_negative": fields.get("qwen_edit_negative") or "",
            "loras": list(qwen.get("loras") or []),
            "build": build,
        }


@router.post("/edit/generate")
def api_edit_generate(payload: EditGeneratePayload) -> dict[str, Any]:
    with session_scope() as session:
        try:
            return start_edit_generate(session, payload)
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


@router.post("/edit/canvas-save")
def api_edit_canvas_save(payload: EditCanvasSavePayload) -> dict[str, Any]:
    with session_scope() as session:
        try:
            build = None
            if payload.source_kind == "edit":
                row = session.get(EditGeneration, payload.source_prompt_id)
                if row is not None:
                    build = dict(row.build_json or {})
            else:
                row = session.get(Generation, payload.source_prompt_id)
                if row is not None:
                    build = dict(row.build_json or {})
            return save_canvas_edit(
                session,
                source_prompt_id=payload.source_prompt_id,
                source_kind=payload.source_kind,
                image_data_url=payload.image_data_url,
                animation_slug=payload.animation_slug,
                build=build,
                request=payload.model_dump(mode="json"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/edit/rmbg")
def api_edit_rmbg(payload: EditRmbgPayload) -> dict[str, Any]:
    with session_scope() as session:
        try:
            return start_edit_rmbg(session, payload)
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
