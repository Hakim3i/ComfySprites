"""Edit Lab: Qwen Image Edit generation."""

from __future__ import annotations

import base64
import binascii
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import PROJECT_ROOT
from ..config import EDIT_OUTPUT_DIR, EDIT_OUTPUT_URL_PREFIX
from ..db import session_scope
from ..db.models import EditGeneration, Generation, Lora
from ..env_settings import load_comfyui_base_url
from ..services.catalog.diffusion_models import diffusion_model_spec
from ..services.edit_generations import (
    resolve_source_image_path,
    save_edit_generation,
)
from ..services.qwen.build import (
    _lora_dict,
    build_qwen_edit_from_edit,
    build_qwen_edit_from_generation,
    resolve_qwen_edit_fields,
)
from .asset_inventory import resolve_diffusion_model_paths
from .client import (
    JobCancelled,
    collect_output_images,
    delete_queue_prompts,
    interrupt_prompt,
    queue_prompt,
    upload_image_bytes,
    wait_for_prompt,
)
from .diffusion_asset_preflight import ensure_diffusion_model_assets_on_comfyui
from .generate import (
    _cancel_targets_for,
    _job_is_cancelled,
    _register_stop_event,
    _signal_stop_event,
    _unregister_stop_event,
)
from .jobs import job_store
from .make_lab.rmbg import _instantiate_rmbg_node, load_rmbg_defaults
from .outputs import (
    download_fraction_from_parts,
    output_edit_name,
    remove_live_preview_files,
    save_all_output_images,
)
from .qwen_edit.progress import build_qwen_edit_progress_plan
from .qwen_edit.workflow import QWEN_EDIT_EXPORT_NODE_ID, patch_qwen_edit_workflow
from .ws_progress import connect_comfyui_ws, start_ws_progress_listener

_log = logging.getLogger(__name__)

_MAX_EDIT_PNG_BYTES = 16 * 1024 * 1024
_MAX_EDIT_PNG_DATA_URL_LEN = 22_000_000
_EPHEMERAL_GEN_PREFIX = "_gen_"

def _resolve_base(base_url: str | None = None) -> str:
    if base_url is not None:
        return base_url
    return load_comfyui_base_url()


def _comfyui_stop_remote(prompt_id: str, base_url: str | None) -> None:
    for name, call in (
        ("interrupt", lambda: interrupt_prompt(prompt_id, base_url)),
        ("delete_queue", lambda: delete_queue_prompts([prompt_id], base_url)),
    ):
        try:
            call()
        except Exception as exc:
            _log.warning("ComfyUI %s for %s failed: %s", name, prompt_id, exc)


def _upload_source_image(src_path: Path, *, base_url: str) -> str:
    return upload_image_bytes(src_path.read_bytes(), src_path.name, base_url=base_url)


def _lora_download_fields() -> tuple[str, ...]:
    return (
        "download_url",
        "download_fallback_url",
        "version_id",
        "model_id",
        "civitai_url",
    )


