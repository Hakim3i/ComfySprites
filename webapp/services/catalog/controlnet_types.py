"""ControlNet type catalog from dataset/controlnet_types.json."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT
from .dataset_json import require_json_object

_SHIPPED_PATH = PROJECT_ROOT / "dataset" / "controlnet_types.json"
_DATASET_PATH = DATASET_DIR / "controlnet_types.json"


@dataclass(frozen=True)
class ControlNetPreprocessorSpec:
    class_type: str
    inputs: dict[str, Any]


@dataclass(frozen=True)
class ControlNetTypeSpec:
    key: str
    label: str
    control_net: str
    download_url: str | None
    download_fallback_url: str | None
    default_strength: float
    default_start: float
    default_end: float
    preprocessor: ControlNetPreprocessorSpec | None = None


def ensure_controlnet_types_file() -> None:
    if _DATASET_PATH.is_file():
        return
    _DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_PATH.is_file():
        shutil.copy2(_SHIPPED_PATH, _DATASET_PATH)


def _raw_catalog() -> dict[str, Any]:
    ensure_controlnet_types_file()
    data = require_json_object("ControlNet types", _DATASET_PATH, _SHIPPED_PATH)
    types = data.get("types")
    if not isinstance(types, dict) or not types:
        raise ValueError("controlnet_types.json: expected non-empty 'types' object")
    return types


def controlnet_type_keys() -> tuple[str, ...]:
    return tuple(_raw_catalog().keys())


def _parse_preprocessor(raw: Any) -> ControlNetPreprocessorSpec | None:
    if not isinstance(raw, dict):
        return None
    class_type = str(raw.get("class_type") or "").strip()
    if not class_type:
        return None
    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    return ControlNetPreprocessorSpec(
        class_type=class_type,
        inputs={str(k): v for k, v in inputs.items()},
    )


def controlnet_type_spec(key: str) -> ControlNetTypeSpec | None:
    raw = _raw_catalog().get(key)
    if not isinstance(raw, dict):
        return None
    control_net = str(raw.get("control_net") or "").strip()
    if not control_net:
        return None
    return ControlNetTypeSpec(
        key=key,
        label=str(raw.get("label") or key).strip(),
        control_net=control_net,
        download_url=str(raw.get("download_url") or "").strip() or None,
        download_fallback_url=str(raw.get("download_fallback_url") or "").strip()
        or None,
        default_strength=float(raw.get("default_strength", 0.9)),
        default_start=float(raw.get("default_start", 0.0)),
        default_end=float(raw.get("default_end", 1.0)),
        preprocessor=_parse_preprocessor(raw.get("preprocessor")),
    )


def all_controlnet_type_specs() -> list[ControlNetTypeSpec]:
    out: list[ControlNetTypeSpec] = []
    for key in controlnet_type_keys():
        spec = controlnet_type_spec(key)
        if spec is not None:
            out.append(spec)
    return out


def controlnet_defaults_for_type(key: str) -> dict[str, float]:
    spec = controlnet_type_spec(key)
    if spec is None:
        return {"strength": 0.9, "start_percent": 0.0, "end_percent": 1.0}
    return {
        "strength": spec.default_strength,
        "start_percent": spec.default_start,
        "end_percent": spec.default_end,
    }


def normalize_controlnets_map(raw: dict | None) -> dict[str, dict[str, Any]]:
    """Keep only known types with image_path."""
    if not isinstance(raw, dict):
        return {}
    allowed = set(controlnet_type_keys())
    out: dict[str, dict[str, Any]] = {}
    for key, entry in raw.items():
        if key not in allowed or not isinstance(entry, dict):
            continue
        image_path = str(entry.get("image_path") or "").strip()
        if not image_path:
            continue
        defaults = controlnet_defaults_for_type(key)
        strength = entry.get("strength")
        start = entry.get("start_percent")
        end = entry.get("end_percent")
        out[key] = {
            "image_path": image_path,
            "strength": float(
                strength if strength is not None else defaults["strength"]
            ),
            "start_percent": float(
                start if start is not None else defaults["start_percent"]
            ),
            "end_percent": float(end if end is not None else defaults["end_percent"]),
        }
    return out


def controlnet_ensure_entry(key: str) -> dict[str, str] | None:
    spec = controlnet_type_spec(key)
    if spec is None:
        return None
    return {
        "filename": spec.control_net,
        "download_url": spec.download_url or "",
        "download_fallback_url": spec.download_fallback_url or "",
    }
