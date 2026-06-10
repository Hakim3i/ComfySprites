"""Compare Make build asset manifests against files installed on ComfyUI."""

from __future__ import annotations

from typing import Any

from .asset_manifest import (
    make_lab_checkpoints_manifest,
    make_lab_controlnets_manifest,
    make_lab_detailer_assets_manifest,
    make_lab_loras_manifest,
    make_lab_upscalers_manifest,
)
from .client import (
    ComfyUIRequestError,
    list_checkpoints,
    list_controlnets,
    list_loras,
    list_sams_models,
    list_ultralytics_models,
    list_upscale_models,
)


def _installed_set(names: list[str] | None) -> frozenset[str]:
    if not names:
        return frozenset()
    return frozenset(str(n).lower() for n in names if n)


def _missing_from_manifest(
    entries: list[dict[str, Any]],
    installed: frozenset[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = (entry.get("filename") or "").strip()
        if not filename:
            continue
        if filename.lower() not in installed:
            out.append(entry)
    return out


def _missing_detailers_from_manifest(
    entries: list[dict[str, Any]],
    ultralytics: frozenset[str],
    sams: frozenset[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("relative_path") or entry.get("filename") or "").strip()
        if not rel:
            continue
        folder = str(entry.get("folder") or "").strip().lower()
        installed = sams if folder == "sams" else ultralytics
        if rel.lower() not in installed:
            out.append(entry)
    return out


def installed_assets(base_url: str | None) -> dict[str, frozenset[str]] | None:
    """Installed checkpoint / LoRA / ControlNet filenames on ComfyUI (``None`` if unreachable)."""
    try:
        return {
            "checkpoints": _installed_set(list_checkpoints(base_url)),
            "loras": _installed_set(list_loras(base_url)),
            "controlnets": _installed_set(list_controlnets(base_url)),
            "upscalers": _installed_set(list_upscale_models(base_url)),
            "ultralytics": _installed_set(list_ultralytics_models(base_url)),
            "sams": _installed_set(list_sams_models(base_url)),
        }
    except (OSError, ComfyUIRequestError):
        return None


def required_assets(build: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Manifest rows for all assets referenced by a Make build."""
    return {
        "checkpoints": make_lab_checkpoints_manifest(build),
        "loras": make_lab_loras_manifest(build),
        "controlnets": make_lab_controlnets_manifest(build),
        "upscalers": make_lab_upscalers_manifest(build),
        "detailers": make_lab_detailer_assets_manifest(build),
    }


def missing_assets(
    build: dict[str, Any],
    base_url: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Manifest rows not yet present on the ComfyUI host."""
    installed = installed_assets(base_url)
    required = required_assets(build)
    if installed is None:
        return required
    return {
        "checkpoints": _missing_from_manifest(
            required["checkpoints"], installed["checkpoints"]
        ),
        "loras": _missing_from_manifest(required["loras"], installed["loras"]),
        "controlnets": _missing_from_manifest(
            required["controlnets"], installed["controlnets"]
        ),
        "upscalers": _missing_from_manifest(
            required["upscalers"], installed["upscalers"]
        ),
        "detailers": _missing_detailers_from_manifest(
            required["detailers"],
            installed["ultralytics"],
            installed["sams"],
        ),
    }


def assets_ready(build: dict[str, Any], base_url: str | None) -> bool:
    """True when every required asset filename is listed on ComfyUI."""
    missing = missing_assets(build, base_url)
    return not any(
        missing[k]
        for k in ("checkpoints", "loras", "controlnets", "upscalers", "detailers")
    )


def count_missing_assets(missing: dict[str, list[dict[str, Any]]]) -> int:
    """Number of manifest rows that still need downloading."""
    return sum(
        len(missing.get(key) or [])
        for key in ("checkpoints", "loras", "controlnets", "upscalers", "detailers")
    )


def missing_filenames(missing: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Flat list of missing filenames for error messages."""
    names: list[str] = []
    for key in ("checkpoints", "loras", "controlnets", "upscalers", "detailers"):
        for entry in missing.get(key) or []:
            fn = (entry.get("filename") or "").strip()
            if fn:
                names.append(fn)
    return names
