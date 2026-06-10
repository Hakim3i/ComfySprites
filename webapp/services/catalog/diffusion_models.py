"""Diffusion model catalog for Animate (Wan 2.2 / LTX 2.3) from dataset/diffusion_models.json."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT
from .dataset_json import require_json_object

_SHIPPED_PATH = PROJECT_ROOT / "dataset" / "diffusion_models.json"
_DATASET_PATH = DATASET_DIR / "diffusion_models.json"


@dataclass(frozen=True)
class DiffusionModelAsset:
    folder: str
    filename: str
    download_url: str | None
    download_fallback_url: str | None


@dataclass(frozen=True)
class DiffusionModelSpec:
    id: str
    label: str
    engine: str
    lora_roles: tuple[str, ...]
    is_default: bool
    default_settings: dict[str, Any]
    assets: tuple[DiffusionModelAsset, ...]


def ensure_diffusion_models_file() -> None:
    if _DATASET_PATH.is_file():
        return
    _DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_PATH.is_file():
        shutil.copy2(_SHIPPED_PATH, _DATASET_PATH)


def _raw_catalog() -> dict[str, Any]:
    ensure_diffusion_models_file()
    data = require_json_object("Diffusion models", _DATASET_PATH, _SHIPPED_PATH)
    models = data.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("diffusion_models.json: expected non-empty 'models' object")
    return models


def _parse_assets(raw: Any) -> tuple[DiffusionModelAsset, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[DiffusionModelAsset] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        folder = str(item.get("folder") or "").strip()
        filename = str(item.get("filename") or "").strip()
        if not folder or not filename:
            continue
        out.append(
            DiffusionModelAsset(
                folder=folder,
                filename=filename,
                download_url=str(item.get("download_url") or "").strip() or None,
                download_fallback_url=str(item.get("download_fallback_url") or "").strip()
                or None,
            )
        )
    return tuple(out)


def diffusion_model_spec(model_id: str) -> DiffusionModelSpec | None:
    raw = _raw_catalog().get(model_id)
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get("id") or model_id).strip()
    if not mid:
        return None
    roles = raw.get("lora_roles")
    if not isinstance(roles, list):
        roles = []
    lora_roles = tuple(str(r).strip() for r in roles if str(r).strip())
    defaults = raw.get("default_settings")
    if not isinstance(defaults, dict):
        defaults = {}
    return DiffusionModelSpec(
        id=mid,
        label=str(raw.get("label") or mid).strip(),
        engine=str(raw.get("engine") or "").strip(),
        lora_roles=lora_roles,
        is_default=bool(raw.get("is_default")),
        default_settings=dict(defaults),
        assets=_parse_assets(raw.get("assets")),
    )


def all_diffusion_model_specs() -> list[DiffusionModelSpec]:
    out: list[DiffusionModelSpec] = []
    for key in _raw_catalog().keys():
        spec = diffusion_model_spec(key)
        if spec is not None:
            out.append(spec)
    return out


def default_diffusion_model_id() -> str | None:
    specs = all_diffusion_model_specs()
    for spec in specs:
        if spec.is_default:
            return spec.id
    return specs[0].id if specs else None


def diffusion_model_to_dict(spec: DiffusionModelSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "label": spec.label,
        "engine": spec.engine,
        "lora_roles": list(spec.lora_roles),
        "is_default": spec.is_default,
        "default_settings": dict(spec.default_settings),
        "assets": [
            {
                "folder": a.folder,
                "filename": a.filename,
                "download_url": a.download_url,
                "download_fallback_url": a.download_fallback_url,
            }
            for a in spec.assets
        ],
    }


def diffusion_model_ensure_entries(model_id: str) -> list[dict[str, str]]:
    """Manifest rows for future ComfySpritesDownloader preflight."""
    spec = diffusion_model_spec(model_id)
    if spec is None:
        return []
    out: list[dict[str, str]] = []
    for asset in spec.assets:
        row: dict[str, str] = {
            "folder": asset.folder,
            "filename": asset.filename,
            "name": asset.filename,
        }
        if asset.download_url:
            row["download_url"] = asset.download_url
        if asset.download_fallback_url:
            row["download_fallback_url"] = asset.download_fallback_url
        out.append(row)
    return out
