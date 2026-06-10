"""Load and patch API-format ComfyUI workflows."""

from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path
from typing import Any

from ..make.limits import (
    MAKE_LAB_REFINE_DENOISE_DEFAULT,
    MAKE_LAB_REFINE_STEPS_DEFAULT,
    MAKE_LAB_UPSCALE_BY_DEFAULT,
    MAKE_LAB_UPSCALE_MODEL_DEFAULT,
)
from .make_lab.compose import upscale_output_dimensions
from .make_lab.detailers import (
    apply_detailer_patches,
    detailer_style_positive_from_render,
    detailers_from_request,
    resolve_detailer_timing,
)
from .make_lab.compose import (
    UPSCALE_TIMING_DISABLED,
    refine_enabled_from_request,
    resolve_upscale_timing,
)
from .workflow_builder import build_pipeline_workflow, load_base_workflow_nodes, registry_nodes
from .make_lab.rmbg import apply_rmbg_stage

# Make UI uses ``-1`` for "random"; ComfyUI KSampler requires seed >= 0.
_COMFYUI_RANDOM_SEED_SENTINEL = -1


def _comfyui_seed(seed: int) -> int:
    if seed == _COMFYUI_RANDOM_SEED_SENTINEL:
        return random.randrange(2**32)
    return max(0, int(seed))

# Node ids in composed Make Lab workflows. Re-exported for output collection.
_MAKE_LAB_NODES: dict[str, str] = registry_nodes()
MAKE_LAB_EXPORT_IMAGE_NODE_ID = _MAKE_LAB_NODES["export_image"]
MAKE_LAB_SAVE_NODE_ID = _MAKE_LAB_NODES["save"]

REFINE_STACK_REWIRE = {
    "model": _MAKE_LAB_NODES["refine_lora"],
    "positive": _MAKE_LAB_NODES["refine_positive"],
    "negative": _MAKE_LAB_NODES["refine_negative"],
}

# LoRA stack order (style → character → animation).
_MAKE_LAB_LORA_KINDS = ("style", "character", "animation")
_MAKE_LAB_REFINE_LORA_KINDS = ("style", "character")

# Base pipeline nodes — optional stages composed by workflow_builder.
_MAKE_LAB_BASE_EXPECTED_TITLES: dict[str, str] = {
    "latent_empty": "Empty Latent Image",
    "checkpoint_main": "Load Checkpoint Main",
    "clip_skip": "CLIP Set Last Layer",
    "sampler_main": "Main Sampling",
    "prompt_main_positive": "Main Positive Prompt",
    "prompt_main_negative": "Main Negative Prompt",
    "vae_decode_output": "VAE Decode Refine",
    "export_image": "ComfySprites Export Image",
    "preview_save": "Preview Image",
}

# Make / style editor labels → ComfyUI ``KSampler.inputs.sampler_name``.
# UI keeps readable names (e.g. ``DPM++ SDE``); only the workflow patch uses
# ComfyUI ids (e.g. ``dpmpp_sde``). See ``dataset/style_defaults.json`` hints.
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


def validate_make_lab_workflow(workflow: dict[str, Any]) -> None:
    """Raise if the base Make Lab template drifts from the expected export."""
    titles = workflow_node_titles(workflow)
    for node_id, expected_title in _MAKE_LAB_BASE_EXPECTED_TITLES.items():
        if node_id not in workflow:
            raise ValueError(
                f"Make Lab base workflow missing node {node_id!r}"
            )
        if titles.get(node_id) != expected_title:
            raise ValueError(
                f"Make Lab node {node_id} title mismatch: "
                f"expected {expected_title!r}, got {titles.get(node_id)!r}"
            )
    export_node = workflow.get(MAKE_LAB_EXPORT_IMAGE_NODE_ID)
    if not isinstance(export_node, dict) or export_node.get("class_type") != "ComfySpritesExportImage":
        raise ValueError(
            f"Make Lab export node {MAKE_LAB_EXPORT_IMAGE_NODE_ID!r} must be "
            "ComfySpritesExportImage"
        )
    save_node = workflow.get(MAKE_LAB_SAVE_NODE_ID)
    if not isinstance(save_node, dict) or save_node.get("class_type") != "PreviewImage":
        raise ValueError(
            f"Make Lab output node {MAKE_LAB_SAVE_NODE_ID!r} must be PreviewImage"
        )
    save_images = (save_node.get("inputs") or {}).get("images")
    if save_images != [MAKE_LAB_EXPORT_IMAGE_NODE_ID, 0]:
        raise ValueError(
            f"Make Lab preview must read from {MAKE_LAB_EXPORT_IMAGE_NODE_ID!r}, "
            f"got {save_images!r}"
        )
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "FaceDetailer":
            raise ValueError(
                "Make Lab base workflow must not include FaceDetailer nodes; "
                "use detailer node composition instead"
            )


