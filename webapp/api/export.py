"""Export tab API: saved video library + batched frame background removal."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..comfyui.client import ComfyUIRequestError
from ..comfyui.export_rmbg import start_export_rmbg
from ..db import session_scope
from ..services.video_generations import (
    delete_video_generation,
    list_recent_video_generations,
)
from .router import router
from .schemas import ExportRmbgPayload

_VIDEO_LIMIT = 200


@router.get("/export/videos")
def api_export_videos(limit: int = 100) -> dict[str, Any]:
    capped = min(max(1, limit), _VIDEO_LIMIT)
    with session_scope() as session:
        items = list_recent_video_generations(session, limit=capped)
    return {"items": items}


@router.delete("/export/videos/{prompt_id}")
def api_export_delete_video(prompt_id: str) -> dict[str, Any]:
    with session_scope() as session:
        deleted = delete_video_generation(session, prompt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="saved video not found")
    return {"prompt_id": prompt_id, "deleted": True}


@router.post("/export/rmbg")
def api_export_rmbg(payload: ExportRmbgPayload) -> dict[str, Any]:
    with session_scope() as session:
        try:
            return start_export_rmbg(session, payload)
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
