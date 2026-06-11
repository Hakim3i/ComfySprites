"""Load and patch the Qwen Image 2512 Make Lab workflow."""

from __future__ import annotations

import copy
from typing import Any

from ..make_lab.compose import (
    UPSCALE_TIMING_DISABLED,
    refine_enabled_from_request,
    resolve_upscale_timing,
)
from ..make_lab.workflow_patch import (
    REFINE_STACK_REWIRE,
    _MAKE_LAB_NODES,
    _comfyui_seed,
    assign_make_lab_seeds,
    patch_clip_skip,
    patch_refine_model_stack,
    patch_refine_sampler_nodes,
    patch_upscale_nodes,
    refine_stack_from_build,
    upscale_settings_from_request,
    uses_separate_refine_model,
)
from ..make_lab.detailers import (
    DETAILER_TIMING_DISABLED,
    apply_detailer_patches,
    detailer_style_positive_from_render,
    detailers_from_request,
    resolve_detailer_timing,
)
from ...services.sdxl.payload import QWEN_MAKE_SHIFT_DEFAULT
from ..pipeline_builder import build_pipeline
from ..workflow_builder import (
    _apply_detailer_links,
    build_pipeline_workflow,
    load_registry,
)

_QWEN_MAKE_UNET = "qwen_image_2512_fp8_e4m3fn.safetensors"
_QWEN_MAKE_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
_QWEN_MAKE_VAE = "qwen_image_vae.safetensors"
_QWEN_MAKE_LIGHTNING = "Qwen-Image-2512-Lightning-4steps-V1.0-fp32.safetensors"
_QWEN_MODEL_ID = "qwen_image_2512"


def _blueprint() -> dict[str, Any]:
    from ..pipeline_builder import _load_pipeline_blueprint

    return _load_pipeline_blueprint("qwen_make")


def qwen_make_patch_roles() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_blueprint().get("patch_roles") or {}).items()}


def qwen_make_export_node_id() -> str:
    return str((_blueprint().get("outputs") or {}).get("image") or "export_image")


def load_qwen_make_workflow() -> dict[str, Any]:
    return copy.deepcopy(build_pipeline("qwen_make").workflow)


def _resolved_path(model_paths: dict[str, str] | None, catalog_filename: str) -> str:
    if model_paths:
        hit = model_paths.get(catalog_filename)
        if hit:
            return hit
    return catalog_filename


def patch_qwen_make_workflow(
    *,
    positive: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    steps: int = 4,
    cfg: float = 1.0,
    shift: float | None = None,
    batch_size: int = 1,
    model_paths: dict[str, str] | None = None,
    unet_filename: str | None = None,
) -> dict[str, Any]:
    from ...services.sdxl.payload import QWEN_MAKE_SHIFT_DEFAULT

    if shift is None:
        shift = QWEN_MAKE_SHIFT_DEFAULT
    workflow = load_qwen_make_workflow()
    nodes = qwen_make_patch_roles()

    unet = (unet_filename or "").strip() or _QWEN_MAKE_UNET
    workflow[nodes["diffusion_model"]]["inputs"]["unet_name"] = _resolved_path(
        model_paths, unet
    )
    workflow[nodes["qwen_clip"]]["inputs"]["clip_name"] = _resolved_path(
        model_paths, _QWEN_MAKE_CLIP
    )
    workflow[nodes["qwen_vae"]]["inputs"]["vae_name"] = _resolved_path(
        model_paths, _QWEN_MAKE_VAE
    )
    workflow[nodes["lightning_lora"]]["inputs"]["lora_name"] = _resolved_path(
        model_paths, _QWEN_MAKE_LIGHTNING
    )
    workflow[nodes["model_sampling"]]["inputs"]["shift"] = float(shift)
    workflow[nodes["positive"]]["inputs"]["text"] = positive
    workflow[nodes["negative"]]["inputs"]["text"] = negative
    workflow[nodes["empty_latent"]]["inputs"]["width"] = int(width)
    workflow[nodes["empty_latent"]]["inputs"]["height"] = int(height)
    workflow[nodes["empty_latent"]]["inputs"]["batch_size"] = max(1, int(batch_size))

    sampler = workflow[nodes["ksampler"]]["inputs"]
    sampler["seed"] = int(seed)
    sampler["steps"] = max(1, int(steps))
    sampler["cfg"] = float(cfg)

    return workflow


