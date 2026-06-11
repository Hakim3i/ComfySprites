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
    keys: set[str] = set()
    for name in names:
        norm = _norm_asset_key(name)
        if not norm:
            continue
        keys.add(norm)
        if "/" in norm:
            keys.add(norm.rsplit("/", 1)[-1])
    return frozenset(keys)


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


def _installed_bucket(
    list_fn,
    base_url: str | None,
    *,
    required: bool,
) -> frozenset[str] | None:
    """Fetch one model folder; optional buckets treat 404 as empty."""
    try:
        return _installed_set(list_fn(base_url))
    except ComfyUIRequestError as exc:
        if not required and exc.status_code == 404:
            return frozenset()
        return None
    except OSError:
        return None


def installed_assets(base_url: str | None) -> dict[str, frozenset[str]] | None:
    """Installed checkpoint / LoRA / ControlNet filenames on ComfyUI (``None`` if unreachable)."""
    checkpoints = _installed_bucket(list_checkpoints, base_url, required=True)
    loras = _installed_bucket(list_loras, base_url, required=True)
    if checkpoints is None or loras is None:
        return None
    return {
        "checkpoints": checkpoints,
        "loras": loras,
        "controlnets": _installed_bucket(list_controlnets, base_url, required=False)
        or frozenset(),
        "upscalers": _installed_bucket(list_upscale_models, base_url, required=False)
        or frozenset(),
        "ultralytics": _installed_bucket(list_ultralytics_models, base_url, required=False)
        or frozenset(),
        "sams": _installed_bucket(list_sams_models, base_url, required=False) or frozenset(),
    }


def _diffusion_model_manifest_row(entry: dict[str, Any]) -> dict[str, Any] | None:
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


def _apply_qwen_style_unet_manifest(
    target: dict[str, list[dict[str, Any]]],
    build: dict[str, Any],
    *,
    model_id: str = "qwen_image_2512",
) -> None:
    """Replace catalog default UNET with the style-linked diffusion model row."""
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    checkpoint = sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
    style_row = _diffusion_model_manifest_row(checkpoint)
    if style_row is None:
        return
    spec = diffusion_model_spec(model_id)
    catalog_unet_keys: set[str] = set()
    if spec is not None:
        for asset in spec.assets:
            if str(asset.folder or "").strip() == "diffusion_models":
                key = _norm_asset_key(str(asset.filename or ""))
                if key:
                    catalog_unet_keys.add(key)
    rows = target.setdefault("diffusion_models", [])
    target["diffusion_models"] = [
        row
        for row in rows
        if _norm_asset_key(str(row.get("filename") or "")) not in catalog_unet_keys
    ]
    seen = {
        _norm_asset_key(str(row.get("filename") or ""))
        for row in target["diffusion_models"]
        if _norm_asset_key(str(row.get("filename") or ""))
    }
    key = _norm_asset_key(style_row["filename"])
    if key and key not in seen:
        target["diffusion_models"].append(style_row)


def _merge_diffusion_catalog_assets(
    target: dict[str, list[dict[str, Any]]],
    model_id: str,
) -> None:
    buckets = required_diffusion_model_assets(model_id)
    for key in ("diffusion_models", "text_encoders", "vae", "loras"):
        rows = buckets.get(key) or []
        if not rows:
            continue
        existing = target.setdefault(key, [])
        seen = {
            _norm_asset_key(str(entry.get("filename") or ""))
            for entry in existing
            if _norm_asset_key(str(entry.get("filename") or ""))
        }
        for entry in rows:
            fn = _norm_asset_key(str(entry.get("filename") or ""))
            if fn and fn not in seen:
                existing.append(entry)
                seen.add(fn)


