"""Compose Make Lab workflows from decomposed node files and recipes."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .make_lab.detailers import (
    DETAILER_TIMING_AFTER,
    DETAILER_TIMING_BEFORE,
    DETAILER_TIMING_DISABLED,
    DetailerStageNodes,
    _stage_node_id,
    load_detailer_manifest,
)

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
NODES_DIR = WORKFLOWS_DIR / "nodes"
REGISTRY_PATH = WORKFLOWS_DIR / "registry.json"
RECIPE_PATH = WORKFLOWS_DIR / "recipes" / "make_lab.json"

UPSCALE_TIMING_DISABLED = "disabled"
UPSCALE_TIMING_BEFORE = "before"
UPSCALE_TIMING_AFTER = "after"


@dataclass(frozen=True)
class ComposeResult:
    workflow: dict[str, Any]
    stages: list[DetailerStageNodes]
    refine_on: bool
    upscale_timing: str
    detailer_timing: str
    nodes: dict[str, str]


@lru_cache(maxsize=1)
def load_registry() -> dict[str, str]:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in raw.items()}


def registry_nodes() -> dict[str, str]:
    """Symbolic registry for patching and progress (``workflow._MAKE_LAB_NODES``)."""
    reg = load_registry()
    return {
        "checkpoint": reg["checkpoint"],
        "lora": reg["lora"],
        "clip_skip": reg["clip_skip"],
        "main_decode": reg["main_decode"],
        "base_decode": reg["base_decode"],
        "refine_decode": reg["refine_decode"],
        "upscale_model": reg["upscale_model"],
        "upscale_with_model": reg["upscale_with_model"],
        "upscale_scale": reg["upscale_scale"],
        "upscale_restore": reg["upscale_restore"],
        "refine_sampler": reg["refine_sampler"],
        "latent": reg["latent"],
        "sampler": reg["sampler"],
        "positive": reg["main_positive"],
        "negative": reg["negative"],
        "refine_positive": reg["refine_positive"],
        "refine_negative": reg["refine_negative"],
        "save": reg["save"],
        "export_image": reg["export_image"],
        "refine_checkpoint": reg["refine_checkpoint"],
        "refine_lora": reg["refine_lora"],
        "vae_encode": reg["vae_encode"],
    }


@lru_cache(maxsize=1)
def _load_recipe() -> dict[str, Any]:
    return json.loads(RECIPE_PATH.read_text(encoding="utf-8"))


def _load_node_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pipeline_node(role: str) -> dict[str, Any]:
    path = NODES_DIR / f"{role}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Pipeline node file missing: {path}")
    return copy.deepcopy(_load_node_file(path))


def load_node_template(name: str) -> dict[str, Any]:
    path = NODES_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Node template missing: {path}")
    return copy.deepcopy(_load_node_file(path))


def _resolve_ref(
    ref: str,
    *,
    registry: dict[str, str],
    context: dict[str, str],
) -> str:
    if ref.startswith("@"):
        key = ref[1:]
        if key in context:
            return context[key]
        if key in registry:
            return registry[key]
        return ref
    return ref


def _resolve_value(
    value: Any,
    *,
    registry: dict[str, str],
    context: dict[str, str],
) -> Any:
    if isinstance(value, list) and value and isinstance(value[0], str):
        head = value[0]
        if head.startswith("@") or head in registry:
            resolved = _resolve_ref(head, registry=registry, context=context)
            return [resolved, *value[1:]]
        return value
    if isinstance(value, dict):
        return {
            k: _resolve_value(v, registry=registry, context=context)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_resolve_value(v, registry=registry, context=context) for v in value]
    return value


def _instantiate_pipeline_node(
    role: str,
    *,
    registry: dict[str, str],
    context: dict[str, str] | None = None,
) -> dict[str, Any]:
    raw = load_pipeline_node(role)
    ctx = context or {}
    inputs = copy.deepcopy(raw.get("inputs") or {})
    defaults = copy.deepcopy(raw.get("defaults") or {})
    for key, val in defaults.items():
        inputs.setdefault(key, val)
    resolved = _resolve_value(inputs, registry=registry, context=ctx)
    return {
        "inputs": resolved,
        "class_type": raw["class_type"],
        "_meta": copy.deepcopy(raw.get("_meta") or {}),
    }


def _set_input(
    workflow: dict[str, Any],
    node_id: str,
    key: str,
    value: Any,
) -> None:
    node = workflow.get(node_id)
    if not isinstance(node, dict):
        raise ValueError(f"Cannot wire missing node {node_id!r}")
    node.setdefault("inputs", {})[key] = value


def _needs_main_decode(
    *,
    refine_on: bool,
    upscale_timing: str,
    detailer_timing: str,
    detailers_on: bool,
) -> bool:
    if not refine_on:
        return False
    if upscale_timing == UPSCALE_TIMING_BEFORE:
        return True
    return detailer_timing == DETAILER_TIMING_BEFORE and detailers_on


def _needs_vae_encode(
    *,
    refine_on: bool,
    upscale_timing: str,
    detailer_timing: str,
    detailers_on: bool,
) -> bool:
    if not refine_on:
        return False
    if upscale_timing == UPSCALE_TIMING_BEFORE:
        return True
    return detailer_timing == DETAILER_TIMING_BEFORE and detailers_on


def _ensure_main_decode_node(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    registry: dict[str, str],
) -> None:
    role = nodes["main_decode"]
    if role in workflow:
        return
    workflow[role] = _instantiate_pipeline_node(role, registry=registry)
    _set_input(workflow, role, "samples", [nodes["sampler"], 0])
    _set_input(workflow, role, "vae", [nodes["checkpoint"], 2])


def _ensure_vae_encode_node(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    registry: dict[str, str],
) -> None:
    role = nodes["vae_encode"]
    if role in workflow:
        return
    workflow[role] = _instantiate_pipeline_node(role, registry=registry)


def _include_sets(
    *,
    refine_on: bool,
    upscale_timing: str,
    detailer_timing: str = DETAILER_TIMING_DISABLED,
    detailers_on: bool = False,
) -> list[str]:
    recipe = _load_recipe()
    include = list(recipe.get("base_include") or [])
    optional = recipe.get("optional_sets") or {}
    if refine_on:
        include.extend(optional.get("refine") or [])
    if upscale_timing != UPSCALE_TIMING_DISABLED:
        include.extend(optional.get("upscale") or [])
    if _needs_vae_encode(
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        detailers_on=detailers_on,
    ):
        include.extend(optional.get("upscale_before_encode") or [])
    if _needs_main_decode(
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        detailers_on=detailers_on,
    ):
        include.append(load_registry()["main_decode"])
    return list(dict.fromkeys(include))


def _region_label(manifest: dict[str, Any], region: str) -> str:
    meta = (manifest.get("regions") or {}).get(region) or {}
    return str(meta.get("label") or region.replace("_", " ").title())


def _format_title(template: str, *, label: str, region: str) -> str:
    return (
        template.replace("{{label}}", label)
        .replace("{{region}}", region)
        .replace("{{id}}", region)
    )


def _instantiate_detailer_template(
    template_name: str,
    *,
    region: str,
    label: str,
    node_id: str,
    registry: dict[str, str],
    context: dict[str, str],
) -> dict[str, Any]:
    raw = load_node_template(template_name)
    inputs = copy.deepcopy(raw.get("inputs") or {})
    defaults = copy.deepcopy(raw.get("defaults") or {})
    for key, val in defaults.items():
        inputs.setdefault(key, val)
    resolved = _resolve_value(inputs, registry=registry, context=context)
    meta = copy.deepcopy(raw.get("_meta") or {})
    title = meta.get("title")
    if isinstance(title, str):
        meta["title"] = _format_title(title, label=label, region=region)
    return {
        "inputs": resolved,
        "class_type": raw["class_type"],
        "_meta": meta,
    }


def _include_detailer_pipe(
    *,
    is_last: bool,
    refine_enabled: bool,
    timing: str,
) -> bool:
    """Pipe nodes carry the stack to the next region or into refine (before only)."""
    if not is_last:
        return True
    return refine_enabled and timing == DETAILER_TIMING_BEFORE


def _detailer_stack_external(
    nodes: dict[str, str],
    *,
    timing: str,
    refine_enabled: bool,
    upscale_enabled: bool,
) -> dict[str, str]:
    if refine_enabled:
        return {
            "detail_image": (
                nodes["refine_decode"]
                if timing == DETAILER_TIMING_AFTER
                else nodes["main_decode"]
            ),
            "detail_model": nodes["refine_lora"],
            "detail_clip": nodes["clip_skip"],
            "detail_vae": nodes["refine_checkpoint"],
            "detail_negative": nodes["refine_negative"],
            "detail_main_positive": nodes["refine_positive"],
        }
    if timing == DETAILER_TIMING_AFTER:
        image = nodes["upscale_scale"] if upscale_enabled else nodes["base_decode"]
    else:
        image = nodes["base_decode"]
    return {
        "detail_image": image,
        "detail_model": nodes["checkpoint"],
        "detail_clip": nodes["clip_skip"],
        "detail_vae": nodes["checkpoint"],
        "detail_negative": nodes["negative"],
        "detail_main_positive": nodes["positive"],
    }


def instantiate_detailer_region(
    workflow: dict[str, Any],
    region: str,
    *,
    prev: DetailerStageNodes | None,
    timing: str,
    refine_enabled: bool,
    upscale_enabled: bool,
    nodes: dict[str, str],
    registry: dict[str, str],
    is_last: bool = True,
) -> DetailerStageNodes:
    manifest = load_detailer_manifest()
    label = _region_label(manifest, region)
    is_first = prev is None
    suffix = "first" if is_first else "chain"

    det_id = _stage_node_id(region, "det")
    sam_id = _stage_node_id(region, "sam")
    fd_id = _stage_node_id(region, "fd")
    pos_id = _stage_node_id(region, "pos")
    to_pipe_id = _stage_node_id(region, "to_pipe")
    from_pipe_id = _stage_node_id(region, "from_pipe")

    stack = _detailer_stack_external(
        nodes,
        timing=timing,
        refine_enabled=refine_enabled,
        upscale_enabled=upscale_enabled,
    )
    include_pipe = _include_detailer_pipe(
        is_last=is_last,
        refine_enabled=refine_enabled,
        timing=timing,
    )
    context: dict[str, str] = {
        **stack,
        "detail_detector": det_id,
        "detail_sam": sam_id,
        "detail_positive": pos_id,
    }
    if include_pipe:
        context["detail_to_pipe"] = to_pipe_id
    if prev is not None:
        context["prev_detailer"] = prev.face_detailer
        if prev.from_basic_pipe:
            context["prev_from_pipe"] = prev.from_basic_pipe

    workflow[det_id] = _instantiate_detailer_template(
        f"detail_detector_{suffix}",
        region=region,
        label=label,
        node_id=det_id,
        registry=registry,
        context=context,
    )
    workflow[sam_id] = _instantiate_detailer_template(
        "detail_sam",
        region=region,
        label=label,
        node_id=sam_id,
        registry=registry,
        context=context,
    )
    workflow[pos_id] = _instantiate_detailer_template(
        f"detailer_pos_{suffix}",
        region=region,
        label=label,
        node_id=pos_id,
        registry=registry,
        context=context,
    )
    if include_pipe:
        workflow[to_pipe_id] = _instantiate_detailer_template(
            f"detailer_to_pipe_{suffix}",
            region=region,
            label=label,
            node_id=to_pipe_id,
            registry=registry,
            context=context,
        )
        workflow[from_pipe_id] = _instantiate_detailer_template(
            "detailer_from_pipe",
            region=region,
            label=label,
            node_id=from_pipe_id,
            registry=registry,
            context=context,
        )
    workflow[fd_id] = _instantiate_detailer_template(
        f"detailer_fd_{suffix}",
        region=region,
        label=label,
        node_id=fd_id,
        registry=registry,
        context=context,
    )

    return DetailerStageNodes(
        region=region,
        face_detailer=fd_id,
        from_basic_pipe=from_pipe_id if include_pipe else "",
        positive=pos_id,
        detector=det_id,
        sam=sam_id,
    )


def _wire_export_image(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    image_source: list[Any],
    *,
    upscale_on: bool,
) -> None:
    """Route export through ``upscale_restore`` when upscale ran at higher resolution."""
    reg = nodes
    if upscale_on and reg["upscale_restore"] in workflow:
        _set_input(workflow, reg["upscale_restore"], "image", image_source)
        export_source: list[Any] = [reg["upscale_restore"], 0]
    else:
        export_source = image_source
    _set_input(workflow, reg["export_image"], "images", export_source)


def _apply_inference_links(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    refine_on: bool,
    upscale_timing: str,
    upscale_on: bool = False,
) -> None:
    reg = nodes
    if refine_on and upscale_timing == UPSCALE_TIMING_BEFORE:
        _set_input(workflow, reg["main_decode"], "samples", [reg["sampler"], 0])
        _set_input(workflow, reg["main_decode"], "vae", [reg["checkpoint"], 2])
        _set_input(
            workflow, reg["upscale_with_model"], "image", [reg["main_decode"], 0]
        )
        _set_input(workflow, reg["vae_encode"], "pixels", [reg["upscale_scale"], 0])
        _set_input(workflow, reg["vae_encode"], "vae", [reg["checkpoint"], 2])
        _set_input(
            workflow, reg["refine_sampler"], "latent_image", [reg["vae_encode"], 0]
        )
        _set_input(
            workflow, reg["refine_decode"], "samples", [reg["refine_sampler"], 0]
        )
        _set_input(workflow, reg["refine_decode"], "vae", [reg["checkpoint"], 2])
        _set_input(workflow, reg["refine_positive"], "clip", [reg["clip_skip"], 0])
        _set_input(workflow, reg["refine_negative"], "clip", [reg["clip_skip"], 0])
        _wire_export_image(
            workflow,
            reg,
            [reg["refine_decode"], 0],
            upscale_on=upscale_on,
        )
        return

    if refine_on:
        if reg["main_decode"] in workflow:
            _set_input(workflow, reg["main_decode"], "samples", [reg["sampler"], 0])
            _set_input(workflow, reg["main_decode"], "vae", [reg["checkpoint"], 2])
        _set_input(workflow, reg["refine_sampler"], "latent_image", [reg["sampler"], 0])
        _set_input(
            workflow, reg["refine_decode"], "samples", [reg["refine_sampler"], 0]
        )
        _set_input(workflow, reg["refine_decode"], "vae", [reg["checkpoint"], 2])
        _set_input(workflow, reg["refine_positive"], "clip", [reg["clip_skip"], 0])
        _set_input(workflow, reg["refine_negative"], "clip", [reg["clip_skip"], 0])
        if upscale_timing == UPSCALE_TIMING_AFTER:
            _set_input(
                workflow, reg["upscale_with_model"], "image", [reg["refine_decode"], 0]
            )
            _wire_export_image(
                workflow,
                reg,
                [reg["upscale_scale"], 0],
                upscale_on=upscale_on,
            )
        else:
            _wire_export_image(
                workflow,
                reg,
                [reg["refine_decode"], 0],
                upscale_on=upscale_on,
            )
        return

    _set_input(workflow, reg["refine_decode"], "samples", [reg["sampler"], 0])
    _set_input(workflow, reg["refine_decode"], "vae", [reg["checkpoint"], 2])
    if upscale_timing == UPSCALE_TIMING_AFTER:
        _set_input(
            workflow, reg["upscale_with_model"], "image", [reg["refine_decode"], 0]
        )
        _wire_export_image(
            workflow,
            reg,
            [reg["upscale_scale"], 0],
            upscale_on=upscale_on,
        )
    else:
        _wire_export_image(
            workflow,
            reg,
            [reg["refine_decode"], 0],
            upscale_on=upscale_on,
        )


def _apply_detailer_links(
    workflow: dict[str, Any],
    nodes: dict[str, str],
    *,
    stages: list[DetailerStageNodes],
    timing: str,
    refine_on: bool,
    upscale_on: bool,
    upscale_timing: str,
    refine_rewire: dict[str, str],
) -> None:
    if not stages:
        return
    last = stages[-1]
    reg = nodes

    if timing == DETAILER_TIMING_BEFORE:
        image_source = last.face_detailer
        if refine_on:
            if upscale_on and upscale_timing == UPSCALE_TIMING_BEFORE:
                _set_input(
                    workflow, reg["upscale_with_model"], "image", [image_source, 0]
                )
                encode_pixels: list[Any] = [reg["upscale_scale"], 0]
            else:
                encode_pixels = [image_source, 0]
            _set_input(workflow, reg["vae_encode"], "pixels", encode_pixels)
            _set_input(workflow, reg["vae_encode"], "vae", [reg["checkpoint"], 2])
            refine = workflow[reg["refine_sampler"]]["inputs"]
            refine["latent_image"] = [reg["vae_encode"], 0]
            if last.from_basic_pipe:
                refine["model"] = [last.from_basic_pipe, 0]
                refine["positive"] = [last.from_basic_pipe, 3]
                refine["negative"] = [last.from_basic_pipe, 4]
            if upscale_on and upscale_timing == UPSCALE_TIMING_AFTER:
                _set_input(
                    workflow,
                    reg["upscale_with_model"],
                    "image",
                    [reg["refine_decode"], 0],
                )
                _wire_export_image(
                    workflow,
                    reg,
                    [reg["upscale_scale"], 0],
                    upscale_on=upscale_on,
                )
            else:
                _wire_export_image(
                    workflow,
                    reg,
                    [reg["refine_decode"], 0],
                    upscale_on=upscale_on,
                )
        elif upscale_on and upscale_timing == UPSCALE_TIMING_AFTER:
            _set_input(workflow, reg["upscale_with_model"], "image", [image_source, 0])
            _wire_export_image(
                workflow,
                reg,
                [reg["upscale_scale"], 0],
                upscale_on=upscale_on,
            )
        else:
            _wire_export_image(
                workflow,
                reg,
                [image_source, 0],
                upscale_on=upscale_on,
            )
        return

    if upscale_on and upscale_timing == UPSCALE_TIMING_AFTER:
        _set_input(
            workflow, reg["upscale_with_model"], "image", [reg["refine_decode"], 0]
        )
    if refine_on:
        refine = workflow[reg["refine_sampler"]]["inputs"]
        refine["model"] = [refine_rewire["model"], 0]
        refine["positive"] = [refine_rewire["positive"], 0]
        refine["negative"] = [refine_rewire["negative"], 0]
    _wire_export_image(
        workflow,
        reg,
        [last.face_detailer, 0],
        upscale_on=upscale_on,
    )


def build_pipeline_workflow(
    *,
    refine_on: bool,
    upscale_timing: str,
    detailer_timing: str,
    enabled_detailers: list[str],
    refine_rewire: dict[str, str],
    upscale_enabled: bool | None = None,
) -> ComposeResult:
    registry = load_registry()
    nodes = registry_nodes()
    upscale_on = (
        upscale_enabled
        if upscale_enabled is not None
        else upscale_timing != UPSCALE_TIMING_DISABLED
    )

    workflow: dict[str, Any] = {}
    detailers_on = detailer_timing != DETAILER_TIMING_DISABLED and bool(
        enabled_detailers
    )
    for role in _include_sets(
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        detailers_on=detailers_on,
    ):
        workflow[role] = _instantiate_pipeline_node(role, registry=registry)

    stages: list[DetailerStageNodes] = []
    if detailer_timing != DETAILER_TIMING_DISABLED and enabled_detailers:
        prev: DetailerStageNodes | None = None
        for index, region in enumerate(enabled_detailers):
            stage = instantiate_detailer_region(
                workflow,
                region,
                prev=prev,
                timing=detailer_timing,
                refine_enabled=refine_on,
                upscale_enabled=upscale_on,
                nodes=nodes,
                registry=registry,
                is_last=index == len(enabled_detailers) - 1,
            )
            stages.append(stage)
            prev = stage

    _apply_inference_links(
        workflow,
        nodes,
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        upscale_on=upscale_on,
    )
    _apply_detailer_links(
        workflow,
        nodes,
        stages=stages,
        timing=detailer_timing,
        refine_on=refine_on,
        upscale_on=upscale_on,
        upscale_timing=upscale_timing,
        refine_rewire=refine_rewire,
    )

    validate_composed_workflow(workflow)
    return ComposeResult(
        workflow=workflow,
        stages=stages,
        refine_on=refine_on,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
        nodes=nodes,
    )


def validate_composed_workflow(workflow: dict[str, Any]) -> None:
    """Raise when a link target is missing from the composed graph."""
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        for key, val in inputs.items():
            if not isinstance(val, list) or not val:
                continue
            if not isinstance(val[0], str):
                continue
            ref = val[0]
            if ref.startswith("@"):
                continue
            if ref not in workflow:
                raise ValueError(
                    f"Composed workflow link {node_id}.{key} -> {ref!r} "
                    f"targets missing node"
                )


def infer_upscale_timing(workflow: dict[str, Any]) -> str | None:
    nodes = registry_nodes()
    has_upscale = nodes["upscale_model"] in workflow
    if nodes["vae_encode"] in workflow:
        encode = workflow.get(nodes["vae_encode"]) or {}
        pixels = (encode.get("inputs") or {}).get("pixels")
        if (
            isinstance(pixels, list)
            and pixels
            and str(pixels[0]) == nodes["upscale_scale"]
        ):
            return UPSCALE_TIMING_BEFORE
    if not has_upscale:
        return None
    return UPSCALE_TIMING_AFTER


def infer_detailer_timing(workflow: dict[str, Any]) -> str | None:
    main_decode = registry_nodes()["main_decode"]
    refine_decode = registry_nodes()["refine_decode"]
    for node_id, node in workflow.items():
        nid = str(node_id)
        if not nid.startswith("detail:") or not nid.endswith(":fd"):
            continue
        if not isinstance(node, dict):
            continue
        img = (node.get("inputs") or {}).get("image")
        if not isinstance(img, list) or not img:
            continue
        src = str(img[0])
        if src == main_decode:
            return DETAILER_TIMING_BEFORE
        if src == refine_decode:
            return DETAILER_TIMING_AFTER
    return None


def attach_detailer_stages(
    workflow: dict[str, Any],
    enabled_regions: list[str],
    *,
    timing: str,
    refine_enabled: bool,
    upscale_enabled: bool,
    upscale_timing: str,
    refine_rewire: dict[str, str],
    pipeline_nodes: dict[str, str] | None = None,
) -> list[DetailerStageNodes]:
    """Add detailer nodes to an existing pipeline graph and rewire export/upscale."""
    if not enabled_regions:
        return []
    registry = load_registry()
    nodes = pipeline_nodes or registry_nodes()
    if refine_enabled and timing == DETAILER_TIMING_BEFORE and enabled_regions:
        _ensure_main_decode_node(workflow, nodes, registry=registry)
        _ensure_vae_encode_node(workflow, nodes, registry=registry)
    stages: list[DetailerStageNodes] = []
    prev: DetailerStageNodes | None = None
    for index, region in enumerate(enabled_regions):
        stage = instantiate_detailer_region(
            workflow,
            region,
            prev=prev,
            timing=timing,
            refine_enabled=refine_enabled,
            upscale_enabled=upscale_enabled,
            nodes=nodes,
            registry=registry,
            is_last=index == len(enabled_regions) - 1,
        )
        stages.append(stage)
        prev = stage
    _apply_detailer_links(
        workflow,
        nodes,
        stages=stages,
        timing=timing,
        refine_on=refine_enabled,
        upscale_on=upscale_enabled,
        upscale_timing=upscale_timing,
        refine_rewire=refine_rewire,
    )
    validate_composed_workflow(workflow)
    return stages


def load_base_workflow_nodes() -> dict[str, Any]:
    """Return base-only workflow (no optional stages) for validation tests."""
    registry = load_registry()
    recipe = _load_recipe()
    workflow: dict[str, Any] = {}
    for role in recipe.get("base_include") or []:
        workflow[role] = _instantiate_pipeline_node(role, registry=registry)
    _apply_inference_links(
        workflow,
        registry_nodes(),
        refine_on=False,
        upscale_timing=UPSCALE_TIMING_DISABLED,
    )
    validate_composed_workflow(workflow)
    return workflow