def _wire_qwen_refine_stack(
    workflow: dict[str, Any],
    *,
    qwen_decode_id: str,
    nodes: dict[str, str],
    upscale_timing: str,
) -> None:
    """Connect Qwen VAE decode output into the SDXL refine VAEEncode path."""
    refine_ckpt = nodes["refine_checkpoint"]
    vae_encode = nodes["vae_encode"]
    if vae_encode not in workflow:
        from ..workflow_builder import _instantiate_pipeline_node

        registry = load_registry()
        workflow[vae_encode] = _instantiate_pipeline_node(
            "vae_encode", registry=registry
        )

    encode_pixels: list[Any] = [qwen_decode_id, 0]
    if upscale_timing == "before" and nodes["upscale_scale"] in workflow:
        workflow[nodes["upscale_with_model"]]["inputs"]["image"] = [qwen_decode_id, 0]
        encode_pixels = [nodes["upscale_scale"], 0]

    workflow[vae_encode]["inputs"]["pixels"] = encode_pixels
    workflow[vae_encode]["inputs"]["vae"] = [refine_ckpt, 2]
    workflow[nodes["refine_sampler"]]["inputs"]["latent_image"] = [vae_encode, 0]


def _prune_qwen_dead_sdxl_main(workflow: dict[str, Any], nodes: dict[str, str]) -> None:
    """Remove orphaned SDXL main-inference nodes merged from make_lab base_include."""
    for role in ("sampler", "latent", "positive", "negative"):
        nid = nodes.get(role)
        if nid and nid in workflow:
            del workflow[nid]


def _patch_qwen_refine_sdxl_stubs(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    ckpt_name: str,
    clip_skip: int,
) -> None:
    """Patch SDXL stub nodes merged from make_lab so ComfyUI validation passes.

    Qwen inference skips ``checkpoint_main``; refine still composes the SDXL
    refine subgraph (clip_skip, vae_decode_output, etc.) which references it.
    """
    main_ckpt = nodes["checkpoint"]
    refine_ckpt = nodes["refine_checkpoint"]
    if main_ckpt in workflow:
        workflow[main_ckpt]["inputs"]["ckpt_name"] = ckpt_name
    if nodes["clip_skip"] in workflow:
        patch_clip_skip(workflow, nodes["clip_skip"], clip_skip)
        workflow[nodes["clip_skip"]]["inputs"]["clip"] = [refine_ckpt, 1]
    refine_decode = nodes["refine_decode"]
    if refine_decode in workflow and refine_ckpt in workflow:
        workflow[refine_decode]["inputs"]["vae"] = [refine_ckpt, 2]


