"""Phase-weighted progress for the Wan 2.2 ComfyUI workflow."""

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
from .workflow import WAN22_VIDEO_OUTPUT_NODE_ID

_WAN_PHASE_ORDER = (PHASE_LOAD, PHASE_INFERENCE, PHASE_EXPORT)

_STEP_NODES = frozenset({"sampler_high", "sampler_low"})

_DEFAULT_WEIGHTS: dict[str, float] = {
    PHASE_LOAD: 15.0,
    PHASE_INFERENCE: 70.0,
    PHASE_EXPORT: 15.0,
}

_LOAD_CLASS_TYPES = frozenset(
    {
        "UNETLoader",
        "VAELoader",
        "CLIPLoader",
        "LoadImage",
        "LoraLoader",
        "LoraLoaderModelOnly",
        "CLIPTextEncode",
        "ModelSamplingSD3",
    }
)

_INFERENCE_CLASS_TYPES = frozenset(
    {
        "KSamplerAdvanced",
        "VAEDecode",
        "WanImageToVideo",
        "WanFirstLastFrameToVideo",
        "CreateVideo",
    }
)

_EXPORT_CLASS_TYPES = frozenset({"SaveVideo"})


def _blueprint_phase_map() -> dict[str, str]:
    phases = _load_pipeline_blueprint("wan22").get("phases") or {}
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
    if nid in _STEP_NODES or nid == WAN22_VIDEO_OUTPUT_NODE_ID:
        return PHASE_INFERENCE if nid in _STEP_NODES else PHASE_EXPORT

    class_type = str(node.get("class_type") or "")
    title = ""
    meta = node.get("_meta")
    if isinstance(meta, dict):
        title = str(meta.get("title") or "")

    if class_type in _LOAD_CLASS_TYPES:
        return PHASE_LOAD
    if class_type in _INFERENCE_CLASS_TYPES:
        return PHASE_INFERENCE
    if class_type in _EXPORT_CLASS_TYPES:
        return PHASE_EXPORT
    if "Load" in title:
        return PHASE_LOAD
    return PHASE_LOAD


def _is_step_node(node_id: str, node: dict[str, Any]) -> bool:
    if str(node_id) in _STEP_NODES:
        return True
    return str(node.get("class_type") or "") == "KSamplerAdvanced"


def build_wan22_progress_plan(
    workflow: dict[str, Any],
    node_titles: dict[str, str] | None = None,
) -> MakeLabProgressPlan:
    """Build a phase plan from a patched Wan 2.2 API workflow."""
    titles = dict(node_titles or {})
    phase_map = _blueprint_phase_map()
    node_phase: dict[str, str] = {}
    step_nodes: set[str] = set()
    phase_buckets: dict[str, list[str]] = {p: [] for p in _WAN_PHASE_ORDER}
    phase_step_buckets: dict[str, list[str]] = {p: [] for p in _WAN_PHASE_ORDER}

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

    weights = _normalize_weights(dict(_DEFAULT_WEIGHTS), _WAN_PHASE_ORDER)
    phase_node_ids = {p: tuple(phase_buckets.get(p) or ()) for p in _WAN_PHASE_ORDER}
    phase_step_nodes = {
        p: tuple(phase_step_buckets.get(p) or ()) for p in _WAN_PHASE_ORDER
    }

    return MakeLabProgressPlan(
        phase_weights=weights,
        node_phase=node_phase,
        phase_node_ids=phase_node_ids,
        phase_step_nodes=phase_step_nodes,
        step_nodes=frozenset(step_nodes),
        node_titles=titles,
        detailer_count=0,
        phase_order=_WAN_PHASE_ORDER,
    )
