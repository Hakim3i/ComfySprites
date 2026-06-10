"""Canonical camera views — exported from Coomfy dataset plus ComfySprites ``side_view``."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from .models import (
    VIEW_KIND_ANGLE,
    VIEW_KIND_FOCUS,
    VIEW_KIND_POV,
    VIEW_KIND_SHOT,
    View,
)

DEFAULTS_PATH = DATASET_DIR / "views_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "views_defaults.json"

SIDE_VIEW_KEY = "side_view"

CANONICAL_VIEW_KEYS_BY_KIND: dict[str, tuple[str, ...]] = {
    VIEW_KIND_SHOT: ("close-up", "cowboy shot", "pantyshot"),
    VIEW_KIND_ANGLE: (SIDE_VIEW_KEY, "from above", "from outside"),
    VIEW_KIND_POV: ("pov", "pov doorway", "futanari pov"),
    VIEW_KIND_FOCUS: ("breast focus", "pussy focus", "solo focus"),
}


@dataclass(frozen=True)
class ViewDefault:
    key: str
    kind: str
    label: str
    position: int
    comment: str | None
    framing_clause: str | None


def ensure_views_defaults_file() -> None:
    """Copy shipped ``views_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_views_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("views"), list):
        raise ValueError("views_defaults.json: expected object with non-empty 'views' list")
    return data


def _read_framing_clause(raw: dict[str, Any]) -> str | None:
    text = raw.get("framing_clause") or raw.get("ltx_framing")
    if not text:
        return None
    return str(text).strip() or None


def load_view_defaults() -> tuple[ViewDefault, ...]:
    out: list[ViewDefault] = []
    for raw in _load_raw()["views"]:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        kind = str(raw.get("kind") or "").strip()
        label = str(raw.get("label") or key).strip()
        if not key or not kind:
            continue
        out.append(
            ViewDefault(
                key=key,
                kind=kind,
                label=label,
                position=int(raw.get("position") or 0),
                comment=(str(raw["comment"]).strip() or None) if raw.get("comment") else None,
                framing_clause=_read_framing_clause(raw),
            )
        )
    if not out:
        raise ValueError("views_defaults.json: no valid view rows")
    return tuple(out)


def ensure_default_views(session) -> None:
    """Insert or refresh shipped canonical view rows (never deletes user-added views)."""
    existing = {v.key: v for v in session.scalars(select(View))}
    for spec in load_view_defaults():
        row = existing.get(spec.key)
        if row is None:
            session.add(
                View(
                    key=spec.key,
                    kind=spec.kind,
                    label=spec.label,
                    position=spec.position,
                    comment=spec.comment,
                    framing_clause=spec.framing_clause,
                )
            )
            continue
        row.kind = spec.kind
        row.label = spec.label
        row.position = spec.position
        row.comment = spec.comment
        row.framing_clause = spec.framing_clause


def view_tuples() -> tuple[tuple[str, str, str], ...]:
    """(key, kind, label) tuples for legacy test helpers."""
    return tuple((v.key, v.kind, v.label) for v in load_view_defaults())


__all__ = [
    "CANONICAL_VIEW_KEYS_BY_KIND",
    "SIDE_VIEW_KEY",
    "ViewDefault",
    "ensure_default_views",
    "ensure_views_defaults_file",
    "load_view_defaults",
    "view_tuples",
]