def required_assets(build: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Manifest rows for all assets referenced by a Make build."""
    out: dict[str, list[dict[str, Any]]] = {
        "checkpoints": make_lab_checkpoints_manifest(build),
        "loras": make_lab_loras_manifest(build),
        "controlnets": make_lab_controlnets_manifest(build),
        "upscalers": make_lab_upscalers_manifest(build),
        "detailers": make_lab_detailer_assets_manifest(build),
        "diffusion_models": [],
        "text_encoders": [],
        "vae": [],
    }
    if isinstance(build.get("qwen_make"), dict):
        _merge_diffusion_catalog_assets(out, "qwen_image_2512")
        _apply_qwen_style_unet_manifest(out, build)
    return out


def missing_assets(
    build: dict[str, Any],
    base_url: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Manifest rows not yet present on the ComfyUI host."""
    installed = installed_assets(base_url)
    required = required_assets(build)
    if installed is None:
        return required
    diffusion_installed = _installed_diffusion_assets(base_url)
    out = {
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
        "diffusion_models": [],
        "text_encoders": [],
        "vae": [],
    }
    if diffusion_installed is not None:
        out["diffusion_models"] = _missing_from_manifest(
            required.get("diffusion_models") or [],
            diffusion_installed["diffusion_models"],
        )
        out["text_encoders"] = _missing_from_manifest(
            required.get("text_encoders") or [],
            diffusion_installed["text_encoders"],
        )
        out["vae"] = _missing_from_manifest(
            required.get("vae") or [],
            diffusion_installed["vae"],
        )
        extra_loras = _missing_from_manifest(
            required.get("loras") or [],
            diffusion_installed["loras"],
        )
        seen = {
            _norm_asset_key(str(entry.get("filename") or ""))
            for entry in out["loras"]
        }
        for entry in extra_loras:
            fn = _norm_asset_key(str(entry.get("filename") or ""))
            if fn and fn not in seen:
                out["loras"].append(entry)
                seen.add(fn)
    return out


def assets_ready(build: dict[str, Any], base_url: str | None) -> bool:
    """True when every required asset filename is listed on ComfyUI."""
    missing = missing_assets(build, base_url)
    if isinstance(build.get("qwen_make"), dict) and not diffusion_model_assets_ready(
        "qwen_image_2512", base_url, build=build
    ):
        return False
    return not any(
        missing[k]
        for k in (
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


def _live_diffusion_asset_lists(
    base_url: str | None,
) -> dict[str, list[str]] | None:
    """List each diffusion-model folder once (preserves ComfyUI path strings)."""
    try:
        return {
            "diffusion_models": list_diffusion_models(base_url),
            "text_encoders": list_text_encoders(base_url),
            "vae": list_vae_models(base_url),
            "loras": list_loras(base_url),
        }
    except (OSError, ComfyUIRequestError):
        return None


def _installed_diffusion_assets(base_url: str | None) -> dict[str, frozenset[str]] | None:
    live = _live_diffusion_asset_lists(base_url)
    if live is None:
        return None
    return {key: _installed_set(names) for key, names in live.items()}


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


def merge_extra_diffusion_models_into_missing(
    missing: dict[str, list[dict[str, Any]]],
    extra_rows: list[dict[str, Any]] | None,
    *,
    base_url: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Append style-linked UNET rows to missing diffusion_models."""
    merged = {key: list(missing.get(key) or []) for key in _DIFFUSION_ASSET_BUCKETS}
    installed = _installed_diffusion_assets(base_url)
    installed_dm = (
        installed.get("diffusion_models") if installed is not None else None
    )
    seen = {
        _norm_asset_key(str(entry.get("filename") or ""))
        for entry in merged["diffusion_models"]
        if _norm_asset_key(str(entry.get("filename") or ""))
    }
    for raw in list(extra_rows or []):
        row = _diffusion_model_manifest_row(raw if isinstance(raw, dict) else {})
        if row is None:
            continue
        key = _norm_asset_key(str(row.get("filename") or ""))
        if not key or key in seen:
            continue
        if installed_dm is not None and _missing_from_manifest([row], installed_dm):
            merged["diffusion_models"].append(row)
            seen.add(key)
        elif installed_dm is None and (
            row.get("download_url") or row.get("download_fallback_url")
        ):
            merged["diffusion_models"].append(row)
            seen.add(key)
    return merged


def missing_diffusion_model_assets(
    model_id: str,
    base_url: str | None,
    *,
    build: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Catalog assets for *model_id* not yet listed on ComfyUI."""
    if build is not None and isinstance(build.get("qwen_make"), dict):
        required = required_assets(build)
        buckets = {
            key: list(required.get(key) or [])
            for key in _DIFFUSION_ASSET_BUCKETS
        }
    else:
        buckets = required_diffusion_model_assets(model_id)
    installed = _installed_diffusion_assets(base_url)
    if installed is None:
        return buckets
    return {
        "diffusion_models": _missing_from_manifest(
            buckets["diffusion_models"], installed["diffusion_models"]
        ),
        "text_encoders": _missing_from_manifest(
            buckets["text_encoders"], installed["text_encoders"]
        ),
        "vae": _missing_from_manifest(buckets["vae"], installed["vae"]),
        "loras": _missing_from_manifest(buckets["loras"], installed["loras"]),
    }


def diffusion_model_assets_ready(
    model_id: str,
    base_url: str | None,
    *,
    build: dict[str, Any] | None = None,
) -> bool:
    missing = missing_diffusion_model_assets(model_id, base_url, build=build)
    return not any(missing.get(key) for key in _DIFFUSION_ASSET_BUCKETS)


def resolve_installed_model_path(
    catalog_filename: str,
    installed_names: list[str],
) -> str | None:
    """Return the ComfyUI-listed path for *catalog_filename*, if installed."""
    key = _norm_asset_key(catalog_filename)
    if not key:
        return None
    catalog_base = key.rsplit("/", 1)[-1]
    for name in installed_names:
        norm = _norm_asset_key(name)
        if norm == key or norm.rsplit("/", 1)[-1] == catalog_base:
            return str(name)
    return None


def resolve_diffusion_model_paths(
    model_id: str,
    base_url: str | None,
    *,
    extra_filenames: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map catalog asset roles to ComfyUI path strings for workflow patching."""
    spec = diffusion_model_spec(model_id)
    if spec is None:
        return {}
    live = _live_diffusion_asset_lists(base_url)
    if live is None:
        return {}
    paths: dict[str, str] = {}
    for asset in spec.assets:
        folder = str(asset.folder or "").strip()
        filename = str(asset.filename or "").strip()
        if not folder or not filename:
            continue
        if folder == "diffusion_models" and extra_filenames:
            override = str(extra_filenames.get("unet") or "").strip()
            if override:
                filename = override
        names = live.get(folder)
        if not names:
            continue
        resolved = resolve_installed_model_path(filename, names)
        if resolved:
            paths[filename] = resolved
    if extra_filenames:
        override = str(extra_filenames.get("unet") or "").strip()
        if override and override not in paths:
            names = live.get("diffusion_models") or []
            resolved = resolve_installed_model_path(override, names)
            if resolved:
                paths[override] = resolved
    return paths
