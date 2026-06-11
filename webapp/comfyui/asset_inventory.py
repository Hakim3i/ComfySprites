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
from ..services.catalog.diffusion_models import diffusion_model_ensure_entries, diffusion_model_spec
from .client import (
    ComfyUIRequestError,
    list_checkpoints,
    list_controlnets,
    list_diffusion_models,
    list_loras,
    list_sams_models,
    list_text_encoders,
    list_ultralytics_models,
    list_upscale_models,
    list_vae_models,
)


def _norm_asset_key(name: str) -> str:
    """Case-insensitive key; ComfyUI on Windows uses backslashes in subfolder paths."""
    return str(name or "").strip().replace("\\", "/").lower()


def _installed_set(names: list[str] | None) -> frozenset[str]:
    if not names:
        return frozenset()
    return frozenset(_norm_asset_key(n) for n in names if n)


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
        if _norm_asset_key(filename) not in installed:
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
        if _norm_asset_key(rel) not in installed:
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
        for key in (
            "checkpoints",
            "loras",
            "controlnets",
            "upscalers",
            "detailers",
            "diffusion_models",
            "text_encoders",
            "vae",
        )
    )


def missing_filenames(missing: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Flat list of missing filenames for error messages."""
    names: list[str] = []
    for key in (
        "checkpoints",
        "loras",
        "controlnets",
        "upscalers",
        "detailers",
        "diffusion_models",
        "text_encoders",
        "vae",
    ):
        for entry in missing.get(key) or []:
            fn = (entry.get("filename") or "").strip()
            if fn:
                names.append(fn)
    return names


_DIFFUSION_ASSET_BUCKETS = (
    "diffusion_models",
    "text_encoders",
    "vae",
    "loras",
)


def _installed_diffusion_assets(base_url: str | None) -> dict[str, frozenset[str]] | None:
    try:
        return {
            "diffusion_models": _installed_set(list_diffusion_models(base_url)),
            "text_encoders": _installed_set(list_text_encoders(base_url)),
            "vae": _installed_set(list_vae_models(base_url)),
            "loras": _installed_set(list_loras(base_url)),
        }
    except (OSError, ComfyUIRequestError):
        return None


def required_diffusion_model_assets(model_id: str) -> dict[str, list[dict[str, Any]]]:
    """Manifest rows for a diffusion-model catalog entry, grouped by ComfyUI folder."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "diffusion_models": [],
        "text_encoders": [],
        "vae": [],
        "loras": [],
    }
    for entry in diffusion_model_ensure_entries(model_id):
        folder = str(entry.get("folder") or "").strip()
        if folder in buckets:
            buckets[folder].append(entry)
    return buckets


def _lora_manifest_row(entry: dict[str, Any]) -> dict[str, Any] | None:
    filename = str(entry.get("filename") or "").strip()
    if not filename:
        return None
    row: dict[str, Any] = {
        "filename": filename,
        "name": str(entry.get("name") or filename).strip(),
    }
    if entry.get("download_url"):
        row["download_url"] = entry["download_url"]
    if entry.get("download_fallback_url"):
        row["download_fallback_url"] = entry["download_fallback_url"]
    if entry.get("version_id") is not None:
        row["version_id"] = entry["version_id"]
    if entry.get("model_id") is not None:
        row["model_id"] = entry["model_id"]
    if entry.get("civitai_url"):
        row["civitai_url"] = entry["civitai_url"]
    return row


def missing_loras_from_rows(
    rows: list[dict[str, Any]],
    base_url: str | None,
) -> list[dict[str, Any]]:
    """LoRA manifest rows from *rows* not yet listed on ComfyUI."""
    try:
        installed = _installed_set(list_loras(base_url))
    except (OSError, ComfyUIRequestError):
        installed = frozenset()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = _lora_manifest_row(item)
        if row is None:
            continue
        if not (row.get("download_url") or row.get("version_id")):
            continue
        key = _norm_asset_key(row["filename"])
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in installed:
            out.append(row)
    return out


def merge_extra_loras_into_missing(
    missing: dict[str, list[dict[str, Any]]],
    extra_loras: list[dict[str, Any]] | None,
    *,
    base_url: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Append downloadable extra LoRAs to *missing* without duplicating filenames."""
    merged = {key: list(missing.get(key) or []) for key in _DIFFUSION_ASSET_BUCKETS}
    seen = {
        _norm_asset_key(str(entry.get("filename") or ""))
        for entry in merged["loras"]
        if _norm_asset_key(str(entry.get("filename") or ""))
    }
    for row in missing_loras_from_rows(list(extra_loras or []), base_url):
        key = _norm_asset_key(str(row.get("filename") or ""))
        if key and key not in seen:
            merged["loras"].append(row)
            seen.add(key)
    return merged


def missing_diffusion_model_assets(
    model_id: str,
    base_url: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Catalog assets for *model_id* not yet listed on ComfyUI."""
    required = required_diffusion_model_assets(model_id)
    installed = _installed_diffusion_assets(base_url)
    if installed is None:
        return required
    return {
        "diffusion_models": _missing_from_manifest(
            required["diffusion_models"], installed["diffusion_models"]
        ),
        "text_encoders": _missing_from_manifest(
            required["text_encoders"], installed["text_encoders"]
        ),
        "vae": _missing_from_manifest(required["vae"], installed["vae"]),
        "loras": _missing_from_manifest(required["loras"], installed["loras"]),
    }


def diffusion_model_assets_ready(model_id: str, base_url: str | None) -> bool:
    missing = missing_diffusion_model_assets(model_id, base_url)
    return not any(missing.get(key) for key in _DIFFUSION_ASSET_BUCKETS)


def resolve_installed_model_path(
    catalog_filename: str,
    installed_names: list[str] | frozenset[str],
) -> str | None:
    """Return the ComfyUI-listed path for *catalog_filename*, if installed."""
    key = _norm_asset_key(catalog_filename)
    if not key:
        return None
    if isinstance(installed_names, frozenset):
        # Re-query live names when only normalized keys are available.
        return None
    for name in installed_names:
        if _norm_asset_key(name) == key:
            return str(name)
    return None


def resolve_diffusion_model_paths(
    model_id: str,
    base_url: str | None,
) -> dict[str, str]:
    """Map catalog asset roles to ComfyUI path strings for workflow patching."""
    spec = diffusion_model_spec(model_id)
    if spec is None:
        return {}
    installed = _installed_diffusion_assets(base_url)
    if installed is None:
        return {}
    paths: dict[str, str] = {}
    for asset in spec.assets:
        folder = str(asset.folder or "").strip()
        filename = str(asset.filename or "").strip()
        if not folder or not filename:
            continue
        bucket = installed.get(folder)
        if bucket is None:
            continue
        # Find live path from API list (preserves Windows backslashes).
        live_names = {
            "diffusion_models": list_diffusion_models,
            "text_encoders": list_text_encoders,
            "vae": list_vae_models,
            "loras": list_loras,
        }.get(folder)
        if live_names is None:
            continue
        resolved = resolve_installed_model_path(filename, live_names(base_url))
        if resolved:
            paths[filename] = resolved
    return paths
