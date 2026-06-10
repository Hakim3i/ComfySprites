"""Detailer manifest, request parsing, and runtime patches for Make Lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
DETAILERS_MANIFEST_PATH = WORKFLOWS_DIR / "recipes" / "detailers.json"
_SHIPPED_SETTINGS_PATH = PROJECT_ROOT / "dataset" / "make_lab_detailers.json"

DETAILER_TIMING_BEFORE = "before"
DETAILER_TIMING_AFTER = "after"
DETAILER_TIMING_DISABLED = "disabled"
DETAILER_TIMING_VALUES = frozenset(
    {DETAILER_TIMING_BEFORE, DETAILER_TIMING_AFTER, DETAILER_TIMING_DISABLED}
)

_FACE_DETAILER_LINK_KEYS = frozenset(
    {
        "image",
        "model",
        "clip",
        "vae",
        "positive",
        "negative",
        "bbox_detector",
        "sam_model_opt",
        "segm_detector_opt",
        "seed",
    }
)


def _settings_path() -> Path:
    for path in (DATASET_DIR / "make_lab_detailers.json", _SHIPPED_SETTINGS_PATH):
        if path.is_file():
            return path
    return _SHIPPED_SETTINGS_PATH


def default_detailer_timing(*, separate_refine_model: bool) -> str:
    """After refine when inference/refine share a checkpoint; before when they differ."""
    return DETAILER_TIMING_BEFORE if separate_refine_model else DETAILER_TIMING_AFTER


def resolve_detailer_timing(
    request: dict[str, Any] | None,
    *,
    separate_refine_model: bool,
) -> str:
    raw = str((request or {}).get("detailer_timing") or "").strip().lower()
    if raw in DETAILER_TIMING_VALUES:
        return raw
    return default_detailer_timing(separate_refine_model=separate_refine_model)


def infer_detailer_timing(workflow: dict[str, Any]) -> str | None:
    from ..workflow_builder import infer_detailer_timing as _infer

    return _infer(workflow)


def _refine_stack_rewire() -> dict[str, str]:
    from ..workflow import REFINE_STACK_REWIRE

    return REFINE_STACK_REWIRE


@dataclass(frozen=True)
class DetailerStageNodes:
    """Resolved node ids for one composed detailer region."""

    region: str
    face_detailer: str
    from_basic_pipe: str
    positive: str
    detector: str
    sam: str


def _stage_node_id(region: str, role: str) -> str:
    return f"detail:{region}:{role}"


@lru_cache(maxsize=1)
def load_detailer_manifest() -> dict[str, Any]:
    raw = DETAILERS_MANIFEST_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def load_detailer_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {"version": 1, "quality_prefix": "", "regions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def detailer_catalog() -> list[dict[str, Any]]:
    """Regions for Make UI (order preserved)."""
    manifest = load_detailer_manifest()
    settings = load_detailer_settings()
    settings_regions = settings.get("regions") or {}
    out: list[dict[str, Any]] = []
    for region_id in manifest.get("order") or []:
        meta = (manifest.get("regions") or {}).get(region_id) or {}
        cfg = settings_regions.get(region_id) or {}
        out.append(
            {
                "id": region_id,
                "label": meta.get("label") or cfg.get("label") or region_id.title(),
                "detector_model": cfg.get("detector_model"),
            }
        )
    return out


def detailers_from_request(request: dict[str, Any] | None) -> list[str]:
    """Enabled detailer region ids in canonical order."""
    manifest = load_detailer_manifest()
    order = list(manifest.get("order") or [])
    req = request or {}
    raw = req.get("detailers")
    if not raw:
        return []
    selected = {str(x).strip() for x in raw if str(x).strip()}
    if "genitals" in selected:
        selected.discard("genitals")
        selected.add("penis")
        selected.add("pussy")
    return [r for r in order if r in selected]


def compose_detailer_stages(
    workflow: dict[str, Any],
    enabled_regions: list[str],
    *,
    external: dict[str, str] | None = None,
    refine_rewire: dict[str, str] | None = None,
    timing: str = DETAILER_TIMING_AFTER,
    upscale_enabled: bool = True,
    upscale_timing: str = "after",
    refine_enabled: bool = True,
    pipeline_nodes: dict[str, str] | None = None,
) -> list[DetailerStageNodes]:
    """Attach enabled detailer regions to *workflow* (mutates)."""
    del external
    from ..workflow_builder import attach_detailer_stages, registry_nodes

    rewire = refine_rewire if refine_rewire is not None else _refine_stack_rewire()
    return attach_detailer_stages(
        workflow,
        enabled_regions,
        timing=timing,
        refine_enabled=refine_enabled,
        upscale_enabled=upscale_enabled,
        upscale_timing=upscale_timing,
        refine_rewire=rewire,
        pipeline_nodes=pipeline_nodes or registry_nodes(),
    )


def detailer_style_positive_from_render(sdxl: dict[str, Any]) -> str:
    """Refine style prefix only — for FaceDetailer regional CLIP (not full scene)."""
    parts: list[str] = []
    for seg in sdxl.get("positive_segments") or []:
        if str(seg.get("source") or "") != "style":
            continue
        for tag in seg.get("tags") or []:
            t = str(tag).strip()
            if t:
                parts.append(t)
    return ", ".join(parts)


def _format_detailer_prompt(*, base: str, tags: str) -> str:
    base = (base or "").strip()
    tags = (tags or "").strip()
    if tags and base:
        return f"{base},\n{tags}"
    return tags or base


def patch_detailer_prompts(
    workflow: dict[str, Any],
    stages: list[DetailerStageNodes],
    character_adetailer: dict[str, str] | None,
    *,
    detailer_style_positive: str,
    settings: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    regions_cfg = settings.get("regions") or {}
    manifest_regions = manifest.get("regions") or {}
    adetailer = character_adetailer or {}

    for stage in stages:
        cfg = regions_cfg.get(stage.region) or {}
        key = cfg.get("adetailer_key")
        if key is None:
            key = (manifest_regions.get(stage.region) or {}).get("adetailer_key")
        tags = str(adetailer.get(key) or "").strip() if key else ""
        workflow[stage.positive]["inputs"]["text"] = _format_detailer_prompt(
            base=detailer_style_positive,
            tags=tags,
        )


def patch_detailer_detectors(
    workflow: dict[str, Any],
    stages: list[DetailerStageNodes],
    *,
    regions_cfg: dict[str, Any],
) -> None:
    for stage in stages:
        cfg = regions_cfg.get(stage.region) or {}
        det = cfg.get("detector_model")
        sam = cfg.get("sam_model")
        if det:
            workflow[stage.detector]["inputs"]["model_name"] = str(det)
        if sam:
            workflow[stage.sam]["inputs"]["model_name"] = str(sam)


def patch_detailer_seeds(
    workflow: dict[str, Any],
    stages: list[DetailerStageNodes],
    seed: int,
) -> None:
    del workflow, stages, seed


def patch_detailer_face_detailer(
    workflow: dict[str, Any],
    stages: list[DetailerStageNodes],
    *,
    regions_cfg: dict[str, Any],
) -> None:
    for stage in stages:
        overrides = (regions_cfg.get(stage.region) or {}).get("face_detailer")
        if not isinstance(overrides, dict):
            continue
        fd_in = workflow[stage.face_detailer]["inputs"]
        for key, val in overrides.items():
            if key in _FACE_DETAILER_LINK_KEYS:
                continue
            fd_in[key] = val


def apply_detailer_patches(
    workflow: dict[str, Any],
    stages: list[DetailerStageNodes],
    *,
    character_adetailer: dict[str, str] | None,
    detailer_style_positive: str,
    seed: int,
) -> None:
    if not stages:
        return
    settings = load_detailer_settings()
    manifest = load_detailer_manifest()
    regions_cfg = settings.get("regions") or {}
    patch_detailer_prompts(
        workflow,
        stages,
        character_adetailer,
        detailer_style_positive=detailer_style_positive,
        settings=settings,
        manifest=manifest,
    )
    patch_detailer_detectors(workflow, stages, regions_cfg=regions_cfg)
    patch_detailer_face_detailer(workflow, stages, regions_cfg=regions_cfg)
    patch_detailer_seeds(workflow, stages, seed)
