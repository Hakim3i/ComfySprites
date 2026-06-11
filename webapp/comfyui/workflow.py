"""Load and patch API-format ComfyUI workflows."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

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
from .workflow_builder import (
    build_pipeline_workflow,
    load_base_workflow_nodes,
    registry_nodes,
)
from .make_lab.rmbg import apply_rmbg_stage
from .make_lab.workflow_patch import (
    REFINE_STACK_REWIRE,
    _MAKE_LAB_NODES,
    _comfyui_seed,
    assign_make_lab_seeds,
    comfyui_sampler_name,
    comfyui_scheduler_from_style,
    make_lab_refine_loras_from_build,
    patch_clip_skip,
    patch_refine_model_stack,
    patch_refine_sampler_nodes,
    patch_upscale_nodes,
    refine_stack_from_build,
    upscale_settings_from_request,
    uses_separate_refine_model,
)

MAKE_LAB_EXPORT_IMAGE_NODE_ID = _MAKE_LAB_NODES["export_image"]
MAKE_LAB_SAVE_NODE_ID = _MAKE_LAB_NODES["save"]

# LoRA stack order (style → character → animation).
_MAKE_LAB_LORA_KINDS = ("style", "character", "animation")

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

def validate_make_lab_workflow(workflow: dict[str, Any]) -> None:
    """Raise if the base Make Lab template drifts from the expected export."""
    titles = workflow_node_titles(workflow)
    for node_id, expected_title in _MAKE_LAB_BASE_EXPECTED_TITLES.items():
        if node_id not in workflow:
            raise ValueError(f"Make Lab base workflow missing node {node_id!r}")
        if titles.get(node_id) != expected_title:
            raise ValueError(
                f"Make Lab node {node_id} title mismatch: "
                f"expected {expected_title!r}, got {titles.get(node_id)!r}"
            )
    export_node = workflow.get(MAKE_LAB_EXPORT_IMAGE_NODE_ID)
    if (
        not isinstance(export_node, dict)
        or export_node.get("class_type") != "ComfySpritesExportImage"
    ):
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
    if isinstance(build.get("qwen_make"), dict):
        from ..env_settings import load_comfyui_base_url
        from .asset_inventory import resolve_diffusion_model_paths
        from .qwen_make.workflow import build_qwen_make_lab_workflow

        try:
            base_url = load_comfyui_base_url()
        except RuntimeError:
            base_url = None
        sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
        checkpoint = sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
        unet_filename = (checkpoint.get("filename") or "").strip()
        extra = {"unet": unet_filename} if unet_filename else None
        model_paths = resolve_diffusion_model_paths(
            "qwen_image_2512", base_url, extra_filenames=extra
        )
        return build_qwen_make_lab_workflow(
            build,
            batch_size=batch_size,
            model_paths=model_paths or None,
        )

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
    refine_sdxl = (
        build.get("refine_sdxl") if isinstance(build.get("refine_sdxl"), dict) else {}
    )
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