def load_make_lab_workflow() -> dict[str, Any]:
    """Return a deep copy of the base Make workflow (no optional stages)."""
    workflow = copy.deepcopy(load_base_workflow_nodes())
    validate_make_lab_workflow(workflow)
    return workflow


def prepare_make_lab_workflow(
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Composed workflow for the given request flags (no detailers unless in request)."""
    from .make_lab.detailers import (
        DETAILER_TIMING_DISABLED,
        detailers_from_request,
        resolve_detailer_timing,
    )

    req = request or {}
    refine_on = refine_enabled_from_request(req)
    upscale_timing = resolve_upscale_timing(req, refine_on=refine_on)
    detailer_timing = resolve_detailer_timing(req, separate_refine_model=False)
    enabled = (
        []
        if detailer_timing == DETAILER_TIMING_DISABLED
        else detailers_from_request(req)
    )
    refine_rewire = (
        REFINE_STACK_REWIRE
        if refine_on
        else {
            "model": _MAKE_LAB_NODES["lora"],
            "positive": _MAKE_LAB_NODES["positive"],
            "negative": _MAKE_LAB_NODES["negative"],
        }
    )
    result = build_pipeline_workflow(
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        enabled_detailers=enabled,
        refine_rewire=refine_rewire,
    )
    return copy.deepcopy(result.workflow)


def workflow_node_titles(workflow: dict[str, Any]) -> dict[str, str]:
    """Map workflow node id → display title (``_meta.title`` or ``class_type``)."""
    titles: dict[str, str] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        meta = node.get("_meta")
        if isinstance(meta, dict) and meta.get("title"):
            titles[str(node_id)] = str(meta["title"])
        else:
            titles[str(node_id)] = str(node.get("class_type") or node_id)
    return titles


def comfyui_sampler_name(display_name: str) -> str:
    """Map a style-form sampler label to ComfyUI ``sampler_name``."""
    key = re.sub(r"\s+", " ", (display_name or "").strip().lower())
    if key in _SAMPLER_MAP:
        return _SAMPLER_MAP[key]
    slug = key.replace(" ", "_").replace("++", "pp")
    return slug or "euler"


def _lora_loader_strength(lora: dict[str, Any]) -> float:
    raw = lora.get("strength")
    if raw is None:
        return 1.0
    return float(raw)


def _lora_active_for_loader(lora: dict[str, Any]) -> bool:
    """Strength ``0`` skips the file (session override or dataset save)."""
    return _lora_loader_strength(lora) != 0.0


def make_lab_loras_from_build(sdxl: dict[str, Any]) -> list[dict[str, Any]]:
    """Pick style → character → animation LoRAs from ``build.sdxl.loras`` (one per kind)."""
    raw = sdxl.get("loras") or []
    by_kind: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        filename = (item.get("filename") or "").strip()
        if not kind or not filename or kind in by_kind:
            continue
        if not _lora_active_for_loader(item):
            continue
        by_kind[kind] = item
    return [by_kind[k] for k in _MAKE_LAB_LORA_KINDS if k in by_kind]


def make_lab_inference_loras_from_build(
    sdxl: dict[str, Any], *, omit_style_lora: bool
) -> list[dict[str, Any]]:
    """Inference LoRAs; omit style when refine uses its own checkpoint stack."""
    loras = make_lab_loras_from_build(sdxl)
    if not omit_style_lora:
        return loras
    return [x for x in loras if str(x.get("kind") or "") != "style"]


def make_lab_refine_loras_from_build(
    refine_sdxl: dict[str, Any],
    sdxl: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Style → character LoRAs for the refine/detailer stack (no act).

    Merges character from inference ``sdxl`` when absent (partial test payloads).
    """
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
        raise ValueError(
            "build result has no checkpoint filename for refine stack"
        )
    loras = make_lab_refine_loras_from_build(sdxl, None)
    return {"ckpt_name": ckpt_name, "loras": loras}


def patch_clip_skip(workflow: dict[str, Any], node_id: str, clip_skip: int) -> None:
    """Map style ``clip_skip`` (e.g. 2) to ComfyUI ``stop_at_clip_layer`` (e.g. -2)."""
    workflow[node_id]["inputs"]["stop_at_clip_layer"] = -max(1, int(clip_skip or 2))


def _apply_inference_lora_chain(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    loras: list[dict[str, Any]] | None,
) -> None:
    from .lora_loader_chain import apply_lora_loader_chain, rewire_lora_model_consumers

    model_out, clip_out = apply_lora_loader_chain(
        workflow,
        tail_id=nodes["lora"],
        loras=list(loras or []),
        model_source=[nodes["checkpoint"], 0],
        clip_source=[nodes["checkpoint"], 1],
        stack_prefix="lora_stack",
        title_prefix="Inference LoRA",
    )
    workflow[nodes["clip_skip"]]["inputs"]["clip"] = clip_out
    workflow[nodes["sampler"]]["inputs"]["model"] = model_out
    rewire_lora_model_consumers(
        workflow,
        model_ref=model_out,
        previous_model_nodes=[nodes["lora"], nodes["checkpoint"]],
    )


def _apply_refine_lora_chain(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    loras: list[dict[str, Any]] | None,
) -> None:
    from .lora_loader_chain import apply_lora_loader_chain, rewire_lora_model_consumers

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
    workflow[nodes["sampler"]]["inputs"]["seed"] = int(base_seed)
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


def comfyui_scheduler_from_style(sampler: str, scheduler: str) -> str:
    """If the sampler label embeds Karras, prefer ``karras`` scheduler."""
    sched = (scheduler or "normal").strip().lower()
    if sched != "normal":
        return sched
    if re.search(r"\bkarras\b", sampler, re.I):
        return "karras"
    return sched


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


def patch_make_lab(
    workflow: dict[str, Any],
    *,
    positive: str,
    negative: str,
    ckpt_name: str,
    refine_positive: str | None = None,
    refine_negative: str | None = None,
    width: int,
    height: int,
    seed: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
    batch_size: int = 1,
    loras: list[dict[str, Any]] | None = None,
    clip_skip: int = 2,
    upscale: dict[str, Any] | None = None,
    refine_stack: dict[str, Any] | None = None,
    refine_enabled: bool = True,
    upscale_enabled: bool = True,
) -> dict[str, Any]:
    """Apply build inference + prompts to Make Lab nodes."""
    nodes = _MAKE_LAB_NODES
    bs = max(1, int(batch_size))
    workflow[nodes["checkpoint"]]["inputs"]["ckpt_name"] = ckpt_name
    _apply_inference_lora_chain(workflow, nodes, loras)
    patch_clip_skip(workflow, nodes["clip_skip"], clip_skip)
    workflow[nodes["latent"]]["inputs"]["width"] = int(width)
    workflow[nodes["latent"]]["inputs"]["height"] = int(height)
    workflow[nodes["latent"]]["inputs"]["batch_size"] = bs
    workflow[nodes["positive"]]["inputs"]["text"] = positive
    workflow[nodes["negative"]]["inputs"]["text"] = negative
    if refine_enabled and nodes["refine_positive"] in workflow:
        workflow[nodes["refine_positive"]]["inputs"]["text"] = (
            refine_positive if refine_positive is not None else positive
        )
        workflow[nodes["refine_negative"]]["inputs"]["text"] = (
            refine_negative if refine_negative is not None else negative
        )
        stack = refine_stack or {
            "ckpt_name": ckpt_name,
            "loras": list(loras or []),
        }
        patch_refine_model_stack(workflow, nodes, **stack)
    sampler_inputs = workflow[nodes["sampler"]]["inputs"]
    sampler_inputs["seed"] = int(seed)
    sampler_inputs["steps"] = int(steps)
    sampler_inputs["cfg"] = float(cfg)
    sampler_inputs["sampler_name"] = comfyui_sampler_name(sampler)
    sampler_inputs["scheduler"] = comfyui_scheduler_from_style(sampler, scheduler)
    upscale_cfg = upscale or upscale_settings_from_request(None)
    if upscale_enabled and nodes["upscale_model"] in workflow:
        patch_upscale_nodes(
            workflow,
            nodes,
            width=int(width),
            height=int(height),
            upscale=upscale_cfg,
        )
    if refine_enabled and nodes["refine_sampler"] in workflow:
        patch_refine_sampler_nodes(
            workflow,
            nodes,
            seed=int(seed),
            cfg=float(cfg),
            sampler=sampler,
            scheduler=scheduler,
            refine_steps=int(upscale_cfg["refine_steps"]),
            refine_denoise=float(upscale_cfg["refine_denoise"]),
        )
    return workflow


def build_result_to_make_lab(
    build: dict[str, Any], *, batch_size: int = 1
) -> dict[str, Any]:
    """Patch workflow from a ``composer.build()`` response."""
    sdxl = build.get("sdxl") or {}
    checkpoint = sdxl.get("checkpoint") or {}
    ckpt_name = (checkpoint.get("filename") or "").strip()
    if not ckpt_name:
        raise ValueError("build result has no checkpoint filename")

    scene = build.get("scene") or {}
    seed = _comfyui_seed(int(scene.get("seed", 0)))
    request = build.get("request") or {}
    width = int(sdxl.get("width") or 512)
    height = int(sdxl.get("height") or 512)
    positive = sdxl.get("positive") or ""
    negative = sdxl.get("negative") or ""
    refine_sdxl = build.get("refine_sdxl") if isinstance(build.get("refine_sdxl"), dict) else {}
    refine_positive = refine_sdxl.get("positive") or positive
    refine_negative = refine_sdxl.get("negative") or negative
    refine_stack = refine_stack_from_build(build, sdxl)
    # Sampler/scheduler come from the rolled style unless explicitly overridden
    # (Validate). Make omits them so the style record is authoritative.
    ckpt_sampler = str(checkpoint.get("sampler") or "").strip()
    ckpt_scheduler = str(checkpoint.get("scheduler") or "").strip()
    sampler = str(request.get("sampler") or ckpt_sampler or "Euler a")
    scheduler = str(request.get("scheduler") or ckpt_scheduler or "normal")

    from .make_lab.detailers import DETAILER_TIMING_DISABLED

    detailer_timing = resolve_detailer_timing(
        request,
        separate_refine_model=uses_separate_refine_model(build),
    )
    refine_on = refine_enabled_from_request(request)
    upscale_timing = resolve_upscale_timing(request, refine_on=refine_on)
    upscale_on = upscale_timing != UPSCALE_TIMING_DISABLED
    enabled_detailers = (
        []
        if detailer_timing == DETAILER_TIMING_DISABLED
        else detailers_from_request(request)
    )
    nodes = _MAKE_LAB_NODES
    detailer_rewire = (
        REFINE_STACK_REWIRE
        if refine_on
        else {
            "model": nodes["lora"],
            "positive": nodes["positive"],
            "negative": nodes["negative"],
        }
    )
    composed = build_pipeline_workflow(
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        enabled_detailers=enabled_detailers,
        refine_rewire=detailer_rewire,
        upscale_enabled=upscale_on,
    )
    workflow = composed.workflow
    stages = composed.stages
    patch_make_lab(
        workflow,
        positive=positive,
        negative=negative,
        refine_positive=refine_positive,
        refine_negative=refine_negative,
        ckpt_name=ckpt_name,
        width=width,
        height=height,
        seed=seed,
        steps=int(checkpoint.get("steps") or 20),
        cfg=float(checkpoint.get("cfg_scale") or 8.0),
        sampler=sampler,
        scheduler=scheduler,
        batch_size=batch_size,
        loras=make_lab_inference_loras_from_build(sdxl, omit_style_lora=False),
        clip_skip=int(checkpoint.get("clip_skip") or 2),
        upscale=upscale_settings_from_request(request),
        refine_stack=refine_stack,
        refine_enabled=refine_on,
        upscale_enabled=upscale_on,
    )
    detailer_style_positive = refine_sdxl.get("detailer_style_positive")
    if detailer_style_positive is None:
        detailer_style_positive = detailer_style_positive_from_render(refine_sdxl)
    apply_detailer_patches(
        workflow,
        stages,
        character_adetailer=build.get("character_adetailer"),
        detailer_style_positive=str(detailer_style_positive or ""),
        seed=seed,
    )
    assign_make_lab_seeds(
        workflow, nodes, base_seed=seed, stages=stages, refine_enabled=refine_on
    )
    from .make_lab.controlnet import apply_controlnet_stage
    from ..env_settings import load_comfyui_base_url

    apply_controlnet_stage(
        workflow,
        request,
        build,
        base_url=load_comfyui_base_url(),
    )
    apply_rmbg_stage(workflow, request)
    from .inject_assets import patch_make_lab_export

    patch_make_lab_export(workflow, request=request)
    return workflow
