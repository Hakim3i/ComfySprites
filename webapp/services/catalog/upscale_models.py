"""Upscale model catalog from dataset/upscale_models.json."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT
from .dataset_json import require_json_object

_SHIPPED_PATH = PROJECT_ROOT / "dataset" / "upscale_models.json"
_DATASET_PATH = DATASET_DIR / "upscale_models.json"


@dataclass(frozen=True)
class UpscaleModelSpec:
    key: str
    label: str
    filename: str
    scale: int
    download_url: str | None
    download_fallback_url: str | None


def ensure_upscale_models_file() -> None:
    if _DATASET_PATH.is_file():
        return
    _DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_PATH.is_file():
        shutil.copy2(_SHIPPED_PATH, _DATASET_PATH)


def _raw_catalog() -> dict[str, Any]:
    ensure_upscale_models_file()
    data = require_json_object("Upscale models", _DATASET_PATH, _SHIPPED_PATH)
    models = data.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("upscale_models.json: expected non-empty 'models' object")
    return models


def upscale_model_keys() -> tuple[str, ...]:
    return tuple(_raw_catalog().keys())


def upscale_model_spec(key: str) -> UpscaleModelSpec | None:
    raw = _raw_catalog().get(key)
    if not isinstance(raw, dict):
        return None
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return None
    try:
        scale = int(raw.get("scale") or 4)
    except (TypeError, ValueError):
        scale = 4
    return UpscaleModelSpec(
        key=key,
        label=str(raw.get("label") or filename).strip(),
        filename=filename,
        scale=max(1, scale),
        download_url=str(raw.get("download_url") or "").strip() or None,
        download_fallback_url=str(raw.get("download_fallback_url") or "").strip()
        or None,
    )


def all_upscale_model_specs() -> list[UpscaleModelSpec]:
    out: list[UpscaleModelSpec] = []
    for key in upscale_model_keys():
        spec = upscale_model_spec(key)
        if spec is not None:
            out.append(spec)
    return out


def upscale_model_spec_for_filename(filename: str) -> UpscaleModelSpec | None:
    name = (filename or "").strip().lower()
    if not name:
        return None
    for spec in all_upscale_model_specs():
        if spec.filename.lower() == name:
            return spec
    return None


def upscale_ensure_entry(filename: str) -> dict[str, str] | None:
    spec = upscale_model_spec_for_filename(filename)
    if spec is None:
        return None
    return {
        "filename": spec.filename,
        "name": spec.label,
        "download_url": spec.download_url or "",
        "download_fallback_url": spec.download_fallback_url or "",
    }
