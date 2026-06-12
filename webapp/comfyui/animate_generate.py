"""Animate Lab: LTX / Wan image-to-video generation."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy.orm import Session

from .. import PROJECT_ROOT
from ..db import session_scope
from ..db.models import EditGeneration, Generation
from ..env_settings import load_comfyui_base_url
from ..services.catalog.diffusion_models import diffusion_model_spec
from ..services.edit_generations import resolve_source_image_path
from ..services.ltx.build import (
    build_ltx_from_edit,
    build_ltx_from_generation,
    resolve_ltx_fields,
    resolve_wan_fields,
)
from ..services.video_generations import save_video_generation
from .asset_inventory import resolve_diffusion_model_paths
from .client import (
    JobCancelled,
    collect_output_videos,
    delete_queue_prompts,
    interrupt_prompt,
    queue_prompt,
    upload_image_bytes,
    wait_for_prompt,
)
from .diffusion_asset_preflight import ensure_diffusion_model_assets_on_comfyui
from .edit_generate import _enrich_loras_for_download, _merge_lora_download_metadata
from .jobs import job_store
from .ltx_studio.workflow import (
    VIDEO_STUDIO_COMBINE_NODE_ID,
    merge_ltx_loras,
    patch_ltx_studio_workflow,
)
from .ltx_studio.progress import build_ltx_progress_plan
from .wan22.workflow import WAN22_VIDEO_OUTPUT_NODE_ID, patch_wan22_workflow
from .wan22.progress import build_wan22_progress_plan
from .outputs import (
    download_fraction_from_parts,
    remove_live_preview_files,
    save_all_output_videos,
)
from .ws_progress import connect_comfyui_ws, start_ws_progress_listener
from .generate import (
    _cancel_targets_for,
    _job_is_cancelled,
    _register_stop_event,
    _signal_stop_event,
    _unregister_stop_event,
)

_log = logging.getLogger(__name__)

_SUPPORTED_ENGINES = frozenset({"ltx23", "wan22"})


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


def _upload_source_path(src_path, *, base_url: str) -> str:
    return upload_image_bytes(src_path.read_bytes(), src_path.name, base_url=base_url)


def _resolve_animate_build(session: Session, payload: Any) -> dict[str, Any]:
    source_kind = str(getattr(payload, "source_kind", "make") or "make")
    style_slug = getattr(payload, "style_slug", None)
    animation_slug = getattr(payload, "animation_slug", None)
    lora_strengths = dict(getattr(payload, "lora_strengths", None) or {})
    if source_kind == "edit":
        source = session.get(EditGeneration, payload.source_prompt_id)
        if source is None:
            raise ValueError(f"Unknown or missing edit source {payload.source_prompt_id!r}")
        return build_ltx_from_edit(
            session,
            source,
            style_slug=style_slug,
            animation_slug=animation_slug,
            lora_strengths=lora_strengths,
        )
    source = session.get(Generation, payload.source_prompt_id)
    if source is None:
        raise ValueError(f"Unknown or missing source still {payload.source_prompt_id!r}")
    return build_ltx_from_generation(
        session,
        source,
        style_slug=style_slug,
        animation_slug=animation_slug,
        lora_strengths=lora_strengths,
    )


def _dims_from_build(build: dict[str, Any], width: int | None, height: int | None) -> tuple[int, int]:
    if width and height:
        return max(1, int(width)), max(1, int(height))
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    w = int(sdxl.get("width") or 832)
    h = int(sdxl.get("height") or 1216)
    return max(1, w), max(1, h)


def _build_lora_rows(build: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block_key in ("ltx", "wan"):
        block = build.get(block_key)
        if not isinstance(block, dict):
            continue
        for item in block.get("loras") or []:
            if isinstance(item, dict):
                rows.append(dict(item))
    return rows


def _loras_from_payload(payload: Any, build: dict[str, Any]) -> list[dict[str, Any]]:
    from ..services.ltx.render import is_animate_video_lora_kind

    build_loras = _build_lora_rows(build)
    explicit = getattr(payload, "loras", None) or []
    if explicit:
        out: list[dict[str, Any]] = []
        for row in explicit:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or "ltx").strip().lower()
            if not is_animate_video_lora_kind(kind):
                continue
            if not (row.get("filename") or "").strip():
                continue
            out.append(dict(row))
        return _merge_lora_download_metadata(out, build_loras)
    strengths = dict(getattr(payload, "lora_strengths", None) or {})
    ltx = build.get("ltx") if isinstance(build.get("ltx"), dict) else {}
    loras = []
    for item in ltx.get("loras") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        kind = str(row.get("kind") or "ltx")
        if kind in strengths:
            row["strength"] = float(strengths[kind])
        elif kind.startswith("style_") or kind.startswith("animation_"):
            base = kind.split("_", 1)[-1]
            if base in strengths:
                row["strength"] = float(strengths[base])
        elif "ltx" in strengths:
            row["strength"] = float(strengths["ltx"])
        loras.append(row)
    return loras


def _setting_or_default(
    value: Any,
    *,
    defaults: dict[str, Any],
    key: str,
    fallback: int | float,
) -> int | float:
    if value is not None:
        return value
    hit = defaults.get(key)
    if hit is not None:
        return hit
    return fallback


def _finish_animate_job(
    job_id: str,
    comfy_prompt_id: str,
    *,
    base_url: str | None,
    wait_timeout: float,
    stop_event: threading.Event,
    source_prompt_id: str,
    model_id: str,
    output_node_id: str = VIDEO_STUDIO_COMBINE_NODE_ID,
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
        videos = collect_output_videos(history, node_ids=[output_node_id])

        def _on_download_progress(fraction: float) -> None:
            store.set_download_progress(job_id, fraction)

        saved = save_all_output_videos(
            history,
            job_id,
            base_url=base_url,
            videos=videos,
            on_download_progress=_on_download_progress,
        )
        if _job_is_cancelled(job_id):
            return
        job = store.get(job_id)
        if job and saved:
            path, url, storage_id = saved[0]
            video_path = path.relative_to(PROJECT_ROOT).as_posix()
            with session_scope() as session:
                save_video_generation(
                    session,
                    prompt_id=storage_id,
                    video_path=video_path,
                    source_prompt_id=source_prompt_id,
                    model_id=model_id,
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


def _run_animate_job(
    job_id: str,
    *,
    payload: Any,
    base_url: str,
    wait_timeout: float,
    client_id: str,
) -> None:
    store = job_store()
    stop_event = threading.Event()
    _register_stop_event(job_id, stop_event)
    model_id = str(getattr(payload, "model_id", "ltx23_eros") or "ltx23_eros")
    spec = diffusion_model_spec(model_id)
    engine = spec.engine if spec else "ltx23"
    defaults = dict(spec.default_settings) if spec else {}
    try:
        with session_scope() as session:
            build = _resolve_animate_build(session, payload)
            source_path = resolve_source_image_path(
                session,
                source_prompt_id=payload.source_prompt_id,
                source_kind=str(getattr(payload, "source_kind", "make") or "make"),
            )
            loras = _enrich_loras_for_download(
                session,
                _loras_from_payload(payload, build),
            )
        preflight_loras = (
            merge_ltx_loras(
                loras,
                use_sulphur_experimental=bool(
                    getattr(payload, "use_sulphur_experimental_lora", False)
                ),
                build=build,
            )
            if engine == "ltx23"
            else loras
        )
        ensure_diffusion_model_assets_on_comfyui(
            job_id,
            model_id,
            base_url=base_url,
            client_id=client_id,
            stop_event=stop_event,
            extra_loras=preflight_loras,
            build=build,
        )
        if _job_is_cancelled(job_id):
            return

        upload_name = _upload_source_path(source_path, base_url=base_url)
        end_upload_name: str | None = None
        end_source_id = (getattr(payload, "end_source_prompt_id", None) or "").strip()
        if end_source_id:
            end_kind = str(getattr(payload, "end_source_kind", "make") or "make")
            with session_scope() as session:
                end_path = resolve_source_image_path(
                    session,
                    source_prompt_id=end_source_id,
                    source_kind=end_kind,
                )
            end_upload_name = _upload_source_path(end_path, base_url=base_url)

        width, height = _dims_from_build(
            build, getattr(payload, "width", None), getattr(payload, "height", None)
        )
        job = store.get(job_id)
        request = dict(job.request or {}) if job else {}
        store.set_build(job_id, build)
        model_paths = resolve_diffusion_model_paths(model_id, base_url)

        steps = int(
            _setting_or_default(
                getattr(payload, "steps", None),
                defaults=defaults,
                key="steps",
                fallback=12 if engine == "ltx23" else 4,
            )
        )
        shift = float(
            _setting_or_default(
                getattr(payload, "shift", None),
                defaults=defaults,
                key="shift",
                fallback=1.0 if engine == "ltx23" else 5.0,
            )
        )

        if engine == "wan22":
            wan_fields = resolve_wan_fields(
                build,
                positive_override=getattr(payload, "ltx_caption", None),
            )
            workflow = patch_wan22_workflow(
                comfy_image_name=upload_name,
                model=model_id,
                width=width,
                height=height,
                length_seconds=int(getattr(payload, "length_seconds", 5) or 5),
                fps=int(getattr(payload, "fps", 16) or 16),
                seed=int(getattr(payload, "seed", -1)),
                cfg=float(getattr(payload, "cfg", 1.0) or 1.0),
                steps=steps,
                shift=shift,
                loras=loras,
                build=build,
                positive_text=wan_fields.get("positive"),
                negative_text=wan_fields.get("negative"),
                end_comfy_image_name=end_upload_name,
                request=request,
                model_paths=model_paths,
            )
            progress_builder = build_wan22_progress_plan
            output_node_id = WAN22_VIDEO_OUTPUT_NODE_ID
        else:
            ltx_fields = resolve_ltx_fields(
                build,
                ltx_caption=getattr(payload, "ltx_caption", None),
                ltx_video_negative=getattr(payload, "ltx_video_negative", None),
                ltx_audio_negative=getattr(payload, "ltx_audio_negative", None),
            )
            effective_loras = merge_ltx_loras(
                loras,
                use_sulphur_experimental=bool(
                    getattr(payload, "use_sulphur_experimental_lora", False)
                ),
                build=build,
            )
            workflow = patch_ltx_studio_workflow(
                comfy_image_name=upload_name,
                model=model_id,
                width=width,
                height=height,
                length_seconds=int(getattr(payload, "length_seconds", 5) or 5),
                fps=int(getattr(payload, "fps", 24) or 24),
                seed=int(getattr(payload, "seed", -1)),
                image_strength=float(getattr(payload, "image_strength", 0.95) or 0.95),
                audio_volume=int(getattr(payload, "audio_volume", 100) or 100),
                cfg=float(getattr(payload, "cfg", 1.0) or 1.0),
                steps=steps,
                shift=shift,
                loras=effective_loras,
                build=build,
                ltx_caption=ltx_fields.get("ltx_caption"),
                ltx_video_negative=ltx_fields.get("ltx_video_negative"),
                ltx_audio_negative=ltx_fields.get("ltx_audio_negative"),
                end_comfy_image_name=end_upload_name,
                end_frame_strength=float(getattr(payload, "end_frame_strength", 1.0) or 1.0),
                request=request,
                model_paths=model_paths,
            )
            progress_builder = build_ltx_progress_plan
            output_node_id = VIDEO_STUDIO_COMBINE_NODE_ID

        titles = {
            nid: str((node.get("_meta") or {}).get("title") or nid)
            for nid, node in workflow.items()
            if isinstance(node, dict)
        }
        progress_plan = progress_builder(workflow, titles)
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
        _finish_animate_job(
            job_id,
            comfy_prompt_id,
            base_url=base_url,
            wait_timeout=wait_timeout,
            stop_event=stop_event,
            source_prompt_id=payload.source_prompt_id,
            model_id=model_id,
            output_node_id=output_node_id,
        )
    except JobCancelled:
        pass
    except Exception as exc:
        if not _job_is_cancelled(job_id):
            store.fail(job_id, str(exc))
    finally:
        stop_event.set()
        _unregister_stop_event(job_id)


def cancel_animate_job(job_id: str, *, base_url: str | None = None) -> bool:
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


def start_animate_generate(session: Session, payload: Any) -> dict[str, Any]:
    model_id = str(getattr(payload, "model_id", "ltx23_eros") or "ltx23_eros")
    spec = diffusion_model_spec(model_id)
    if spec is None or spec.engine not in _SUPPORTED_ENGINES:
        raise ValueError(
            f"Animate generate supports LTX and Wan models only (got {model_id!r})"
        )

    source_kind = str(getattr(payload, "source_kind", "make") or "make")
    resolve_source_image_path(
        session,
        source_prompt_id=payload.source_prompt_id,
        source_kind=source_kind,
    )
    end_source_id = (getattr(payload, "end_source_prompt_id", None) or "").strip()
    if end_source_id:
        end_kind = str(getattr(payload, "end_source_kind", "make") or "make")
        resolve_source_image_path(
            session,
            source_prompt_id=end_source_id,
            source_kind=end_kind,
        )

    resolved_base = _resolve_base()
    job_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    request = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload)

    store = job_store()
    store.create(
        job_id,
        client_id,
        lab="animate",
        base_url=resolved_base,
        build=None,
        request=request,
        workflow_node_count=0,
        node_titles={},
        progress_plan=build_ltx_progress_plan({}, node_titles={}),
    )
    threading.Thread(
        target=_run_animate_job,
        kwargs={
            "job_id": job_id,
            "payload": payload,
            "base_url": resolved_base,
            "wait_timeout": 1200.0,
            "client_id": client_id,
        },
        daemon=True,
        name=f"animate-{job_id[:8]}",
    ).start()
    return {"prompt_id": job_id, "request": request}