def _lora_rows_by_filename(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if not filename:
            continue
        out[filename.casefold()] = item
    return out


def _merge_lora_download_metadata(
    loras: list[dict[str, Any]],
    *sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Copy download fields from *sources* onto *loras* matched by filename."""
    by_name = _lora_rows_by_filename(
        [row for source in sources for row in source if isinstance(row, dict)]
    )
    merged: list[dict[str, Any]] = []
    for item in loras:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        source = by_name.get(str(row.get("filename") or "").strip().casefold()) or {}
        for field in _lora_download_fields():
            if not row.get(field) and source.get(field) is not None:
                row[field] = source[field]
        merged.append(row)
    return merged


def _loras_from_payload(payload: Any, build: dict[str, Any]) -> list[dict[str, Any]]:
    strengths = dict(getattr(payload, "lora_strengths", None) or {})
    qwen = build.get("qwen_edit") if isinstance(build.get("qwen_edit"), dict) else {}
    build_loras = [
        dict(item)
        for item in (qwen.get("loras") or [])
        if isinstance(item, dict)
    ]
    explicit = getattr(payload, "loras", None) or []
    if explicit:
        loras = [dict(x) for x in explicit if isinstance(x, dict)]
        loras = _merge_lora_download_metadata(loras, build_loras)
    else:
        loras = list(build_loras)
    for row in loras:
        role = str(row.get("kind") or "qwen_edit")
        if role in strengths:
            row["strength"] = float(strengths[role])
        elif "qwen_edit" in strengths:
            row["strength"] = float(strengths["qwen_edit"])
    return loras


def _lora_download_rows_from_db(session: Session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lora in session.scalars(select(Lora)):
        row = _lora_dict(lora)
        if row is None:
            continue
        if not (row.get("download_url") or row.get("version_id")):
            continue
        key = str(row.get("filename") or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _enrich_loras_for_download(
    session: Session,
    loras: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure animation LoRAs carry download metadata for asset preflight."""
    sources: list[dict[str, Any]] = []
    for row in loras:
        if row.get("download_url") or row.get("version_id"):
            continue
        filename = str(row.get("filename") or "").strip()
        if not filename:
            continue
        lora = session.scalar(select(Lora).where(Lora.filename == filename))
        if lora is not None:
            db_row = _lora_dict(lora)
            if db_row is not None:
                sources.append(db_row)
    sources.extend(_lora_download_rows_from_db(session))
    if not sources:
        return loras
    return _merge_lora_download_metadata(loras, sources)


def _finish_edit_job(
    job_id: str,
    comfy_prompt_id: str,
    *,
    base_url: str | None,
    wait_timeout: float,
    stop_event: threading.Event,
    source_prompt_id: str,
    source_kind: str,
    animation_slug: str | None,
    model_id: str,
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
        images = collect_output_images(history, node_ids=[QWEN_EDIT_EXPORT_NODE_ID])

        def _on_download_progress(fraction: float) -> None:
            store.set_download_progress(job_id, fraction)

        saved = save_all_output_images(
            history,
            job_id,
            base_url=base_url,
            images=images,
            on_download_progress=_on_download_progress,
            output_dir=EDIT_OUTPUT_DIR,
            url_prefix=EDIT_OUTPUT_URL_PREFIX,
        )
        if _job_is_cancelled(job_id):
            return
        job = store.get(job_id)
        if job and saved:
            path, url, storage_id = saved[0]
            image_path = path.relative_to(PROJECT_ROOT).as_posix()
            with session_scope() as session:
                save_edit_generation(
                    session,
                    prompt_id=storage_id,
                    image_path=image_path,
                    source_prompt_id=source_prompt_id,
                    source_kind=source_kind,
                    animation_slug=animation_slug,
                    request=dict(job.request or {}),
                    build=dict(job.build or {}),
                )
            store.complete(
                job_id,
                preview_url=url,
                preview_urls=[url],
                image_ids=[storage_id],
                build=job.build,
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


def _run_edit_job(
    job_id: str,
    *,
    source_path: Path,
    payload: Any,
    base_url: str,
    wait_timeout: float,
    client_id: str,
) -> None:
    store = job_store()
    stop_event = threading.Event()
    _register_stop_event(job_id, stop_event)
    model_id = str(getattr(payload, "model_id", "qwen_edit_2511") or "qwen_edit_2511")
    try:
        source_kind = str(getattr(payload, "source_kind", "make") or "make")
        with session_scope() as session:
            if source_kind == "edit":
                source = session.get(EditGeneration, payload.source_prompt_id)
                if source is None:
                    raise ValueError(
                        f"Unknown or missing edit source {payload.source_prompt_id!r}"
                    )
                build = build_qwen_edit_from_edit(
                    session,
                    source,
                    animation_slug=getattr(payload, "animation_slug", None),
                    lora_strengths=dict(
                        getattr(payload, "lora_strengths", None) or {}
                    ),
                )
            else:
                source = session.get(Generation, payload.source_prompt_id)
                if source is None:
                    raise ValueError(
                        f"Unknown or missing source still {payload.source_prompt_id!r}"
                    )
                build = build_qwen_edit_from_generation(
                    session,
                    source,
                    animation_slug=getattr(payload, "animation_slug", None),
                    lora_strengths=dict(
                        getattr(payload, "lora_strengths", None) or {}
                    ),
                )
            loras = _enrich_loras_for_download(
                session,
                _loras_from_payload(payload, build),
            )
        ensure_diffusion_model_assets_on_comfyui(
            job_id,
            model_id,
            base_url=base_url,
            client_id=client_id,
            stop_event=stop_event,
            extra_loras=loras,
        )
        if _job_is_cancelled(job_id):
            return

        upload_name = _upload_source_image(source_path, base_url=base_url)
        fields = resolve_qwen_edit_fields(
            build,
            qwen_edit_prompt=getattr(payload, "qwen_edit_prompt", None),
            qwen_edit_negative=getattr(payload, "qwen_edit_negative", None),
        )
        job = store.get(job_id)
        request = dict(job.request or {}) if job else {}
        store.set_build(job_id, build)
        model_paths = resolve_diffusion_model_paths(model_id, base_url)
        workflow = patch_qwen_edit_workflow(
            comfy_image_name=upload_name,
            qwen_edit_prompt=fields.get("qwen_edit_prompt"),
            qwen_edit_negative=fields.get("qwen_edit_negative"),
            loras=loras,
            seed=int(getattr(payload, "seed", -1)),
            steps=int(getattr(payload, "steps", 4) or 4),
            cfg=float(getattr(payload, "cfg", 1.0) or 1.0),
            image_strength=float(getattr(payload, "image_strength", 1.0) or 1.0),
            shift=float(getattr(payload, "shift", 3.1) or 3.1),
            build=build,
            request=request,
            model_paths=model_paths,
        )
        titles = {
            nid: str((node.get("_meta") or {}).get("title") or nid)
            for nid, node in workflow.items()
            if isinstance(node, dict)
        }
        progress_plan = build_qwen_edit_progress_plan(workflow, titles)
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
        _finish_edit_job(
            job_id,
            comfy_prompt_id,
            base_url=base_url,
            wait_timeout=wait_timeout,
            stop_event=stop_event,
            source_prompt_id=str(getattr(payload, "source_prompt_id", "")),
            source_kind=str(getattr(payload, "source_kind", "make")),
            animation_slug=getattr(payload, "animation_slug", None),
            model_id=model_id,
        )
    except JobCancelled:
        pass
    except Exception as exc:
        if not _job_is_cancelled(job_id):
            store.fail(job_id, str(exc))
    finally:
        _unlink_ephemeral_gen(source_path)
        stop_event.set()
        _unregister_stop_event(job_id)


def cancel_edit_job(job_id: str, *, base_url: str | None = None) -> bool:
    store = job_store()
    job = store.get(job_id)
    if job is None:
        return False
    resolved_base = base_url if base_url is not None else job.base_url
    for pid in _cancel_targets_for(job_id):
        _comfyui_stop_remote(pid, resolved_base)
    _signal_stop_event(job_id)
    if job.status not in ("complete", "cancelled"):
        store.cancel(job_id)
        remove_live_preview_files(job_id)
        return True
    return job.status == "cancelled"


def _resolve_generate_source_path(session: Session, payload: Any) -> Path:
    data_url = (getattr(payload, "image_data_url", None) or "").strip()
    if data_url:
        data = _decode_png_data_url(data_url)
        EDIT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = EDIT_OUTPUT_DIR / f"_gen_{uuid.uuid4().hex}.png"
        path.write_bytes(data)
        return path
    source_kind = str(getattr(payload, "source_kind", "make") or "make")
    return resolve_source_image_path(
        session,
        source_prompt_id=payload.source_prompt_id,
        source_kind=source_kind,
    )


def start_edit_generate(session: Session, payload: Any) -> dict[str, Any]:
    model_id = str(getattr(payload, "model_id", "qwen_edit_2511") or "qwen_edit_2511")
    spec = diffusion_model_spec(model_id)
    if spec is None or spec.engine != "qwen_edit":
        raise ValueError(f"Edit generate supports Qwen edit models only (got {model_id!r})")

    source_path = _resolve_generate_source_path(session, payload)
    resolved_base = _resolve_base()
    job_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    request = _sanitize_edit_request(
        payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)
    )

    store = job_store()
    store.create(
        job_id,
        client_id,
        lab="edit",
        base_url=resolved_base,
        build=None,
        request=request,
        workflow_node_count=0,
        node_titles={},
        progress_plan=build_qwen_edit_progress_plan({}, node_titles={}),
    )
    threading.Thread(
        target=_run_edit_job,
        kwargs={
            "job_id": job_id,
            "source_path": source_path,
            "payload": payload,
            "base_url": resolved_base,
            "wait_timeout": 600.0,
            "client_id": client_id,
        },
        daemon=True,
        name=f"edit-{job_id[:8]}",
    ).start()
    return {"prompt_id": job_id, "request": request}


def _sanitize_edit_request(request: dict[str, Any]) -> dict[str, Any]:
    out = dict(request)
    out.pop("image_data_url", None)
    return out


def _is_ephemeral_gen_path(path: Path) -> bool:
    try:
        return (
            path.name.startswith(_EPHEMERAL_GEN_PREFIX)
            and path.parent.resolve() == EDIT_OUTPUT_DIR.resolve()
        )
    except OSError:
        return False


def _unlink_ephemeral_gen(path: Path) -> None:
    if not _is_ephemeral_gen_path(path):
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("Failed to remove ephemeral edit source %s: %s", path, exc)


def _decode_png_data_url(
    data_url: str,
    *,
    max_bytes: int = _MAX_EDIT_PNG_BYTES,
) -> bytes:
    raw = (data_url or "").strip()
    if not raw.startswith("data:image/png;base64,"):
        raise ValueError("Expected data:image/png;base64,…")
    if len(raw) > _MAX_EDIT_PNG_DATA_URL_LEN:
        raise ValueError(
            f"image_data_url exceeds maximum length ({_MAX_EDIT_PNG_DATA_URL_LEN})"
        )
    payload = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid base64 in image_data_url") from exc
    if len(data) > max_bytes:
        raise ValueError(f"Decoded image exceeds maximum size ({max_bytes} bytes)")
    return data


def save_canvas_edit(
    session: Session,
    *,
    source_prompt_id: str,
    source_kind: str,
    image_data_url: str,
    animation_slug: str | None = None,
    build: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = _decode_png_data_url(image_data_url)
    prompt_id = str(uuid.uuid4())
    EDIT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_name = output_edit_name(prompt_id, ext=".png")
    dest = EDIT_OUTPUT_DIR / out_name
    dest.write_bytes(data)
    image_path = dest.relative_to(PROJECT_ROOT).as_posix()
    req = dict(request or {})
    req.setdefault("source_prompt_id", source_prompt_id)
    req.setdefault("source_kind", source_kind)
    req.setdefault("animation_slug", animation_slug)
    req["canvas_save"] = True
    save_edit_generation(
        session,
        prompt_id=prompt_id,
        image_path=image_path,
        source_prompt_id=source_prompt_id,
        source_kind=source_kind,
        animation_slug=animation_slug,
        request=req,
        build=dict(build or {}),
    )
    url = f"{EDIT_OUTPUT_URL_PREFIX}/{out_name}"
    return {"prompt_id": prompt_id, "image_url": url, "image_path": image_path}


def _build_rmbg_workflow(
    comfy_image_name: str,
    *,
    background: str = "Alpha",
    background_color: str = "#000000",
) -> dict[str, Any]:
    load_id = "load_image"
    rmbg_id = "rmbg"
    save_id = "export_image"
    settings = load_rmbg_defaults()
    settings["background"] = background
    settings["background_color"] = background_color
    workflow = {
        load_id: {
            "class_type": "LoadImage",
            "_meta": {"title": "Load Image"},
            "inputs": {"image": comfy_image_name},
        },
        rmbg_id: _instantiate_rmbg_node([load_id, 0], settings),
        save_id: {
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
            "inputs": {
                "filename_prefix": "Edit_RMBG",
                "images": [rmbg_id, 0],
            },
        },
    }
    return workflow


def _edit_root_source_refs(payload: Any) -> tuple[str, str]:
    """Pinned source for saved edit metadata (regenerate always uses this image)."""
    root_id = str(
        getattr(payload, "root_source_prompt_id", None)
        or getattr(payload, "source_prompt_id", "")
    ).strip()
    root_kind = str(
        getattr(payload, "root_source_kind", None)
        or getattr(payload, "source_kind", "make")
        or "make"
    )
    return root_id, root_kind


def start_edit_rmbg(session: Session, payload: Any) -> dict[str, Any]:
    source_kind = str(getattr(payload, "source_kind", "make") or "make")
    source_path = resolve_source_image_path(
        session,
        source_prompt_id=payload.source_prompt_id,
        source_kind=source_kind,
    )
    root_source_prompt_id, root_source_kind = _edit_root_source_refs(payload)
    resolved_base = _resolve_base()
    job_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    request = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)
    bg = str(getattr(payload, "background", "transparent") or "transparent")
    bg_color = str(getattr(payload, "background_color", "#000000") or "#000000")
    rmbg_bg = "Alpha" if bg == "transparent" else "Color"
    rmbg_color = bg_color if rmbg_bg == "Color" else "#000000"

    store = job_store()
    store.create(
        job_id,
        client_id,
        lab="edit",
        base_url=resolved_base,
        build=None,
        request=request,
        workflow_node_count=0,
        node_titles={},
        progress_plan=build_qwen_edit_progress_plan({}, node_titles={}),
    )

    def _run() -> None:
        stop_event = threading.Event()
        _register_stop_event(job_id, stop_event)
        try:
            upload_name = _upload_source_image(source_path, base_url=resolved_base)
            workflow = _build_rmbg_workflow(
                upload_name,
                background=rmbg_bg,
                background_color=rmbg_color,
            )
            ws, ws_err = connect_comfyui_ws(client_id, base_url=resolved_base)
            comfy_prompt_id, _ = queue_prompt(workflow, resolved_base, client_id=client_id)
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
            _finish_edit_job(
                job_id,
                comfy_prompt_id,
                base_url=resolved_base,
                wait_timeout=300.0,
                stop_event=stop_event,
                source_prompt_id=root_source_prompt_id,
                source_kind=root_source_kind,
                animation_slug=getattr(payload, "animation_slug", None),
                model_id="rmbg",
            )
        except Exception as exc:
            if not _job_is_cancelled(job_id):
                store.fail(job_id, str(exc))
        finally:
            stop_event.set()
            _unregister_stop_event(job_id)

    threading.Thread(target=_run, daemon=True, name=f"edit-rmbg-{job_id[:8]}").start()
    return {"prompt_id": job_id, "request": request}
