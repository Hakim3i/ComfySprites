"""Shared Make Lab workflow patch helpers (engine-agnostic)."""

from __future__ import annotations

import random
import re
from typing import Any

from ...make.limits import (
    MAKE_LAB_REFINE_DENOISE_DEFAULT,
    MAKE_LAB_REFINE_STEPS_DEFAULT,
    MAKE_LAB_UPSCALE_BY_DEFAULT,
    MAKE_LAB_UPSCALE_MODEL_DEFAULT,
)
from ..workflow_builder import registry_nodes
from .compose import upscale_output_dimensions

_COMFYUI_RANDOM_SEED_SENTINEL = -1

_MAKE_LAB_NODES: dict[str, str] = registry_nodes()

REFINE_STACK_REWIRE = {
    "model": _MAKE_LAB_NODES["refine_lora"],
    "positive": _MAKE_LAB_NODES["refine_positive"],
    "negative": _MAKE_LAB_NODES["refine_negative"],
}

_MAKE_LAB_REFINE_LORA_KINDS = ("style", "character")

_SAMPLER_MAP: dict[str, str] = {
    "euler": "euler",
    "euler a": "euler_ancestral",
    "euler ancestral": "euler_ancestral",
    "dpm++ 2m": "dpmpp_2m",
    "dpm++ 2m karras": "dpmpp_2m",
    "dpm++ sde": "dpmpp_sde",
    "dpm++ sde karras": "dpmpp_sde",
    "dpm++ 2s a": "dpmpp_2s_ancestral",
    "dpm++ 3m sde": "dpmpp_3m_sde",
    "ddim": "ddim",
    "uni_pc": "uni_pc",
    "unipc": "uni_pc",
    "heun": "heun",
    "heunpp2": "heunpp2",
    "lms": "lms",
    "lcm": "lcm",
}


def _comfyui_seed(seed: int) -> int:
    if seed == _COMFYUI_RANDOM_SEED_SENTINEL:
        return random.randrange(2**32)
    return max(0, int(seed))


def comfyui_sampler_name(display_name: str) -> str:
    """Map a style-form sampler label to ComfyUI ``sampler_name``."""
    key = re.sub(r"\s+", " ", (display_name or "").strip().lower())
    if key in _SAMPLER_MAP:
        return _SAMPLER_MAP[key]
    slug = key.replace(" ", "_").replace("++", "pp")
    return slug or "euler"


def comfyui_scheduler_from_style(sampler: str, scheduler: str) -> str:
    """If the sampler label embeds Karras, prefer ``karras`` scheduler."""
    sched = (scheduler or "normal").strip().lower()
    if sched != "normal":
        return sched
    if re.search(r"\bkarras\b", sampler, re.I):
        return "karras"
    return sched


def _lora_loader_strength(lora: dict[str, Any]) -> float:
    raw = lora.get("strength")
    if raw is None:
        return 1.0
    return float(raw)


def _lora_active_for_loader(lora: dict[str, Any]) -> bool:
    """Strength ``0`` skips the file (session override or dataset save)."""
    return _lora_loader_strength(lora) != 0.0


