"""Detailer detector / SAM asset catalog from dataset/detailer_assets.json."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT
from .dataset_json import require_json_object

_SHIPPED_PATH = PROJECT_ROOT / "dataset" / "detailer_assets.json"
_DATASET_PATH = DATASET_DIR / "detailer_assets.json"


@dataclass(frozen=True)
class DetailerAssetSpec:
    key: str
    label: str
    folder: str
    relative_path: str
    download_url: str | None
    download_fallback_url: str | None


def ensure_detailer_assets_file() -> None:
    if _DATASET_PATH.is_file():
        return
    _DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_PATH.is_file():
        shutil.copy2(_SHIPPED_PATH, _DATASET_PATH)


def _raw_catalog() -> dict[str, Any]:
    ensure_detailer_assets_file()
    data = require_json_object("Detailer assets", _DATASET_PATH, _SHIPPED_PATH)
    assets = data.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise ValueError("detailer_assets.json: expected non-empty 'assets' object")
    return assets


def detailer_asset_spec(key: str) -> DetailerAssetSpec | None:
    raw = _raw_catalog().get(key)
    if not isinstance(raw, dict):
        return None
    relative_path = str(raw.get("relative_path") or key).strip()
    folder = str(raw.get("folder") or "").strip().lower()
    if not relative_path or folder not in {"ultralytics", "sams"}:
        return None
    return DetailerAssetSpec(
        key=key,
        label=str(raw.get("label") or relative_path).strip(),
        folder=folder,
        relative_path=relative_path,
        download_url=str(raw.get("download_url") or "").strip() or None,
        download_fallback_url=str(raw.get("download_fallback_url") or "").strip()
        or None,
    )


def detailer_asset_spec_for_path(model_path: str) -> DetailerAssetSpec | None:
    path = (model_path or "").strip()
    if not path:
        return None
    spec = detailer_asset_spec(path)
    if spec is not None:
        return spec
    key = path.replace("\\", "/")
    for candidate in _raw_catalog():
        if candidate.replace("\\", "/").lower() == key.lower():
            return detailer_asset_spec(candidate)
    return None


def detailer_ensure_entry(model_path: str) -> dict[str, str] | None:
    spec = detailer_asset_spec_for_path(model_path)
    if spec is None:
        return None
    return {
        "filename": spec.relative_path,
        "relative_path": spec.relative_path,
        "folder": spec.folder,
        "name": spec.label,
        "download_url": spec.download_url or "",
        "download_fallback_url": spec.download_fallback_url or "",
    }
