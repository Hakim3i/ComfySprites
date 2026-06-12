"""Make Lab generation API."""

from __future__ import annotations


from typing import Any


from fastapi import HTTPException

from fastapi.responses import Response


from ..comfyui.client import ComfyUIRequestError, list_upscale_models
from ..services.catalog.upscale_models import all_upscale_model_specs

from ..env_settings import load_comfyui_base_url

from ..comfyui.make_lab.detailers import detailer_catalog

from ..comfyui.animate_generate import cancel_animate_job
from ..comfyui.edit_generate import cancel_edit_job
from ..comfyui.export_rmbg import cancel_export_job
from ..comfyui.generate import cancel_make_lab_job, start_make_generate

from ..comfyui.jobs import job_store

from ..services.sdxl import composer

from ..db import session_scope

from ..services.generations import list_recent_make_generations

from .router import router


_HISTORY_LIMIT = 25


@router.get("/comfyui/upscale-models")
def api_comfyui_upscale_models() -> dict[str, Any]:
    """Upscale weights installed on the ComfyUI host (``models/upscale_models``)."""

    catalog = all_upscale_model_specs()
    options = [
        {
            "key": spec.key,
            "label": spec.label,
            "filename": spec.filename,
            "scale": spec.scale,
        }
        for spec in catalog
    ]
    installed_names: list[str] = []
    try:
        base_url = load_comfyui_base_url()
    except RuntimeError:
        return {"models": [spec.filename for spec in catalog], "options": options}
    try:
        installed_names = list_upscale_models(base_url)
        installed = {name.lower() for name in installed_names}
    except ComfyUIRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=502, detail=f"ComfyUI unreachable: {exc}"
        ) from exc
    models: list[str] = []
    seen: set[str] = set()
    for spec in catalog:
        key = spec.filename.lower()
        if key not in seen:
            seen.add(key)
            models.append(spec.filename)
    for name in installed_names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            models.append(name)
    for row in options:
        row["installed"] = row["filename"].lower() in installed
    return {"models": models, "options": options}


@router.get("/make/detailers")
def api_make_lab_detailers() -> dict[str, Any]:
    """Detailer regions for Make Lab toggles (order + labels)."""

    regions = detailer_catalog()

    return {
        "order": [r["id"] for r in regions],
        "regions": regions,
    }


@router.get("/make/history")
def api_make_lab_history(limit: int = _HISTORY_LIMIT) -> dict[str, Any]:
    """Recent Make Lab generations for the history sidebar."""

    capped = min(max(1, limit), _HISTORY_LIMIT)

    with session_scope() as session:
        items = list_recent_make_generations(session, limit=capped)

    return {"items": items}


@router.post("/make/generate")
def api_make_lab_generate(payload: composer.BuildPayload) -> dict[str, Any]:
    """Build, queue ComfyUI, return ``prompt_id`` — poll ``GET /api/comfyui/job/{id}``."""

    with session_scope() as session:
        try:
            return start_make_generate(session, payload)

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


@router.post("/comfyui/job/{prompt_id}/cancel")
def api_comfyui_job_cancel(prompt_id: str) -> dict[str, Any]:
    """Interrupt ComfyUI execution and mark the Make Lab job cancelled."""

    store = job_store()

    if (
        cancel_make_lab_job(prompt_id)
        or cancel_animate_job(prompt_id)
        or cancel_edit_job(prompt_id)
        or cancel_export_job(prompt_id)
    ):
        return {"prompt_id": prompt_id, "status": "cancelled"}

    job = store.get(prompt_id)

    if job is None:
        raise HTTPException(status_code=404, detail="unknown prompt_id")

    if job.status == "complete":
        raise HTTPException(status_code=409, detail="job already complete")

    raise HTTPException(status_code=409, detail="job not cancellable")


@router.get("/comfyui/job/{prompt_id}")
def api_comfyui_job(prompt_id: str) -> dict[str, Any]:
    """Generation progress and result for a Make Lab queue."""

    job = job_store().get(prompt_id)

    if job is None:
        raise HTTPException(status_code=404, detail="unknown prompt_id")

    return job.to_api()


@router.get("/comfyui/job/{prompt_id}/live-preview")
def api_comfyui_job_live_preview(prompt_id: str) -> Response:
    """In-memory KSampler preview frame (not written under ``outputs/make/``)."""

    preview = job_store().get_live_preview(prompt_id)

    if preview is None:
        raise HTTPException(status_code=404, detail="no live preview")

    data, mime = preview

    return Response(content=data, media_type=mime)
