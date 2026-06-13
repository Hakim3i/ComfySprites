"""Load and patch the Anima Make Lab workflow."""

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
    comfyui_sampler_name,
    comfyui_scheduler_from_style,
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
from ..pipeline_builder import build_pipeline
from ..workflow_builder import (
    _apply_detailer_links,
    build_pipeline_workflow,
    load_registry,
)

_ANIMA_MAKE_UNET = "anima-base-v1.0.safetensors"
_ANIMA_MAKE_CLIP = "qwen_3_06b_base.safetensors"
_ANIMA_MAKE_VAE = "qwen_image_vae.safetensors"
_ANIMA_MODEL_ID = "anima"


def _blueprint() -> dict[str, Any]:
    from ..pipeline_builder import _load_pipeline_blueprint

    return _load_pipeline_blueprint("anima_make")


def anima_make_patch_roles() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_blueprint().get("patch_roles") or {}).items()}


def anima_make_export_node_id() -> str:
    return str((_blueprint().get("outputs") or {}).get("image") or "export_image")


def load_anima_make_workflow() -> dict[str, Any]:
    return copy.deepcopy(build_pipeline("anima_make").workflow)


def _resolved_path(model_paths: dict[str, str] | None, catalog_filename: str) -> str:
    if model_paths:
        hit = model_paths.get(catalog_filename)
        if hit:
            return hit
    return catalog_filename


def _apply_anima_make_style_loras(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    loras: list[dict[str, Any]] | None,
    model_paths: dict[str, str] | None,
) -> None:
    from ..lora_loader_chain import (
        apply_lora_loader_model_only_chain,
        rewire_lora_model_consumers,
    )

    model_out = apply_lora_loader_model_only_chain(
        workflow,
        tail_id="anima_make_style_lora",
        loras=list(loras or []),
        model_source=[nodes["diffusion_model"], 0],
        stack_prefix="anima_make_style_lora",
        title_prefix="Style LoRA",
        resolve_lora_name=lambda name: _resolved_path(model_paths, name),
    )
    workflow[nodes["ksampler"]]["inputs"]["model"] = model_out
    rewire_lora_model_consumers(
        workflow,
        model_ref=model_out,
        previous_model_nodes=[nodes["diffusion_model"], "anima_make_style_lora"],
    )


