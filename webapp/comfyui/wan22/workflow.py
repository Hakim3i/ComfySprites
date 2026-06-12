"""Load and patch the Wan 2.2 i2v ComfyUI workflow."""

from __future__ import annotations

import copy
from typing import Any

from ..lora_loader_chain import apply_lora_loader_model_only_chain
from ..pipeline_builder import _instantiate_node, build_pipeline
from ...services.catalog.diffusion_models import diffusion_model_spec
from ...services.ltx.render import is_animate_video_lora_kind

_WAN_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
_WAN_VAE = "wan_2.1_vae.safetensors"

_WAN_I2V_ROLE = "wan_i2v"
_FFLF_END_LOAD_ROLE = "load_end_image"


def _blueprint() -> dict[str, Any]:
    from ..pipeline_builder import _load_pipeline_blueprint

    return _load_pipeline_blueprint("wan22")


def wan22_patch_roles() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_blueprint().get("patch_roles") or {}).items()}


WAN22_VIDEO_OUTPUT_NODE_ID = str(
    (_blueprint().get("outputs") or {}).get("video") or "save_video"
)

_WAN22_NODES = wan22_patch_roles()


def load_wan22_workflow() -> dict[str, Any]:
    return copy.deepcopy(build_pipeline("wan22").workflow)


def _resolved_path(model_paths: dict[str, str] | None, catalog_filename: str) -> str:
    if model_paths:
        hit = model_paths.get(catalog_filename)
        if hit:
            return hit
    return catalog_filename


def _unet_filenames(model_id: str) -> tuple[str, str]:
    spec = diffusion_model_spec(model_id)
    if spec is None:
        raise ValueError(f"Unknown Wan model {model_id!r}")
    high = ""
    low = ""
    for asset in spec.assets:
        if asset.folder != "diffusion_models":
            continue
        name = asset.filename.upper()
        if "HIGH" in name and not high:
            high = asset.filename
        elif "LOW" in name and not low:
            low = asset.filename
    if not high or not low:
        raise ValueError(f"Wan model {model_id!r} missing HIGH/LOW UNET assets")
    return high, low


def _wan_loras_for_pass(
    loras: list[dict[str, Any]] | None,
    *,
    pass_role: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in loras or []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        if not is_animate_video_lora_kind(kind):
            continue
        base = kind.split("_", 1)[-1] if "_" in kind else kind
        if base != pass_role:
            continue
        if not (row.get("filename") or "").strip():
            continue
        out.append(dict(row))
    return out


def _apply_fflf_end_frame(
    workflow: dict[str, Any],
    *,
    end_comfy_image_name: str,
) -> None:
    end_name = (end_comfy_image_name or "").strip()
    if not end_name:
        return
    if _WAN_I2V_ROLE not in workflow:
        raise ValueError(f"Wan workflow missing {_WAN_I2V_ROLE!r}")

    role_to_id = {role: role for role in workflow}
    workflow[_FFLF_END_LOAD_ROLE] = _instantiate_node(
        "wan22", _FFLF_END_LOAD_ROLE, role_to_id
    )
    workflow[_FFLF_END_LOAD_ROLE]["inputs"]["image"] = end_name

    node = workflow[_WAN_I2V_ROLE]
    node["class_type"] = "WanFirstLastFrameToVideo"
    meta = node.setdefault("_meta", {})
    meta["title"] = "WanFirstLastFrameToVideo"
    node.setdefault("inputs", {})["end_image"] = [_FFLF_END_LOAD_ROLE, 0]


def patch_wan22_workflow(
    *,
    comfy_image_name: str,
    model: str,
    width: int,
    height: int,
    length_seconds: int,
    fps: int,
    seed: int,
    cfg: float,
    steps: int,
    shift: float,
    loras: list[dict[str, Any]] | None,
    build: dict[str, Any],
    positive_text: str | None = None,
    negative_text: str | None = None,
    end_comfy_image_name: str | None = None,
    request: dict[str, Any] | None = None,
    model_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    del build, request  # reserved for future export hooks
    workflow = load_wan22_workflow()
    nodes = _WAN22_NODES

    high_unet, low_unet = _unet_filenames(model)
    workflow[nodes["unet_high"]]["inputs"]["unet_name"] = _resolved_path(
        model_paths, high_unet
    )
    workflow[nodes["unet_low"]]["inputs"]["unet_name"] = _resolved_path(
        model_paths, low_unet
    )
    workflow[nodes["clip"]]["inputs"]["clip_name"] = _resolved_path(
        model_paths, _WAN_CLIP
    )
    workflow[nodes["vae"]]["inputs"]["vae_name"] = _resolved_path(
        model_paths, _WAN_VAE
    )

    workflow[nodes["load_image"]]["inputs"]["image"] = comfy_image_name
    workflow[nodes["wan_i2v"]]["inputs"]["width"] = max(1, int(width))
    workflow[nodes["wan_i2v"]]["inputs"]["height"] = max(1, int(height))
    workflow[nodes["positive"]]["inputs"]["text"] = (positive_text or "").strip()
    workflow[nodes["negative"]]["inputs"]["text"] = (negative_text or "").strip()

    frame_count = max(1, int(length_seconds) * max(1, int(fps)) + 1)
    workflow[nodes["wan_i2v"]]["inputs"]["length"] = frame_count
    workflow[nodes["create_video"]]["inputs"]["fps"] = max(1, int(fps))

    workflow["model_sampling_high"]["inputs"]["shift"] = float(shift)
    workflow["model_sampling_low"]["inputs"]["shift"] = float(shift)

    step_count = max(2, int(steps))
    if step_count % 2 != 0:
        step_count += 1
    mid = step_count // 2
    for role in ("sampler_high", "sampler_low"):
        sampler = workflow[role]["inputs"]
        sampler["steps"] = step_count
        sampler["cfg"] = float(cfg)
    workflow["sampler_high"]["inputs"]["end_at_step"] = mid
    workflow["sampler_low"]["inputs"]["start_at_step"] = mid
    workflow["sampler_low"]["inputs"]["end_at_step"] = step_count

    resolved_seed = int(seed) if int(seed) >= 0 else 0
    workflow["sampler_high"]["inputs"]["noise_seed"] = resolved_seed

    high_model = apply_lora_loader_model_only_chain(
        workflow,
        tail_id="lora_high",
        loras=_wan_loras_for_pass(loras, pass_role="wan_high"),
        model_source=[nodes["unet_high"], 0],
        stack_prefix="wan22_lora_high",
        title_prefix="Wan High LoRA",
    )
    workflow["model_sampling_high"]["inputs"]["model"] = high_model
    low_model = apply_lora_loader_model_only_chain(
        workflow,
        tail_id="lora_low",
        loras=_wan_loras_for_pass(loras, pass_role="wan_low"),
        model_source=[nodes["unet_low"], 0],
        stack_prefix="wan22_lora_low",
        title_prefix="Wan Low LoRA",
    )
    workflow["model_sampling_low"]["inputs"]["model"] = low_model

    if (end_comfy_image_name or "").strip():
        _apply_fflf_end_frame(
            workflow,
            end_comfy_image_name=str(end_comfy_image_name).strip(),
        )

    return workflow
