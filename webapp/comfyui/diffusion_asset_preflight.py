"""Two-phase ComfySpritesDownloader preflight for diffusion-model catalog entries."""

from __future__ import annotations

import threading

from typing import Any

from .asset_inventory import (
    merge_extra_diffusion_models_into_missing,
    merge_extra_loras_into_missing,
    missing_diffusion_model_assets,
    missing_filenames,
)
from .asset_manifest import tokens_for_comfyui
from .client import queue_prompt, wait_for_execution
from .download_workflow import build_asset_download_workflow
from .jobs import job_store
from .ws_progress import connect_comfyui_ws, start_ws_progress_listener

_ASSET_DOWNLOAD_TIMEOUT = 3600.0
_ASSET_REFRESH_ERROR = (
    "ComfyUI did not register downloaded diffusion models. "
    "Restart ComfyUI or check models/diffusion_models, text_encoders, vae, and loras."
)

_DIFFUSION_ASSET_BUCKETS = (
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
)


def _job_is_cancelled(job_id: str) -> bool:
    job = job_store().get(job_id)
    return job is not None and job.status == "cancelled"


def ensure_diffusion_model_assets_on_comfyui(
    job_id: str,
    model_id: str,
    *,
    base_url: str,
    client_id: str,
    stop_event: threading.Event,
    extra_loras: list[dict[str, Any]] | None = None,
    build: dict[str, Any] | None = None,
) -> None:
    """Queue ``ComfySpritesDownloader`` for catalog assets missing on ComfyUI."""
    store = job_store()
    missing = missing_diffusion_model_assets(model_id, base_url, build=build)
    checkpoint = (
        (build or {}).get("sdxl", {}).get("checkpoint")
        if isinstance((build or {}).get("sdxl"), dict)
        else None
    )
    extra_unet = [checkpoint] if isinstance(checkpoint, dict) and checkpoint.get("filename") else None
    missing = merge_extra_diffusion_models_into_missing(
        missing,
        extra_unet,
        base_url=base_url,
    )
    missing = merge_extra_loras_into_missing(
        missing,
        extra_loras,
        base_url=base_url,
    )
    if not any(missing.get(key) for key in _DIFFUSION_ASSET_BUCKETS):
        return

    store.begin_fetching_assets(job_id)

    def _on_fetch_poll(fraction: float) -> None:
        store.set_asset_fetch_progress(job_id, fraction)

    download_wf = build_asset_download_workflow(
        missing,
        tokens=tokens_for_comfyui(),
    )
    ws, ws_err = connect_comfyui_ws(client_id, base_url=base_url)
    ws_stop = threading.Event()
    if ws is not None:
        store.update_progress(job_id, ws_connected=True, ws_error=None)
    elif ws_err:
        store.update_progress(job_id, ws_connected=False, ws_error=ws_err)

    dl_prompt_id, _ = queue_prompt(download_wf, base_url, client_id=client_id)
    store.set_asset_download_prompt_id(job_id, dl_prompt_id)
    if ws is not None:
        start_ws_progress_listener(
            client_id,
            job_id,
            ws=ws,
            base_url=base_url,
            stop_event=ws_stop,
            match_prompt_id=dl_prompt_id,
        )
    try:
        wait_for_execution(
            dl_prompt_id,
            base_url,
            timeout=_ASSET_DOWNLOAD_TIMEOUT,
            cancel_event=stop_event,
            on_wait_poll=_on_fetch_poll if ws is None else None,
        )
    finally:
        ws_stop.set()
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
    if _job_is_cancelled(job_id):
        return
    still_missing = merge_extra_loras_into_missing(
        missing_diffusion_model_assets(model_id, base_url),
        extra_loras,
        base_url=base_url,
    )
    if any(still_missing.get(key) for key in _DIFFUSION_ASSET_BUCKETS):
        still = missing_filenames(still_missing)
        detail = ", ".join(still[:5])
        if len(still) > 5:
            detail += f", … (+{len(still) - 5} more)"
        raise RuntimeError(f"{_ASSET_REFRESH_ERROR} Missing: {detail}")