def patch_anima_make_workflow(
    *,
    positive: str,
    negative: str,
    width: int,
    height: int,
    seed: int,
    steps: int = 40,
    cfg: float = 5.0,
    sampler: str = "er_sde",
    scheduler: str = "normal",
    batch_size: int = 1,
    model_paths: dict[str, str] | None = None,
    unet_filename: str | None = None,
    style_loras: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    workflow = load_anima_make_workflow()
    nodes = anima_make_patch_roles()

    unet = (unet_filename or "").strip() or _ANIMA_MAKE_UNET
    workflow[nodes["diffusion_model"]]["inputs"]["unet_name"] = _resolved_path(
        model_paths, unet
    )
    workflow[nodes["anima_clip"]]["inputs"]["clip_name"] = _resolved_path(
        model_paths, _ANIMA_MAKE_CLIP
    )
    workflow[nodes["anima_vae"]]["inputs"]["vae_name"] = _resolved_path(
        model_paths, _ANIMA_MAKE_VAE
    )
    workflow[nodes["positive"]]["inputs"]["text"] = positive
    workflow[nodes["negative"]]["inputs"]["text"] = negative
    workflow[nodes["empty_latent"]]["inputs"]["width"] = int(width)
    workflow[nodes["empty_latent"]]["inputs"]["height"] = int(height)
    workflow[nodes["empty_latent"]]["inputs"]["batch_size"] = max(1, int(batch_size))

    sampler_inputs = workflow[nodes["ksampler"]]["inputs"]
    sampler_inputs["seed"] = int(seed)
    sampler_inputs["steps"] = max(1, int(steps))
    sampler_inputs["cfg"] = float(cfg)
    sampler_inputs["sampler_name"] = comfyui_sampler_name(sampler)
    sampler_inputs["scheduler"] = comfyui_scheduler_from_style(sampler, scheduler)

    _apply_anima_make_style_loras(
        workflow,
        nodes,
        loras=style_loras,
        model_paths=model_paths,
    )

    return workflow


def _wire_anima_refine_stack(
    workflow: dict[str, Any],
    *,
    anima_decode_id: str,
    nodes: dict[str, str],
    upscale_timing: str,
) -> None:
    refine_ckpt = nodes["refine_checkpoint"]
    vae_encode = nodes["vae_encode"]
    if vae_encode not in workflow:
        from ..workflow_builder import _instantiate_pipeline_node

        registry = load_registry()
        workflow[vae_encode] = _instantiate_pipeline_node(
            "vae_encode", registry=registry
        )

    encode_pixels: list[Any] = [anima_decode_id, 0]
    if upscale_timing == "before" and nodes["upscale_scale"] in workflow:
        workflow[nodes["upscale_with_model"]]["inputs"]["image"] = [anima_decode_id, 0]
        encode_pixels = [nodes["upscale_scale"], 0]

    workflow[vae_encode]["inputs"]["pixels"] = encode_pixels
    workflow[vae_encode]["inputs"]["vae"] = [refine_ckpt, 2]
    workflow[nodes["refine_sampler"]]["inputs"]["latent_image"] = [vae_encode, 0]


def _prune_anima_dead_sdxl_main(workflow: dict[str, Any], nodes: dict[str, str]) -> None:
    for role in ("sampler", "latent", "positive", "negative"):
        nid = nodes.get(role)
        if nid and nid in workflow:
            del workflow[nid]


def _patch_anima_refine_sdxl_stubs(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    ckpt_name: str,
    clip_skip: int,
) -> None:
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


def build_anima_make_lab_workflow(
    build: dict[str, Any],
    *,
    batch_size: int = 1,
    model_paths: dict[str, str] | None = None,
    lora_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compose Anima first pass with optional SDXL refine/detailers/upscale."""
    anima = build.get("anima_make") or {}
    sdxl = build.get("sdxl") or {}
    refine_sdxl = build.get("refine_sdxl") if isinstance(build.get("refine_sdxl"), dict) else {}
    request = build.get("request") or {}
    scene = build.get("scene") or {}
    seed = _comfyui_seed(int(scene.get("seed", 0)))
    checkpoint = sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
    unet_filename = (checkpoint.get("filename") or "").strip() or None

    from ..workflow import qwen_make_style_loras_from_build

    sampler = str(
        request.get("sampler") or checkpoint.get("sampler") or anima.get("sampler") or "er_sde"
    )
    scheduler = str(
        request.get("scheduler")
        or checkpoint.get("scheduler")
        or anima.get("scheduler")
        or "normal"
    )

    workflow = patch_anima_make_workflow(
        positive=str(anima.get("positive") or ""),
        negative=str(anima.get("negative") or ""),
        width=int(anima.get("width") or sdxl.get("width") or 1024),
        height=int(anima.get("height") or sdxl.get("height") or 1024),
        seed=seed,
        steps=int(anima.get("steps") or 40),
        cfg=float(anima.get("cfg") or 5.0),
        sampler=sampler,
        scheduler=scheduler,
        batch_size=batch_size,
        model_paths=model_paths,
        unet_filename=unet_filename,
        style_loras=qwen_make_style_loras_from_build(sdxl),
    )
    anima_nodes = anima_make_patch_roles()
    anima_decode = anima_nodes["vae_decode"]

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
        workflow[anima_nodes["export_image"]]["inputs"]["images"] = [anima_decode, 0]
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
    _prune_anima_dead_sdxl_main(workflow, nodes)
    stages = composed.stages

    refine_positive = refine_sdxl.get("positive") or anima.get("positive") or ""
    refine_negative = refine_sdxl.get("negative") or anima.get("negative") or ""
    refine_stack = refine_stack_from_build(build, sdxl)
    ckpt_meta = refine_sdxl.get("checkpoint") or {}
    refine_sampler = str(ckpt_meta.get("sampler") or request.get("sampler") or "Euler a")
    refine_scheduler = str(
        ckpt_meta.get("scheduler") or request.get("scheduler") or "normal"
    )
    upscale_cfg = upscale_settings_from_request(request)

    refine_ckpt_name = str(refine_stack["ckpt_name"])
    from ..asset_inventory import resolve_lora_filename

    resolve_lora = (
        (lambda name, paths=lora_paths: resolve_lora_filename(name, paths))
        if lora_paths
        else None
    )
    patch_refine_model_stack(
        workflow,
        nodes,
        ckpt_name=refine_ckpt_name,
        loras=refine_stack.get("loras"),
        resolve_lora_name=resolve_lora,
    )
    _patch_anima_refine_sdxl_stubs(
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
        sampler=refine_sampler,
        scheduler=refine_scheduler,
        refine_steps=int(upscale_cfg["refine_steps"]),
        refine_denoise=float(upscale_cfg["refine_denoise"]),
    )
    if upscale_on:
        patch_upscale_nodes(
            workflow,
            nodes,
            width=int(anima.get("width") or 1024),
            height=int(anima.get("height") or 1024),
            upscale=upscale_cfg,
        )

    _wire_anima_refine_stack(
        workflow,
        anima_decode_id=anima_decode,
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
