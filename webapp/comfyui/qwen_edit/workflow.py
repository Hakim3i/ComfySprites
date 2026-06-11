"""Load and patch the Qwen Image Edit ComfyUI workflow."""

from __future__ import annotations

import copy
from typing import Any

from ..lora_loader_chain import apply_lora_loader_chain, rewire_lora_model_consumers
from ..make_lab.workflow_patch import _comfyui_seed
from ..pipeline_builder import build_pipeline

_QWEN_EDIT_UNET = "QWEN/qwen_image_edit_2511_fp8mixed.safetensors"
_QWEN_EDIT_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
_QWEN_EDIT_VAE = "qwen_image_vae.safetensors"
_QWEN_EDIT_LIGHTNING = "QWEN/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
_EXPORT_PREFIX = "Qwen_Edit"


def _blueprint() -> dict[str, Any]:
    from ..pipeline_builder import _load_pipeline_blueprint

    return _load_pipeline_blueprint("qwen_edit")


def qwen_edit_patch_roles() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_blueprint().get("patch_roles") or {}).items()}


QWEN_EDIT_EXPORT_NODE_ID = str(
    (_blueprint().get("outputs") or {}).get("image") or "export_image"
)

_QWEN_EDIT_NODES = qwen_edit_patch_roles()


def load_qwen_edit_workflow() -> dict[str, Any]:
    return copy.deepcopy(build_pipeline("qwen_edit").workflow)


def _loras_from_request(loras: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    skip = frozenset({"sdxl", "style", "refine", "character", "partner", "inference"})
    out: list[dict[str, Any]] = []
    for lora in loras or []:
        if not isinstance(lora, dict):
            continue
        kind = str(lora.get("kind") or "").strip().lower()
        if kind in skip:
            continue
        if (lora.get("filename") or "").strip():
            out.append(lora)
    return out


def _motion_loras(
    loras: list[dict[str, Any]] | None,
    build: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    from_request = _loras_from_request(loras)
    if from_request:
        return from_request
    if not build:
        return []
    qwen = build.get("qwen_edit") if isinstance(build.get("qwen_edit"), dict) else {}
    out: list[dict[str, Any]] = []
    for item in qwen.get("loras") or []:
        if isinstance(item, dict) and (item.get("filename") or "").strip():
            out.append(item)
    return out


def _prompt_from_build(build: dict[str, Any]) -> str:
    qwen = build.get("qwen_edit")
    if isinstance(qwen, dict):
        return str(qwen.get("prompt") or "").strip()
    return ""


def _resolved_path(model_paths: dict[str, str] | None, catalog_filename: str) -> str:
    if model_paths:
        hit = model_paths.get(catalog_filename)
        if hit:
            return hit
    return catalog_filename


def patch_qwen_edit_workflow(
    *,
    comfy_image_name: str,
    qwen_edit_prompt: str | None = None,
    loras: list[dict[str, Any]] | None = None,
    seed: int = -1,
    steps: int = 4,
    cfg: float = 1.0,
    image_strength: float = 1.0,
    shift: float = 3.1,
    build: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    model_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    workflow = load_qwen_edit_workflow()
    nodes = _QWEN_EDIT_NODES
    build = build or {}

    workflow[nodes["load_image"]]["inputs"]["image"] = comfy_image_name
    prompt = (qwen_edit_prompt or "").strip() or _prompt_from_build(build)
    workflow[nodes["positive"]]["inputs"]["prompt"] = prompt
    workflow[nodes["ksampler"]]["inputs"]["seed"] = _comfyui_seed(int(seed))
    workflow[nodes["ksampler"]]["inputs"]["steps"] = max(1, int(steps))
    workflow[nodes["ksampler"]]["inputs"]["cfg"] = float(cfg)
    workflow[nodes["model_sampling"]]["inputs"]["shift"] = float(shift)
    workflow[nodes["cfg_norm"]]["inputs"]["strength"] = float(image_strength)
    workflow[nodes["diffusion_model"]]["inputs"]["unet_name"] = _resolved_path(
        model_paths, _QWEN_EDIT_UNET
    )
    if "qwen_clip" in nodes:
        workflow[nodes["qwen_clip"]]["inputs"]["clip_name"] = _resolved_path(
            model_paths, _QWEN_EDIT_CLIP
        )
    if "qwen_vae" in nodes:
        workflow[nodes["qwen_vae"]]["inputs"]["vae_name"] = _resolved_path(
            model_paths, _QWEN_EDIT_VAE
        )
    if "lightning_lora" in nodes:
        workflow[nodes["lightning_lora"]]["inputs"]["lora_name"] = _resolved_path(
            model_paths, _QWEN_EDIT_LIGHTNING
        )

    effective_loras = _motion_loras(loras, build)
    model_out, _clip_out = apply_lora_loader_chain(
        workflow,
        tail_id=nodes["lora"],
        loras=effective_loras,
        model_source=[nodes["lightning_lora"], 0],
        clip_source=[nodes["qwen_clip"], 0],
        stack_prefix="qwen_edit_lora",
        title_prefix="Edit LoRA",
    )
    workflow[nodes["model_sampling"]]["inputs"]["model"] = model_out
    rewire_lora_model_consumers(
        workflow,
        model_ref=model_out,
        previous_model_nodes=[nodes["lora"], nodes["lightning_lora"]],
    )

    prefix = str((request or {}).get("export_prefix") or _EXPORT_PREFIX)
    workflow[nodes["export_image"]]["inputs"]["filename_prefix"] = prefix
    return workflow
