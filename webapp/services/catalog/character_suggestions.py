"""Physical-field tag suggestion banks loaded from dataset/character_suggestions.json."""

from __future__ import annotations

import json
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT

SUGGESTIONS_PATH = DATASET_DIR / "character_suggestions.json"
_SHIPPED_SUGGESTIONS_PATH = PROJECT_ROOT / "dataset" / "character_suggestions.json"

_FIELD_KEYS = (
    "hair_color",
    "hair_length",
    "hair_style",
    "eye_color",
    "eye_shape",
    "facial_marks",
    "glasses",
    "makeup",
    "age_band",
    "ethnicity",
    "skin_tone",
    "height",
    "breast_size",
    "body_type",
    "muscle",
    "piercings",
    "tattoos",
    "hip_size",
    "butt_size",
    "thigh_type",
)


def _normalize(raw: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {key: [] for key in _FIELD_KEYS}
    for key in _FIELD_KEYS:
        rows = raw.get(key) or []
        if isinstance(rows, list):
            out[key] = [str(t).strip() for t in rows if str(t).strip()]
    return out


def _read_suggestions_file(path) -> dict[str, list[str]] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    block = data.get("suggestions") if isinstance(data, dict) else data
    if not isinstance(block, dict):
        return None
    return _normalize(block)


def load_suggestions() -> dict[str, list[str]]:
    loaded = _read_suggestions_file(SUGGESTIONS_PATH)
    if loaded is not None:
        return loaded
    shipped = _read_suggestions_file(_SHIPPED_SUGGESTIONS_PATH)
    if shipped is not None:
        return shipped
    return {key: [] for key in _FIELD_KEYS}


def save_suggestions(suggestions: dict[str, list[str]]) -> None:
    SUGGESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"suggestions": _normalize(suggestions)}
    SUGGESTIONS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ensure_suggestions_file() -> dict[str, list[str]]:
    if SUGGESTIONS_PATH.is_file():
        return load_suggestions()
    if (
        _SHIPPED_SUGGESTIONS_PATH.is_file()
        and _SHIPPED_SUGGESTIONS_PATH != SUGGESTIONS_PATH
    ):
        try:
            data = json.loads(_SHIPPED_SUGGESTIONS_PATH.read_text(encoding="utf-8"))
            block = data.get("suggestions") if isinstance(data, dict) else None
            if isinstance(block, dict) and block:
                normalized = _normalize(block)
                save_suggestions(normalized)
                return normalized
        except (json.JSONDecodeError, OSError):
            pass
    return {key: [] for key in _FIELD_KEYS}


def field_keys() -> tuple[str, ...]:
    return _FIELD_KEYS


def parse_suggestions_form(form) -> dict[str, list[str]]:
    return {
        key: [
            line.strip()
            for line in (form.get(f"sugg_{key}") or "").splitlines()
            if line.strip()
        ]
        for key in _FIELD_KEYS
    }


def suggestion_tags(field_key: str) -> tuple[str, ...]:
    return tuple(load_suggestions().get(field_key, []))
