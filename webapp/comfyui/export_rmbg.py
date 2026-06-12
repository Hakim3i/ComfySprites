"""Export tab: batched background removal over many frames in one ComfyUI job."""

from __future__ import annotations

import base64
import binascii
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..config import EXPORT_OUTPUT_DIR, EXPORT_OUTPUT_URL_PREFIX
from ..env_settings import load_comfyui_base_url
from .client import (
    JobCancelled,
    collect_output_images,
    delete_queue_prompts,
    interrupt_prompt,
    queue_prompt,
    upload_image_bytes,
    wait_for_prompt,
)
from .generate import (
    _cancel_targets_for,
    _job_is_cancelled,
    _register_stop_event,
    _signal_stop_event,
    _unregister_stop_event,
)
from .jobs import job_store
from .make_lab.rmbg import _RMBG_INPUT_KEYS, _instantiate_rmbg_node, load_rmbg_defaults
from .outputs import (
    download_fraction_from_parts,
    remove_live_preview_files,
    save_all_output_images,
)
from .qwen_edit.progress import build_qwen_edit_progress_plan
from .ws_progress import connect_comfyui_ws, start_ws_progress_listener


def _decode_data_url(data_url: str) -> bytes:
    raw = (data_url or "").strip()
    if not raw:
        raise ValueError("empty frame data")
    if raw.startswith("data:"):
        _, _, payload = raw.partition(",")
    else:
        payload = raw
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid frame data: {exc}") from exc


def _rmbg_settings_from_payload(payload: Any) -> dict[str, Any]:
    settings = load_rmbg_defaults()
    block = getattr(payload, "rmbg", None)
    if block is not None:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        for key, val in data.items():
            if key in _RMBG_INPUT_KEYS:
                settings[key] = val
        return settings
    bg = str(getattr(payload, "background", "transparent") or "transparent")
    bg_color = str(getattr(payload, "background_color", "#000000") or "#000000")
    settings["background"] = "Alpha" if bg == "transparent" else "Color"
    settings["background_color"] = bg_color if settings["background"] == "Color" else "#222222"
    return settings


def _build_export_rmbg_workflow(
    frame_names: list[str],
    *,
    settings: dict[str, Any],
) -> dict[str, Any]:

    workflow: dict[str, Any] = {}
    load_ids: list[str] = []
    for idx, name in enumerate(frame_names):
        load_id = f"load_image_{idx}"
        workflow[load_id] = {
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Frame {idx}"},
            "inputs": {"image": name},
        }
        load_ids.append(load_id)

    # Chain ImageBatch nodes so RMBG processes every frame in a single batch.
    batch_source: list[Any] = [load_ids[0], 0]
    for idx in range(1, len(load_ids)):
        batch_id = f"batch_{idx}"
        workflow[batch_id] = {
            "class_type": "ImageBatch",
            "_meta": {"title": f"Batch {idx}"},
            "inputs": {
                "image1": batch_source,
                "image2": [load_ids[idx], 0],
            },
        }
        batch_source = [batch_id, 0]

    rmbg_id = "rmbg"
    workflow[rmbg_id] = _instantiate_rmbg_node(batch_source, settings)
    workflow["export_image"] = {
        "class_type": "SaveImage",
        "_meta": {"title": "Save Image"},
        "inputs": {
            "filename_prefix": "Export_RMBG",
            "images": [rmbg_id, 0],
        },
    }
    return workflow


