"""Phase-weighted progress for the LTX Studio ComfyUI workflow."""

from __future__ import annotations

from typing import Any

from ..make_lab.progress import (
    PHASE_EXPORT,
    PHASE_INFERENCE,
    PHASE_LOAD,
    MakeLabProgressPlan,
    _normalize_weights,
)
from ..pipeline_builder import _load_pipeline_blueprint
from .workflow import VIDEO_STUDIO_COMBINE_NODE_ID

_LTX_PHASE_ORDER = (PHASE_LOAD, PHASE_INFERENCE, PHASE_EXPORT)

_STEP_NODES = frozenset({"sampler_first_pass"})

_DEFAULT_WEIGHTS: dict[str, float] = {
    PHASE_LOAD: 15.0,
    PHASE_INFERENCE: 70.0,
    PHASE_EXPORT: 15.0,
}

_LOAD_CLASS_TYPES = frozenset(
    {
        "CheckpointLoaderSimple",
        "UNETLoader",
        "VAELoader",
        "DualCLIPLoader",
        "CLIPLoader",
        "LoadImage",
        "DiffusionModelLoaderKJ",
        "LTXVAudioVAELoader",
        "LTXVLatentUpscaleModelLoader",
        "LoadLatentUpscaleModel",
        "LoraLoader",
        "Power Lora Loader (rgthree)",
        "CLIPTextEncode",
        "IntConstant",
        "FloatConstant",
        "Seed (rgthree)",
        "EmptyImage",
        "SolidMask",
    }
)

_INFERENCE_CLASS_TYPES = frozenset(
    {
        "SamplerCustomAdvanced",
        "KSampler",
        "KSamplerSelect",
        "VAEDecode",
        "LTXVImgToVideoInplaceKJ",
        "LTXVConditioning",
        "LTXVConcatAVLatent",
        "CFGGuider",
        "RandomNoise",
        "ManualSigmas",
        "LTXVScheduler",
        "BasicScheduler",
        "ImageResizeKJv2",
        "GetImageSize",
        "AudioAdjustVolume",
        "LTXVSeparateAVLatent",
        "LTXVAudioVAEDecode",
        "LTXVAudioVAEEncode",
        "LTX2_NAG",
        "SetLatentNoiseMask",
        "Sigmas Sigmoid",
    }
)

_EXPORT_CLASS_TYPES = frozenset({"CoomfyExportVideo", "CoomfyExportAudio"})


def _blueprint_phase_map() -> dict[str, str]:
    phases = _load_pipeline_blueprint("ltx_studio").get("phases") or {}
    out: dict[str, str] = {}
    for node_id in phases.get("setup") or []:
        out[str(node_id)] = PHASE_LOAD
    for node_id in phases.get("sampling") or []:
        out[str(node_id)] = PHASE_INFERENCE
    for node_id in phases.get("export") or []:
        out[str(node_id)] = PHASE_EXPORT
    return out


def _classify_node(
    node_id: str,
    node: dict[str, Any],
    *,
    phase_map: dict[str, str],
) -> str:
    nid = str(node_id)
    if nid in phase_map:
        return phase_map[nid]
    if nid in _STEP_NODES or nid == VIDEO_STUDIO_COMBINE_NODE_ID:
        return PHASE_INFERENCE if nid in _STEP_NODES else PHASE_EXPORT
    if nid in {"export_video", "export_audio"}:
        return PHASE_EXPORT

    class_type = str(node.get("class_type") or "")
    title = ""
    meta = node.get("_meta")
    if isinstance(meta, dict):
        title = str(meta.get("title") or "")

    if "Load Distilled Lora" in title or class_type in _LOAD_CLASS_TYPES:
        return PHASE_LOAD
    if class_type in _INFERENCE_CLASS_TYPES:
        return PHASE_INFERENCE
    if class_type in _EXPORT_CLASS_TYPES:
        return PHASE_EXPORT
    return PHASE_LOAD


def _is_step_node(node_id: str, node: dict[str, Any]) -> bool:
    if str(node_id) in _STEP_NODES:
        return True
    return str(node.get("class_type") or "") == "SamplerCustomAdvanced"


def build_ltx_progress_plan(
    workflow: dict[str, Any],
    node_titles: dict[str, str] | None = None,
) -> MakeLabProgressPlan:
    """Build a phase plan from a patched LTX Studio API workflow."""
    titles = dict(node_titles or {})
    phase_map = _blueprint_phase_map()
    node_phase: dict[str, str] = {}
    step_nodes: set[str] = set()
    phase_buckets: dict[str, list[str]] = {p: [] for p in _LTX_PHASE_ORDER}
    phase_step_buckets: dict[str, list[str]] = {p: [] for p in _LTX_PHASE_ORDER}

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        nid = str(node_id)
        if nid not in titles:
            meta = node.get("_meta")
            if isinstance(meta, dict) and meta.get("title"):
                titles[nid] = str(meta["title"])
            else:
                titles[nid] = str(node.get("class_type") or nid)
        phase = _classify_node(nid, node, phase_map=phase_map)
        node_phase[nid] = phase
        phase_buckets.setdefault(phase, []).append(nid)
        if _is_step_node(nid, node):
            step_nodes.add(nid)
            phase_step_buckets.setdefault(phase, []).append(nid)

    weights = _normalize_weights(dict(_DEFAULT_WEIGHTS), _LTX_PHASE_ORDER)
    phase_node_ids = {p: tuple(phase_buckets.get(p) or ()) for p in _LTX_PHASE_ORDER}
    phase_step_nodes = {
        p: tuple(phase_step_buckets.get(p) or ()) for p in _LTX_PHASE_ORDER
    }

    return MakeLabProgressPlan(
        phase_weights=weights,
        node_phase=node_phase,
        phase_node_ids=phase_node_ids,
        phase_step_nodes=phase_step_nodes,
        step_nodes=frozenset(step_nodes),
        node_titles=titles,
        detailer_count=0,
        phase_order=_LTX_PHASE_ORDER,
    )
