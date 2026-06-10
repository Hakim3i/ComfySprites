"""Patch Make workflow export settings."""

from __future__ import annotations

from typing import Any

from .workflow_builder import registry_nodes

_NODES = registry_nodes()
MAKE_LAB_EXPORT_IMAGE_NODE_ID = _NODES["export_image"]


def export_compress_enabled(request: dict[str, Any] | None) -> bool:
    if not request:
        return True
    raw = request.get("export_compress")
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def patch_make_lab_export(
    workflow: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
) -> None:
    from .make_lab.rmbg import rmbg_settings_from_request

    node = workflow.get(MAKE_LAB_EXPORT_IMAGE_NODE_ID)
    if not isinstance(node, dict):
        return
    inputs = node.setdefault("inputs", {})
    inputs["enabled"] = export_compress_enabled(request)
    rmbg = rmbg_settings_from_request(request)
    if rmbg and str(rmbg.get("background") or "") == "Alpha":
        inputs["format"] = "png"