def _finish_export_rmbg_job(
    job_id: str,
    comfy_prompt_id: str,
    *,
    base_url: str | None,
    wait_timeout: float,
    stop_event: threading.Event,
) -> None:
    store = job_store()
    try:
        history = wait_for_prompt(
            comfy_prompt_id,
            base_url,
            timeout=wait_timeout,
            cancel_event=stop_event,
        )
        if _job_is_cancelled(job_id):
            return
        store.begin_finalize(job_id)
        store.set_download_progress(
            job_id, download_fraction_from_parts(wait_part=0.0)
        )
        images = collect_output_images(history, node_ids=["export_image"])

        def _on_download_progress(fraction: float) -> None:
            store.set_download_progress(job_id, fraction)

        saved = save_all_output_images(
            history,
            comfy_prompt_id,
            base_url=base_url,
            images=images,
            on_download_progress=_on_download_progress,
            output_dir=EXPORT_OUTPUT_DIR,
            url_prefix=EXPORT_OUTPUT_URL_PREFIX,
        )
        if _job_is_cancelled(job_id):
            return
        urls = [url for _path, url, _sid in saved]
        ids = [sid for _path, _url, sid in saved]
        store.complete(
            job_id,
            preview_url=urls[0] if urls else "",
            preview_urls=urls,
            image_ids=ids,
            build=None,
        )
    except JobCancelled:
        pass
    except Exception as exc:
        if not _job_is_cancelled(job_id):
            store.fail(job_id, str(exc))
    finally:
        remove_live_preview_files(job_id)
        stop_event.set()
        _unregister_stop_event(job_id)


def start_export_rmbg(session: Session, payload: Any) -> dict[str, Any]:
    del session  # frames are supplied inline; no DB source needed
    frames = list(getattr(payload, "frames", None) or [])
    if not frames:
        raise ValueError("no frames supplied for background removal")
    rmbg_settings = _rmbg_settings_from_payload(payload)

    frame_bytes = [_decode_data_url(frame) for frame in frames]

    resolved_base = load_comfyui_base_url()
    job_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    request = (
        payload.model_dump(mode="json")
        if hasattr(payload, "model_dump")
        else dict(payload)
    )

    store = job_store()
    store.create(
        job_id,
        client_id,
        lab="export",
        base_url=resolved_base,
        build=None,
        request={k: v for k, v in request.items() if k != "frames"},
        workflow_node_count=0,
        node_titles={},
        progress_plan=build_qwen_edit_progress_plan({}, node_titles={}),
    )

    def _run() -> None:
        stop_event = threading.Event()
        _register_stop_event(job_id, stop_event)
        try:
            frame_names: list[str] = []
            for idx, data in enumerate(frame_bytes):
                name = upload_image_bytes(
                    data, f"export_frame_{idx:04d}.png", base_url=resolved_base
                )
                frame_names.append(name)
            workflow = _build_export_rmbg_workflow(
                frame_names,
                settings=rmbg_settings,
            )
            ws, ws_err = connect_comfyui_ws(client_id, base_url=resolved_base)
            comfy_prompt_id, _ = queue_prompt(
                workflow, resolved_base, client_id=client_id
            )
            store.set_comfy_prompt_id(job_id, comfy_prompt_id)
            store.update_progress(job_id, status="queued")
            if ws is not None:
                store.update_progress(
                    job_id, ws_connected=True, ws_error=None, ws_prompt_active=True
                )
            elif ws_err:
                store.update_progress(job_id, ws_connected=False, ws_error=ws_err)
            start_ws_progress_listener(
                client_id,
                job_id,
                ws=ws,
                base_url=resolved_base,
                stop_event=stop_event,
                match_prompt_id=comfy_prompt_id,
            )
            _finish_export_rmbg_job(
                job_id,
                comfy_prompt_id,
                base_url=resolved_base,
                wait_timeout=600.0,
                stop_event=stop_event,
            )
        except Exception as exc:
            if not _job_is_cancelled(job_id):
                store.fail(job_id, str(exc))
        finally:
            stop_event.set()
            _unregister_stop_event(job_id)

    threading.Thread(
        target=_run, daemon=True, name=f"export-rmbg-{job_id[:8]}"
    ).start()
    return {"prompt_id": job_id, "request": {"frame_count": len(frames)}}


def cancel_export_job(job_id: str, *, base_url: str | None = None) -> bool:
    store = job_store()
    job = store.get(job_id)
    if job is None:
        return False
    resolved_base = base_url if base_url is not None else job.base_url
    for pid in _cancel_targets_for(job_id):
        for call in (
            lambda p=pid: interrupt_prompt(p, resolved_base),
            lambda p=pid: delete_queue_prompts([p], resolved_base),
        ):
            try:
                call()
            except Exception:
                pass
    _signal_stop_event(job_id)
    if job.status not in ("complete", "cancelled"):
        store.cancel(job_id)
        return True
    return job.status == "cancelled"
