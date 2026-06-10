"""Make: build → ComfyUI queue → preview URL."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from .. import PROJECT_ROOT
from ..make.limits import MAKE_LAB_IMAGES_MAX, MAKE_LAB_IMAGES_MIN
from ..services.sdxl import composer
from ..db import session_scope
from ..services.generations import save_make_generation
from ..env_settings import load_comfyui_base_url
from .asset_inventory import assets_ready, missing_assets, missing_filenames
from .asset_manifest import tokens_for_comfyui
from .client import (
    ComfyUIRequestError,
    JobCancelled,
    collect_output_images,
    delete_queue_prompts,
    interrupt_prompt,
    queue_prompt,
    wait_for_execution,
    wait_for_prompt,
)
from .download_workflow import build_asset_download_workflow
from .jobs import job_store
from .outputs import (
    download_fraction_from_parts,
    remove_live_preview_files,
    save_all_output_images,
)
from .make_lab.progress import build_progress_plan
from .memory_cleanup import maybe_free_memory_before_make
from .workflow import (
    MAKE_LAB_SAVE_NODE_ID,
    build_result_to_make_lab,
    workflow_node_titles,
)
from .ws_progress import connect_comfyui_ws, start_ws_progress_listener

_log = logging.getLogger(__name__)

_ASSET_DOWNLOAD_TIMEOUT = 3600.0
_ASSET_REFRESH_ERROR = (
    "ComfyUI did not register downloaded models. "
    "Restart ComfyUI or check models/checkpoints, loras, and controlnet folders."
)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_STOP_EVENTS: dict[str, threading.Event] = {}


def _register_stop_event(job_id: str, stop_event: threading.Event) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_STOP_EVENTS[job_id] = stop_event


def _unregister_stop_event(job_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_STOP_EVENTS.pop(job_id, None)


def _signal_stop_event(job_id: str) -> None:
    with _ACTIVE_LOCK:
        stop_event = _ACTIVE_STOP_EVENTS.get(job_id)
    if stop_event is not None:
        stop_event.set()


def _job_is_cancelled(job_id: str) -> bool:
    job = job_store().get(job_id)
    return job is not None and job.status == "cancelled"


def _resolve_base(base_url: str | None = None) -> str:
    if base_url is not None:
        return base_url
    return load_comfyui_base_url()


def _batch_size_from_request(request: dict[str, Any] | None) -> int:
    """Clamp workflow ``images`` (batch size per ComfyUI job) from a saved request."""
    if not request:
        return MAKE_LAB_IMAGES_MIN
    try:
        raw = request.get("images")
        if raw is not None:
            n = int(raw)
            return max(MAKE_LAB_IMAGES_MIN, min(MAKE_LAB_IMAGES_MAX, n))
    except (TypeError, ValueError):
        pass
    return MAKE_LAB_IMAGES_MIN


def _comfyui_stop_remote(prompt_id: str, base_url: str | None) -> None:
    for name, call in (
        ("interrupt", lambda: interrupt_prompt(prompt_id, base_url)),
        ("delete_queue", lambda: delete_queue_prompts([prompt_id], base_url)),
    ):
        try:
            call()
        except Exception as exc:
            _log.warning("ComfyUI %s for %s failed: %s", name, prompt_id, exc)


def _cancel_targets_for(job_id: str) -> list[str]:
    job = job_store().get(job_id)
    if job is None:
        return []
    ids: list[str] = []
    if job.asset_download_prompt_id:
        ids.append(job.asset_download_prompt_id)
    if job.comfy_prompt_id:
        ids.append(job.comfy_prompt_id)
    return list(dict.fromkeys(ids))


def _ensure_assets_on_comfyui(
    job_id: str,
    build: dict[str, Any],
    *,
    base_url: str,
    client_id: str,
    stop_event: threading.Event,
) -> None:
    store = job_store()
    missing = missing_assets(build, base_url)
    if not any(
        missing[k]
        for k in ("checkpoints", "loras", "controlnets", "upscalers", "detailers")
    ):
        return

    store.begin_fetching_assets(job_id)
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    checkpoint = (
        sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
    )
    ckpt_name = str(checkpoint.get("filename") or "").strip()
    download_wf = build_asset_download_workflow(
        missing,
        inference_ckpt_name=ckpt_name,
        tokens=tokens_for_comfyui(),
    )

    def _on_fetch_poll(fraction: float) -> None:
        store.set_asset_fetch_progress(job_id, fraction)

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
    if not assets_ready(build, base_url):
        still = missing_filenames(missing_assets(build, base_url))
        detail = ", ".join(still[:5])
        if len(still) > 5:
            detail += f", … (+{len(still) - 5} more)"
        raise RuntimeError(f"{_ASSET_REFRESH_ERROR} Missing: {detail}")


def _finish_generation_job(
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
            job_id,
            download_fraction_from_parts(wait_part=0.0),
        )
        images = collect_output_images(history, node_ids=[MAKE_LAB_SAVE_NODE_ID])

        def _on_download_progress(fraction: float) -> None:
            store.set_download_progress(job_id, fraction)

        saved = save_all_output_images(
            history,
            job_id,
            base_url=base_url,
            images=images,
            on_download_progress=_on_download_progress,
        )
        if _job_is_cancelled(job_id):
            return
        job = store.get(job_id)
        batch_size = _batch_size_from_request(job.request if job else None)
        if job and job.build:
            with session_scope() as session:
                for batch_index, (path, _url, storage_id) in enumerate(saved):
                    if _job_is_cancelled(job_id):
                        return
                    request = dict(job.request or {})
                    request["images"] = batch_size
                    request["batch_index"] = batch_index
                    image_path = path.relative_to(PROJECT_ROOT).as_posix()
                    save_make_generation(
                        session,
                        prompt_id=storage_id,
                        image_path=image_path,
                        request=request,
                        build=job.build,
                    )
        preview_urls = [url for _path, url, _sid in saved]
        image_ids = [sid for _path, _url, sid in saved]
        preview = preview_urls[0]
        store.complete(
            job_id,
            preview_url=preview,
            preview_urls=preview_urls,
            image_ids=image_ids,
            build=job.build if job else None,
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


def _run_make_job(
    job_id: str,
    build: dict[str, Any],
    *,
    base_url: str,
    wait_timeout: float,
    batch_size: int,
    client_id: str,
) -> None:
    store = job_store()
    stop_event = threading.Event()
    _register_stop_event(job_id, stop_event)
    try:
        _ensure_assets_on_comfyui(
            job_id,
            build,
            base_url=base_url,
            client_id=client_id,
            stop_event=stop_event,
        )
        if _job_is_cancelled(job_id):
            return

        workflow = build_result_to_make_lab(build, batch_size=batch_size)
        titles = workflow_node_titles(workflow)
        progress_plan = build_progress_plan(workflow, titles)
        store.attach_workflow_plan(
            job_id,
            workflow=workflow,
            node_titles=titles,
            progress_plan=progress_plan,
        )

        ws, ws_err = connect_comfyui_ws(client_id, base_url=base_url)
        comfy_prompt_id, _ = queue_prompt(workflow, base_url, client_id=client_id)
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
            base_url=base_url,
            stop_event=stop_event,
            match_prompt_id=comfy_prompt_id,
        )
        _finish_generation_job(
            job_id,
            comfy_prompt_id,
            base_url=base_url,
            wait_timeout=wait_timeout,
            stop_event=stop_event,
        )
    except JobCancelled:
        pass
    except Exception as exc:
        if not _job_is_cancelled(job_id):
            store.fail(job_id, str(exc))
    finally:
        stop_event.set()
        _unregister_stop_event(job_id)


def cancel_make_lab_job(job_id: str, *, base_url: str | None = None) -> bool:
    """Stop ComfyUI work for ``job_id`` and mark cancelled."""
    store = job_store()
    job = store.get(job_id)
    if job is None:
        return False
    resolved_base = base_url if base_url is not None else job.base_url

    targets = _cancel_targets_for(job_id)
    cancelled_any = False
    for pid in targets:
        _comfyui_stop_remote(pid, resolved_base)
    _signal_stop_event(job_id)
    if job.status not in ("complete", "cancelled"):
        store.cancel(job_id)
        remove_live_preview_files(job_id)
        cancelled_any = True
    elif job.status == "cancelled":
        cancelled_any = True
    return cancelled_any


def start_make_lab_job(
    build: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
    base_url: str | None = None,
    wait_timeout: float = 300.0,
    batch_size: int = 1,
) -> dict[str, Any]:
    """Queue Make workflow after optional asset download; return job id immediately."""
    resolved_base = _resolve_base(base_url)
    job_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    store = job_store()
    store.create(
        job_id,
        client_id,
        lab="make",
        base_url=resolved_base,
        build=build,
        request=request if request is not None else build.get("request"),
        workflow_node_count=0,
        node_titles={},
        progress_plan=build_progress_plan({}, node_titles={}),
    )
    threading.Thread(
        target=_run_make_job,
        kwargs={
            "job_id": job_id,
            "build": build,
            "base_url": resolved_base,
            "wait_timeout": wait_timeout,
            "batch_size": batch_size,
            "client_id": client_id,
        },
        daemon=True,
        name=f"comfyui-job-{job_id[:8]}",
    ).start()
    return {"prompt_id": job_id, "build": build, "batch_size": batch_size}


def _installed_checkpoint_names(base_url: str | None) -> frozenset[str] | None:
    """Checkpoint filenames on the ComfyUI host (``None`` when unreachable)."""
    from .client import list_checkpoints

    try:
        names = list_checkpoints(base_url)
    except (OSError, ComfyUIRequestError):
        return None
    if not names:
        return frozenset()
    return frozenset(names)


_CHECKPOINT_MISMATCH_MSG = "No dataset style matches a checkpoint installed on ComfyUI"


def composer_build_with_installed_checkpoints(
    session: Session,
    payload: composer.BuildPayload,
    *,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Build scene; filter styles by ComfyUI checkpoints when dataset rows match."""
    if base_url is not None:
        resolved_base = base_url
    else:
        try:
            resolved_base = load_comfyui_base_url()
        except RuntimeError:
            return composer.build(session, payload, installed_checkpoints=None)
    installed = _installed_checkpoint_names(resolved_base)
    if installed:
        try:
            return composer.build(session, payload, installed_checkpoints=installed)
        except ValueError as exc:
            if _CHECKPOINT_MISMATCH_MSG not in str(exc):
                raise
    return composer.build(session, payload, installed_checkpoints=None)


def start_make_generate(
    session: Session,
    payload: composer.BuildPayload,
    *,
    base_url: str | None = None,
    wait_timeout: float = 300.0,
) -> dict[str, Any]:
    """Build scene and queue a single ComfyUI job (client sends one request per slot)."""
    resolved_base = _resolve_base(base_url)
    maybe_free_memory_before_make(resolved_base)
    batch_size = payload.images
    build = composer_build_with_installed_checkpoints(
        session, payload, base_url=resolved_base
    )
    result = start_make_lab_job(
        build,
        request=build.get("request"),
        base_url=resolved_base,
        wait_timeout=wait_timeout,
        batch_size=batch_size,
    )
    prompt_id = result["prompt_id"]
    return {
        "prompt_id": prompt_id,
        "prompt_ids": [prompt_id],
        "generation_count": 1,
        "build": build,
    }
