"""Build LoRA manifests for ComfyUI ensure-node injection."""

from __future__ import annotations

import json
from typing import Any

from ..env_settings import load_api_keys
from ..services.catalog.controlnet_types import controlnet_ensure_entry
from ..make.limits import MAKE_LAB_UPSCALE_MODEL_DEFAULT
from ..services.catalog.detailer_assets import detailer_ensure_entry
from ..services.catalog.upscale_models import upscale_ensure_entry
from .make_lab.compose import refine_enabled_from_request, resolve_upscale_timing
from .make_lab.detailers import (
    DETAILER_TIMING_DISABLED,
    detailers_from_request,
    load_detailer_settings,
    resolve_detailer_timing,
)
from .make_lab.workflow_patch import (
    make_lab_refine_loras_from_build,
    uses_separate_refine_model,
)
from .workflow import (
    make_lab_inference_loras_from_build,
    make_lab_loras_from_build,
    qwen_make_style_loras_from_build,
)


def tokens_for_comfyui() -> dict[str, str]:
    """API keys from ComfySprites Settings (workspace ``.env``)."""
    keys = load_api_keys()
    return {
        "civitai_token": keys.get("civitai_token") or "",
        "hf_token": keys.get("hf_token") or "",
    }


def _dedupe_by_filename(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = (item.get("filename") or "").strip()
        if not filename:
            continue
        key = filename.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_loras_by_filename(loras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_by_filename(loras)


def _checkpoint_manifest_entry(ckpt: dict[str, Any]) -> dict[str, Any] | None:
    filename = (ckpt.get("filename") or "").strip()
    if not filename:
        return None
    out: dict[str, Any] = {
        "filename": filename,
        "name": ckpt.get("name") or filename,
    }
    if ckpt.get("download_url"):
        out["download_url"] = ckpt["download_url"]
    if ckpt.get("version_id") is not None:
        out["version_id"] = ckpt["version_id"]
    if ckpt.get("model_id") is not None:
        out["model_id"] = ckpt["model_id"]
    if ckpt.get("civitai_url"):
        out["civitai_url"] = ckpt["civitai_url"]
    return out


def make_lab_checkpoints_manifest(build: dict[str, Any]) -> list[dict[str, Any]]:
    """SDXL checkpoint files for inference and optional separate refine stack."""
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    diffusion_make = isinstance(build.get("qwen_make"), dict) or isinstance(
        build.get("anima_make"), dict
    )
    entries: list[dict[str, Any]] = []
    if not diffusion_make:
        infer_ckpt = (
            sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
        )
        infer_entry = _checkpoint_manifest_entry(infer_ckpt)
        if infer_entry is not None:
            entries.append(infer_entry)
    if diffusion_make and not refine_enabled_from_request(request):
        return _dedupe_by_filename(entries)
    if uses_separate_refine_model(build):
        refine_sdxl = build.get("refine_sdxl")
        if isinstance(refine_sdxl, dict):
            refine_ckpt = refine_sdxl.get("checkpoint")
            if isinstance(refine_ckpt, dict):
                refine_entry = _checkpoint_manifest_entry(refine_ckpt)
                if refine_entry is not None:
                    entries.append(refine_entry)
    return _dedupe_by_filename(entries)


def checkpoints_json_for_manifest(checkpoints: list[dict[str, Any]]) -> str:
    return json.dumps(checkpoints, ensure_ascii=False)


def make_lab_loras_manifest(build: dict[str, Any]) -> list[dict[str, Any]]:
    """All SDXL LoRA files needed for inference + refine LoRA loader chains."""
    if isinstance(build.get("qwen_make"), dict) or isinstance(
        build.get("anima_make"), dict
    ):
        request = build.get("request") if isinstance(build.get("request"), dict) else {}
        if not refine_enabled_from_request(request):
            sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
            return _dedupe_loras_by_filename(qwen_make_style_loras_from_build(sdxl))
        refine_sdxl = build.get("refine_sdxl")
        if isinstance(refine_sdxl, dict):
            return _dedupe_loras_by_filename(
                make_lab_refine_loras_from_build(refine_sdxl, None)
            )
        return []
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    separate = uses_separate_refine_model(build)
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    loras = list(
        make_lab_inference_loras_from_build(
            sdxl, omit_style_lora=separate
        )
    )
    if refine_enabled_from_request(request):
        refine_sdxl = build.get("refine_sdxl")
        if isinstance(refine_sdxl, dict):
            loras.extend(make_lab_refine_loras_from_build(refine_sdxl, sdxl))
    return _dedupe_loras_by_filename(loras)


def loras_json_for_manifest(loras: list[dict[str, Any]]) -> str:
    return json.dumps(loras, ensure_ascii=False)


def make_lab_controlnets_manifest(build: dict[str, Any]) -> list[dict[str, Any]]:
    raw = build.get("controlnet") if isinstance(build.get("controlnet"), dict) else {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in raw:
        entry = controlnet_ensure_entry(str(key))
        if entry is None:
            continue
        filename = entry.get("filename") or ""
        if not filename or filename.lower() in seen:
            continue
        seen.add(filename.lower())
        out.append(entry)
    return out


def controlnets_json_for_manifest(controlnets: list[dict[str, Any]]) -> str:
    return json.dumps(controlnets, ensure_ascii=False)


def make_lab_upscalers_manifest(build: dict[str, Any]) -> list[dict[str, Any]]:
    """Upscale weight for the selected model when upscaling is enabled."""
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    if resolve_upscale_timing(request) == "disabled":
        return []
    model = (
        str(request.get("upscale_model") or "").strip()
        or MAKE_LAB_UPSCALE_MODEL_DEFAULT
    )
    entry = upscale_ensure_entry(model)
    if entry is None:
        return []
    return [entry]


def upscalers_json_for_manifest(upscalers: list[dict[str, Any]]) -> str:
    return json.dumps(upscalers, ensure_ascii=False)


def make_lab_detailer_assets_manifest(build: dict[str, Any]) -> list[dict[str, Any]]:
    """Ultralytics + SAM weights for enabled detailer regions."""
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    if (
        resolve_detailer_timing(request, separate_refine_model=False)
        == DETAILER_TIMING_DISABLED
    ):
        return []
    regions = detailers_from_request(request)
    if not regions:
        return []
    settings_regions = load_detailer_settings().get("regions") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for region_id in regions:
        cfg = settings_regions.get(region_id) or {}
        if not isinstance(cfg, dict):
            continue
        for field in ("detector_model", "sam_model"):
            model_path = str(cfg.get(field) or "").strip()
            if not model_path:
                continue
            key = model_path.lower()
            if key in seen:
                continue
            entry = detailer_ensure_entry(model_path)
            if entry is None:
                continue
            seen.add(key)
            out.append(entry)
    return out


def detailers_json_for_manifest(detailers: list[dict[str, Any]]) -> str:
    return json.dumps(detailers, ensure_ascii=False)


def diffusion_models_json_for_manifest(diffusion_models: list[dict[str, Any]]) -> str:
    return json.dumps(diffusion_models, ensure_ascii=False)


def text_encoders_json_for_manifest(text_encoders: list[dict[str, Any]]) -> str:
    return json.dumps(text_encoders, ensure_ascii=False)


def vae_json_for_manifest(vae_models: list[dict[str, Any]]) -> str:
    return json.dumps(vae_models, ensure_ascii=False)