def build_qwen_make_lab_workflow(
    build: dict[str, Any],
    *,
    batch_size: int = 1,
    model_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compose Qwen first pass with optional SDXL refine/detailers/upscale."""
    qwen = build.get("qwen_make") or {}
    sdxl = build.get("sdxl") or {}
    refine_sdxl = build.get("refine_sdxl") if isinstance(build.get("refine_sdxl"), dict) else {}
    request = build.get("request") or {}
    scene = build.get("scene") or {}
    seed = _comfyui_seed(int(scene.get("seed", 0)))
    checkpoint = sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
    unet_filename = (checkpoint.get("filename") or "").strip() or None

    workflow = patch_qwen_make_workflow(
        positive=str(qwen.get("positive") or ""),
        negative=str(qwen.get("negative") or ""),
        width=int(qwen.get("width") or sdxl.get("width") or 1328),
        height=int(qwen.get("height") or sdxl.get("height") or 1328),
        seed=seed,
        steps=int(qwen.get("steps") or 4),
        cfg=float(qwen.get("cfg") or 1.0),
        shift=float(qwen.get("shift") or QWEN_MAKE_SHIFT_DEFAULT),
        batch_size=batch_size,
        model_paths=model_paths,
        unet_filename=unet_filename,
    )
    qwen_nodes = qwen_make_patch_roles()
    qwen_decode = qwen_nodes["vae_decode"]

    refine_on = refine_enabled_from_request(request)
    upscale_timing = resolve_upscale_timing(request, refine_on=refine_on)
    upscale_on = upscale_timing != UPSCALE_TIMING_DISABLED
    detailer_timing = (
        DETAILER_TIMING_DISABLED
        if not refine_on
        else resolve_detailer_timing(
            request,
            separate_refine_model=uses_separate_refine_model(build),
        )
    )
    enabled_detailers = (
        []
        if detailer_timing == DETAILER_TIMING_DISABLED
        else detailers_from_request(request)
    )

    if not refine_on:
        workflow[qwen_nodes["export_image"]]["inputs"]["images"] = [qwen_decode, 0]
        from ..make_lab.rmbg import apply_rmbg_stage
        from ..inject_assets import patch_make_lab_export

        apply_rmbg_stage(workflow, request)
        patch_make_lab_export(workflow, request=request)
        return workflow

    composed = build_pipeline_workflow(
        refine_on=True,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        enabled_detailers=enabled_detailers,
        refine_rewire=REFINE_STACK_REWIRE,
        upscale_enabled=upscale_on,
    )
    nodes = _MAKE_LAB_NODES
    workflow.update(composed.workflow)
    _prune_qwen_dead_sdxl_main(workflow, nodes)
    stages = composed.stages

    refine_positive = refine_sdxl.get("positive") or qwen.get("positive") or ""
    refine_negative = refine_sdxl.get("negative") or qwen.get("negative") or ""
    refine_stack = refine_stack_from_build(build, sdxl)
    ckpt_meta = refine_sdxl.get("checkpoint") or {}
    sampler_name = str(ckpt_meta.get("sampler") or request.get("sampler") or "Euler a")
    scheduler_name = str(
        ckpt_meta.get("scheduler") or request.get("scheduler") or "normal"
    )
    upscale_cfg = upscale_settings_from_request(request)

    refine_ckpt_name = str(refine_stack["ckpt_name"])
    patch_refine_model_stack(
        workflow,
        nodes,
        ckpt_name=refine_ckpt_name,
        loras=refine_stack.get("loras"),
    )
    _patch_qwen_refine_sdxl_stubs(
        workflow,
        nodes,
        ckpt_name=refine_ckpt_name,
        clip_skip=int(ckpt_meta.get("clip_skip") or 2),
    )
    workflow[nodes["refine_positive"]]["inputs"]["text"] = refine_positive
    workflow[nodes["refine_negative"]]["inputs"]["text"] = refine_negative
    patch_clip_skip(workflow, nodes["clip_skip"], int(ckpt_meta.get("clip_skip") or 2))
    patch_refine_sampler_nodes(
        workflow,
        nodes,
        seed=seed,
        cfg=float(ckpt_meta.get("cfg_scale") or 8.0),
        sampler=sampler_name,
        scheduler=scheduler_name,
        refine_steps=int(upscale_cfg["refine_steps"]),
        refine_denoise=float(upscale_cfg["refine_denoise"]),
    )
    if upscale_on:
        patch_upscale_nodes(
            workflow,
            nodes,
            width=int(qwen.get("width") or 1328),
            height=int(qwen.get("height") or 1328),
            upscale=upscale_cfg,
        )

    _wire_qwen_refine_stack(
        workflow,
        qwen_decode_id=qwen_decode,
        nodes=nodes,
        upscale_timing=upscale_timing,
    )
    if stages:
        _apply_detailer_links(
            workflow,
            nodes,
            stages=stages,
            timing=detailer_timing,
            refine_on=True,
            upscale_on=upscale_on,
            upscale_timing=upscale_timing,
            refine_rewire=REFINE_STACK_REWIRE,
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
        workflow, nodes, base_seed=seed, stages=stages, refine_enabled=True
    )

    from ..make_lab.rmbg import apply_rmbg_stage
    from ..inject_assets import patch_make_lab_export

    apply_rmbg_stage(workflow, request)
    patch_make_lab_export(workflow, request=request)
    return workflow
