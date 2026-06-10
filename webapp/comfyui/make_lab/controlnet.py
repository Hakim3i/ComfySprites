"""Compose Make Lab ControlNet stage before main KSampler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import UPLOADS_DIR, UPLOADS_URL_PREFIX
from ...services.catalog.controlnet_types import controlnet_type_spec
from ..client import upload_image_bytes
from ..workflow_builder import load_node_template, registry_nodes

_SAMPLER_NODE = registry_nodes()["sampler"]
_POSITIVE_NODE = registry_nodes()["positive"]
_NEGATIVE_NODE = registry_nodes()["negative"]


def controlnet_settings_from_request(
    request: dict[str, Any] | None,
    build: dict[str, Any] | None,
) -> dict[str, dict[str, Any]] | None:
    del request  # resolved at compose time in build["controlnet"]
    if not isinstance(build, dict):
        return None
    raw = build.get("controlnet")
    if not isinstance(raw, dict):
        return None
    out = {
        k: dict(v)
        for k, v in raw.items()
        if isinstance(v, dict) and str(v.get("image_path") or "").strip()
    }
    return out or None


def _upload_path_to_local(image_path: str) -> Path:
    prefix = UPLOADS_URL_PREFIX.rstrip("/")
    path = str(image_path or "").strip()
    if path.startswith(prefix + "/"):
        rel = path[len(prefix) + 1 :]
        return (
            UPLOADS_DIR / rel.replace("/", "\\") if "\\" in rel else UPLOADS_DIR / rel
        )
    if path.startswith("/"):
        return UPLOADS_DIR / path.lstrip("/")
    return UPLOADS_DIR / path


def _instantiate_node(
    template_name: str,
    *,
    node_id: str,
    inputs: dict[str, Any],
    class_type: str | None = None,
) -> dict[str, Any]:
    tpl = load_node_template(template_name)
    return {
        "class_type": class_type or tpl["class_type"],
        "_meta": {"title": (tpl.get("_meta") or {}).get("title") or template_name},
        "inputs": inputs,
    }


def apply_controlnet_stage(
    workflow: dict[str, Any],
    request: dict[str, Any] | None,
    build: dict[str, Any] | None,
    *,
    base_url: str | None = None,
) -> list[str]:
    """Insert ControlNet chains and rewire sampler positive/negative inputs."""
    settings = controlnet_settings_from_request(request, build)
    if not settings:
        return []

    if _SAMPLER_NODE not in workflow:
        raise ValueError("Make Lab workflow missing main sampler node")

    positive_source: list[Any] = [_POSITIVE_NODE, 0]
    negative_source: list[Any] = [_NEGATIVE_NODE, 0]
    added: list[str] = []

    for idx, (cn_type, cfg) in enumerate(settings.items()):
        spec = controlnet_type_spec(cn_type)
        if spec is None:
            continue
        local = _upload_path_to_local(cfg["image_path"])
        if not local.is_file():
            raise FileNotFoundError(f"ControlNet image not found: {local}")
        comfy_name = upload_image_bytes(
            local.read_bytes(),
            local.name,
            base_url=base_url,
        )
        prefix = f"controlnet:{cn_type}:{idx}"
        load_id = f"{prefix}:load"
        loader_id = f"{prefix}:loader"
        apply_id = f"{prefix}:apply"

        workflow[load_id] = _instantiate_node(
            "controlnet_load_image",
            node_id=load_id,
            inputs={"image": comfy_name},
        )
        workflow[loader_id] = _instantiate_node(
            "controlnet_loader",
            node_id=loader_id,
            inputs={"control_net_name": spec.control_net},
        )
        workflow[apply_id] = _instantiate_node(
            "controlnet_apply",
            node_id=apply_id,
            inputs={
                "positive": positive_source,
                "negative": negative_source,
                "control_net": [loader_id, 0],
                "image": [load_id, 0],
                "strength": float(cfg.get("strength", spec.default_strength)),
                "start_percent": float(cfg.get("start_percent", spec.default_start)),
                "end_percent": float(cfg.get("end_percent", spec.default_end)),
            },
        )
        positive_source = [apply_id, 0]
        negative_source = [apply_id, 1]
        added.extend([load_id, loader_id, apply_id])

    sampler = workflow[_SAMPLER_NODE]
    sampler_inputs = sampler.setdefault("inputs", {})
    sampler_inputs["positive"] = positive_source
    sampler_inputs["negative"] = negative_source
    return added