def make_lab_refine_loras_from_build(
    refine_sdxl: dict[str, Any],
    sdxl: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Style → character LoRAs for the refine/detailer stack (no act)."""
    by_kind: dict[str, dict[str, Any]] = {}
    for item in refine_sdxl.get("loras") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        filename = (item.get("filename") or "").strip()
        if (
            kind in _MAKE_LAB_REFINE_LORA_KINDS
            and filename
            and kind not in by_kind
            and _lora_active_for_loader(item)
        ):
            by_kind[kind] = item
    if sdxl:
        for item in sdxl.get("loras") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            filename = (item.get("filename") or "").strip()
            if (
                kind in _MAKE_LAB_REFINE_LORA_KINDS
                and filename
                and kind not in by_kind
                and _lora_active_for_loader(item)
            ):
                by_kind[kind] = item
    return [by_kind[k] for k in _MAKE_LAB_REFINE_LORA_KINDS if k in by_kind]


def uses_separate_refine_model(build: dict[str, Any]) -> bool:
    """True when refine checkpoint filename differs from inference."""
    refine_sdxl = build.get("refine_sdxl")
    if not isinstance(refine_sdxl, dict):
        return False
    sdxl = build.get("sdxl") or {}
    infer_ckpt = ((sdxl.get("checkpoint") or {}).get("filename") or "").strip()
    refine_ckpt = ((refine_sdxl.get("checkpoint") or {}).get("filename") or "").strip()
    return bool(refine_ckpt and refine_ckpt != infer_ckpt)


def refine_stack_from_build(
    build: dict[str, Any],
    sdxl: dict[str, Any],
) -> dict[str, Any]:
    """Checkpoint + LoRAs for refine stack (nodes 120/122), every generation."""
    refine_sdxl = build.get("refine_sdxl")
    if isinstance(refine_sdxl, dict):
        ckpt = refine_sdxl.get("checkpoint") or {}
        ckpt_name = (ckpt.get("filename") or "").strip()
        if not ckpt_name:
            raise ValueError("refine_sdxl has no checkpoint filename")
        loras = make_lab_refine_loras_from_build(refine_sdxl, sdxl)
        return {"ckpt_name": ckpt_name, "loras": loras}
    ckpt = sdxl.get("checkpoint") or {}
    ckpt_name = (ckpt.get("filename") or "").strip()
    if not ckpt_name:
        raise ValueError("build result has no checkpoint filename for refine stack")
    loras = make_lab_refine_loras_from_build(sdxl, None)
    return {"ckpt_name": ckpt_name, "loras": loras}


def patch_clip_skip(workflow: dict[str, Any], node_id: str, clip_skip: int) -> None:
    """Map style ``clip_skip`` (e.g. 2) to ComfyUI ``stop_at_clip_layer`` (e.g. -2)."""
    workflow[node_id]["inputs"]["stop_at_clip_layer"] = -max(1, int(clip_skip or 2))


def _apply_refine_lora_chain(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    loras: list[dict[str, Any]] | None,
) -> None:
    from ..lora_loader_chain import apply_lora_loader_chain, rewire_lora_model_consumers

    model_out, _clip_out = apply_lora_loader_chain(
        workflow,
        tail_id=nodes["refine_lora"],
        loras=list(loras or []),
        model_source=[nodes["refine_checkpoint"], 0],
        clip_source=[nodes["refine_checkpoint"], 1],
        stack_prefix="lora_refine_stack",
        title_prefix="Refine LoRA",
    )
    if nodes["refine_sampler"] in workflow:
        workflow[nodes["refine_sampler"]]["inputs"]["model"] = model_out
    rewire_lora_model_consumers(
        workflow,
        model_ref=model_out,
        previous_model_nodes=[nodes["refine_lora"], nodes["refine_checkpoint"]],
    )


def upscale_settings_from_request(
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    """Read Make upscale fields from a saved ``request`` dict."""
    req = request or {}
    model = (req.get("upscale_model") or "").strip() or MAKE_LAB_UPSCALE_MODEL_DEFAULT
    try:
        upscale_by = float(req.get("upscale_by", MAKE_LAB_UPSCALE_BY_DEFAULT))
    except (TypeError, ValueError):
        upscale_by = MAKE_LAB_UPSCALE_BY_DEFAULT
    refine_steps_raw = req.get("refine_steps", req.get("upscale_steps"))
    try:
        refine_steps = int(
            refine_steps_raw
            if refine_steps_raw is not None
            else MAKE_LAB_REFINE_STEPS_DEFAULT
        )
    except (TypeError, ValueError):
        refine_steps = MAKE_LAB_REFINE_STEPS_DEFAULT
    refine_denoise_raw = req.get("refine_denoise", req.get("upscale_denoise"))
    try:
        refine_denoise = float(
            refine_denoise_raw
            if refine_denoise_raw is not None
            else MAKE_LAB_REFINE_DENOISE_DEFAULT
        )
    except (TypeError, ValueError):
        refine_denoise = MAKE_LAB_REFINE_DENOISE_DEFAULT
    return {
        "model_name": model,
        "upscale_by": max(1.0, upscale_by),
        "refine_steps": max(1, refine_steps),
        "refine_denoise": max(0.0, min(1.0, refine_denoise)),
    }


def assign_make_lab_seeds(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    base_seed: int,
    stages: list[Any],
    refine_enabled: bool = True,
) -> None:
    """Per-sampler seeds so ComfyUI does not skip passes via execution cache."""
    sampler_id = nodes["sampler"]
    if sampler_id not in workflow and "ksampler" in workflow:
        sampler_id = "ksampler"
    workflow[sampler_id]["inputs"]["seed"] = int(base_seed)
    if refine_enabled and nodes["refine_sampler"] in workflow:
        workflow[nodes["refine_sampler"]]["inputs"]["seed"] = int(base_seed) + 20000
    for i, stage in enumerate(stages):
        workflow[stage.face_detailer]["inputs"]["seed"] = int(base_seed) + 1000 + i


def patch_refine_sampler_nodes(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    seed: int,
    cfg: float,
    sampler: str,
    scheduler: str,
    refine_steps: int,
    refine_denoise: float,
) -> None:
    """Patch refine KSampler steps/cfg/sampler (independent of upscale)."""
    comfy_sampler = comfyui_sampler_name(sampler)
    comfy_scheduler = comfyui_scheduler_from_style(sampler, scheduler)
    refine = workflow[nodes["refine_sampler"]]["inputs"]
    refine["seed"] = int(seed)
    refine["steps"] = int(refine_steps)
    refine["cfg"] = float(cfg)
    refine["sampler_name"] = comfy_sampler
    refine["scheduler"] = comfy_scheduler
    refine["denoise"] = float(refine_denoise)


def patch_upscale_nodes(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    width: int,
    height: int,
    upscale: dict[str, Any],
) -> None:
    """Patch upscale model loader and ImageScale target size."""
    workflow[nodes["upscale_model"]]["inputs"]["model_name"] = str(
        upscale["model_name"]
    )
    upscale_by = float(upscale["upscale_by"])
    out_w, out_h = upscale_output_dimensions(width, height, upscale_by)
    scale = workflow[nodes["upscale_scale"]]["inputs"]
    scale["width"] = out_w
    scale["height"] = out_h
    restore_id = nodes.get("upscale_restore")
    if restore_id and restore_id in workflow:
        restore = workflow[restore_id]["inputs"]
        restore["width"] = int(width)
        restore["height"] = int(height)


def patch_refine_model_stack(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    ckpt_name: str,
    loras: list[dict[str, Any]] | None = None,
) -> None:
    """Patch refine checkpoint + LoRA loader; prompts stay on nodes 105/106."""
    workflow[nodes["refine_checkpoint"]]["inputs"]["ckpt_name"] = ckpt_name
    _apply_refine_lora_chain(workflow, nodes, loras)
