"""Phase-weighted progress for the Make Lab ComfyUI workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .compose import (
    UPSCALE_TIMING_AFTER,
    UPSCALE_TIMING_BEFORE,
)
from ..workflow_builder import infer_upscale_timing
from .detailers import (
    DETAILER_TIMING_AFTER,
    DETAILER_TIMING_BEFORE,
    infer_detailer_timing,
)
from ..workflow import _MAKE_LAB_NODES
from ..workflow_builder import registry_nodes

PHASE_LOAD = "load"
PHASE_INFERENCE = "inference"
PHASE_DETAILERS = "detailers"
PHASE_UPSCALE = "upscale"
PHASE_REFINE = "refine"
PHASE_EXPORT = "export"
PHASE_DOWNLOAD = "download"

_DEFAULT_WEIGHTS: dict[str, float] = {
    PHASE_LOAD: 8.0,
    PHASE_INFERENCE: 28.0,
    PHASE_DETAILERS: 22.0,
    PHASE_UPSCALE: 12.0,
    PHASE_REFINE: 25.0,
    PHASE_EXPORT: 5.0,
}

_PHASE_LABELS: dict[str, str] = {
    PHASE_LOAD: "Loading",
    PHASE_INFERENCE: "Inference",
    PHASE_DETAILERS: "Detailers",
    PHASE_UPSCALE: "Upscale",
    PHASE_REFINE: "Refine",
    PHASE_EXPORT: "Saving",
    PHASE_DOWNLOAD: "Download",
}

_STEP_CLASS_TYPES = frozenset({"KSampler", "FaceDetailer"})

INFERENCE_SAMPLER_NODE = _MAKE_LAB_NODES["sampler"]
_QWEN_INFERENCE_SAMPLER = "ksampler"


def inference_sampler_node_id(workflow: dict[str, Any]) -> str:
    """Main first-pass KSampler id (Qwen uses ``ksampler`` when SDXL stub is pruned)."""
    if _QWEN_INFERENCE_SAMPLER in workflow and INFERENCE_SAMPLER_NODE not in workflow:
        return _QWEN_INFERENCE_SAMPLER
    return INFERENCE_SAMPLER_NODE


def is_inference_sampler_node(node_id: str, workflow: dict[str, Any] | None = None) -> bool:
    nid = str(node_id)
    if workflow is not None:
        return nid == inference_sampler_node_id(workflow)
    return nid in {INFERENCE_SAMPLER_NODE, _QWEN_INFERENCE_SAMPLER}


def _download_status_text(fraction: float, *, with_phase_prefix: bool = False) -> str:
    if fraction < 0.35:
        detail = "waiting for outputs"
    elif fraction < 1.0:
        detail = "saving images"
    else:
        return "Download" if not with_phase_prefix else _PHASE_LABELS[PHASE_DOWNLOAD]
    prefix = (
        f"{_PHASE_LABELS[PHASE_DOWNLOAD]} · " if with_phase_prefix else "Download · "
    )
    return f"{prefix}{detail}"


def _workflow_has_refine(workflow: dict[str, Any]) -> bool:
    return _MAKE_LAB_NODES["refine_sampler"] in workflow


def _workflow_has_upscale(workflow: dict[str, Any]) -> bool:
    return _MAKE_LAB_NODES["upscale_model"] in workflow


def _workflow_phase_order(
    *,
    has_refine: bool,
    has_upscale: bool,
    upscale_timing: str | None,
    detailer_timing: str | None,
) -> tuple[str, ...]:
    order: list[str] = [PHASE_LOAD, PHASE_INFERENCE]
    upscale_before = has_upscale and upscale_timing == UPSCALE_TIMING_BEFORE
    upscale_after = has_upscale and upscale_timing == UPSCALE_TIMING_AFTER

    if detailer_timing == DETAILER_TIMING_BEFORE:
        order.append(PHASE_DETAILERS)
    if upscale_before:
        order.append(PHASE_UPSCALE)
    if has_refine:
        order.append(PHASE_REFINE)
    if detailer_timing == DETAILER_TIMING_AFTER:
        order.append(PHASE_DETAILERS)
    if upscale_after:
        order.append(PHASE_UPSCALE)
    order.append(PHASE_EXPORT)

    return tuple(order)


def _normalize_weights(
    weights: dict[str, float], phase_order: tuple[str, ...]
) -> dict[str, float]:
    total = sum(weights.get(p, 0.0) for p in phase_order)
    if total <= 0:
        n = len(phase_order)
        return {p: 100.0 / n for p in phase_order}
    scale = 100.0 / total
    return {p: weights.get(p, 0.0) * scale for p in phase_order}


def classify_node_phase(
    node_id: str,
    node: dict[str, Any],
    *,
    workflow: dict[str, Any],
    detailer_timing: str | None,
    upscale_timing: str | None,
) -> str:
    """Map a workflow node to a progress phase."""
    reg = registry_nodes()
    nid = str(node_id)
    class_type = str(node.get("class_type") or "")
    has_refine = _workflow_has_refine(workflow)

    if class_type == "FaceDetailer" or (
        nid.startswith("detail:") and nid.endswith(":fd")
    ):
        return PHASE_DETAILERS
    if nid.startswith("detail:"):
        return PHASE_DETAILERS

    if nid == reg["refine_sampler"]:
        return PHASE_REFINE
    if nid == reg["sampler"] or nid == _QWEN_INFERENCE_SAMPLER:
        return PHASE_INFERENCE
    if nid == reg["main_decode"]:
        return PHASE_INFERENCE
    if nid in {reg["refine_decode"], reg["base_decode"]}:
        return PHASE_REFINE if has_refine else PHASE_INFERENCE
    if nid == reg["vae_encode"]:
        if detailer_timing == DETAILER_TIMING_BEFORE and has_refine:
            if upscale_timing == UPSCALE_TIMING_BEFORE:
                return PHASE_UPSCALE
            return PHASE_REFINE
        return PHASE_UPSCALE
    if nid in {reg["upscale_with_model"], reg["upscale_scale"]}:
        return PHASE_UPSCALE
    if class_type == "KSampler":
        return PHASE_REFINE if nid == reg["refine_sampler"] else PHASE_INFERENCE
    if class_type == "VAEDecode":
        if nid == reg["main_decode"]:
            return PHASE_INFERENCE
        return PHASE_REFINE if has_refine else PHASE_INFERENCE
    if nid in {reg["export_image"], reg["save"]}:
        return PHASE_EXPORT
    if nid.startswith("rmbg:"):
        return PHASE_EXPORT
    if nid.startswith("controlnet:"):
        return PHASE_INFERENCE
    return PHASE_LOAD


def _is_step_node(node: dict[str, Any]) -> bool:
    return str(node.get("class_type") or "") in _STEP_CLASS_TYPES


def _detailer_region_count(workflow: dict[str, Any]) -> int:
    return sum(
        1
        for node_id in workflow
        if str(node_id).startswith("detail:") and str(node_id).endswith(":fd")
    )


@dataclass(frozen=True)
class MakeLabProgressPlan:
    """Weights and node grouping for one queued workflow."""

    phase_weights: dict[str, float]
    node_phase: dict[str, str]
    phase_node_ids: dict[str, tuple[str, ...]]
    phase_step_nodes: dict[str, tuple[str, ...]]
    step_nodes: frozenset[str]
    node_titles: dict[str, str]
    detailer_count: int
    phase_order: tuple[str, ...]

    def phase_label(self, phase_id: str) -> str:
        return _PHASE_LABELS.get(phase_id, phase_id)

    def node_title(self, node_id: str | None) -> str | None:
        if not node_id:
            return None
        return self.node_titles.get(str(node_id)) or str(node_id)


def build_progress_plan(
    workflow: dict[str, Any],
    node_titles: dict[str, str] | None = None,
) -> MakeLabProgressPlan:
    """Build a phase plan from a patched Make Lab API workflow."""
    titles = dict(node_titles or {})
    node_phase: dict[str, str] = {}
    step_nodes: set[str] = set()
    has_detailers = _detailer_region_count(workflow) > 0
    detailer_timing = infer_detailer_timing(workflow) if has_detailers else None
    upscale_timing = infer_upscale_timing(workflow)
    has_refine = _workflow_has_refine(workflow)
    has_upscale = _workflow_has_upscale(workflow)
    phase_order = _workflow_phase_order(
        has_refine=has_refine,
        has_upscale=has_upscale,
        upscale_timing=upscale_timing,
        detailer_timing=detailer_timing,
    )
    phase_buckets: dict[str, list[str]] = {p: [] for p in phase_order}
    phase_step_buckets: dict[str, list[str]] = {p: [] for p in phase_order}

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
        phase = classify_node_phase(
            nid,
            node,
            workflow=workflow,
            detailer_timing=detailer_timing,
            upscale_timing=upscale_timing,
        )
        if phase not in phase_buckets:
            phase = PHASE_LOAD
        node_phase[nid] = phase
        phase_buckets.setdefault(phase, []).append(nid)
        if _is_step_node(node):
            step_nodes.add(nid)
            phase_step_buckets.setdefault(phase, []).append(nid)

    weights = dict(_DEFAULT_WEIGHTS)
    if not has_detailers:
        weights[PHASE_DETAILERS] = 0.0
    if not has_upscale:
        weights[PHASE_UPSCALE] = 0.0
    if not has_refine:
        weights[PHASE_REFINE] = 0.0
    weights = _normalize_weights(weights, phase_order)

    phase_node_ids = {p: tuple(phase_buckets.get(p) or ()) for p in phase_order}
    phase_step_nodes = {p: tuple(phase_step_buckets.get(p) or ()) for p in phase_order}

    return MakeLabProgressPlan(
        phase_weights=weights,
        node_phase=node_phase,
        phase_node_ids=phase_node_ids,
        phase_step_nodes=phase_step_nodes,
        step_nodes=frozenset(step_nodes),
        node_titles=titles,
        detailer_count=_detailer_region_count(workflow),
        phase_order=phase_order,
    )


@dataclass
class ProgressTracker:
    """Mutable execution state for one generation job."""

    plan: MakeLabProgressPlan
    ws_prompt_active: bool = False
    nodes_done: set[str] = field(default_factory=set)
    active_node: str | None = None
    value: int = 0
    max: int = 0
    download_fraction: float = 0.0
    in_finalize: bool = False
    inference_complete: bool = False

    def phase_for_node(self, node_id: str | None) -> str | None:
        if not node_id:
            return None
        return self.plan.node_phase.get(str(node_id))

    def mark_node_done(self, node_id: str | None) -> None:
        if node_id:
            self.nodes_done.add(str(node_id))

    def _node_fraction(self, node_id: str) -> float:
        if node_id in self.nodes_done:
            return 1.0
        if node_id in self.plan.step_nodes:
            if self.active_node == node_id and self.max > 0:
                return max(0.0, min(1.0, self.value / self.max))
            return 0.0
        if self.active_node == node_id:
            return 0.5
        return 0.0

    def _phase_fraction(self, phase_id: str) -> float:
        node_ids = self.plan.phase_node_ids.get(phase_id) or ()
        if not node_ids:
            return 0.0
        parts = [self._node_fraction(nid) for nid in node_ids]
        return sum(parts) / len(parts)

    def overall_pct(self, *, complete: bool = False) -> int:
        if complete or self.inference_complete:
            return 100
        total = 0.0
        for phase_id in self.plan.phase_order:
            w = self.plan.phase_weights.get(phase_id, 0.0)
            total += w * self._phase_fraction(phase_id)
        return min(99, max(0, int(round(total))))

    def download_pct(self) -> int:
        return min(100, max(0, int(round(self.download_fraction * 100))))

    def active_phase(self) -> str | None:
        if self.in_finalize:
            return PHASE_DOWNLOAD
        if self.active_node:
            return self.plan.node_phase.get(self.active_node)
        return None

    def executing_label(self) -> str | None:
        phase = self.active_phase()
        if phase == PHASE_DOWNLOAD:
            return _download_status_text(
                self.download_fraction, with_phase_prefix=False
            )

        title = self.plan.node_title(self.active_node)
        if not title:
            return self.plan.phase_label(phase) if phase else None
        if self.max > 0 and self.active_node in self.plan.step_nodes:
            return f"{title} ({self.value}/{self.max})"
        return title

    def sampler_step_label(self) -> str | None:
        if self.max <= 0 or self.active_node not in self.plan.step_nodes:
            return None
        return f"{self.value}/{self.max}"

    def set_asset_fetch_fraction(self, fraction: float) -> None:
        """ComfyUI asset-download phase (before inference)."""
        self.download_fraction = max(0.0, min(1.0, fraction))

    def set_download_fraction(self, fraction: float) -> None:
        self.in_finalize = True
        self.active_node = None
        self.value = 0
        self.max = 0
        self.download_fraction = max(0.0, min(1.0, fraction))

    def mark_inference_complete(self) -> None:
        """ComfyUI execution finished; workflow progress is 100%."""
        self.inference_complete = True
        self.in_finalize = True
        self.active_node = None
        self.value = 0
        self.max = 0
        for phase_nodes in self.plan.phase_node_ids.values():
            for nid in phase_nodes:
                self.nodes_done.add(nid)

    def begin_finalize(self) -> None:
        if not self.inference_complete:
            self.mark_inference_complete()
        self.download_fraction = 0.0

    def download_label(self) -> str:
        return _download_status_text(self.download_fraction)
