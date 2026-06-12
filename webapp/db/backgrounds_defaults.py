"""Canonical shipped backgrounds (locations) — upserted on startup."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from .models import ENTITY_BACKGROUND, DesignEntity

DEFAULTS_PATH = DATASET_DIR / "backgrounds_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "backgrounds_defaults.json"


@dataclass(frozen=True)
class BackgroundDefault:
    slug: str
    display_name: str
    comment: str | None
    tags: tuple[str, ...]


def ensure_backgrounds_defaults_file() -> None:
    """Copy shipped ``backgrounds_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_backgrounds_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("backgrounds"), list):
        raise ValueError(
            "backgrounds_defaults.json: expected object with non-empty 'backgrounds' list"
        )
    return data


def _lines(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    val = raw.get(key)
    if not isinstance(val, list):
        return ()
    return tuple(str(v).strip() for v in val if str(v).strip())


def load_background_defaults() -> tuple[BackgroundDefault, ...]:
    out: list[BackgroundDefault] = []
    for raw in _load_raw()["backgrounds"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or raw.get("key") or "").strip()
        if not slug:
            continue
        out.append(
            BackgroundDefault(
                slug=slug,
                display_name=str(raw.get("display_name") or slug).strip(),
                comment=str(raw["comment"]).strip() if raw.get("comment") else None,
                tags=_lines(raw, "tags"),
            )
        )
    if not out:
        raise ValueError("backgrounds_defaults.json: no valid background rows")
    return tuple(out)


def _apply_background_fields(row: DesignEntity, spec: BackgroundDefault) -> None:
    row.display_name = spec.display_name
    row.comment = spec.comment
    row.scene_tags = list(spec.tags)


def ensure_default_backgrounds(session) -> None:
    """Insert shipped background rows that are not already in the database."""
    existing = {
        row.slug: row
        for row in session.scalars(
            select(DesignEntity).where(DesignEntity.entity_type == ENTITY_BACKGROUND)
        )
    }
    for spec in load_background_defaults():
        row = existing.get(spec.slug)
        if row is None:
            session.add(
                DesignEntity(
                    slug=spec.slug,
                    display_name=spec.display_name,
                    entity_type=ENTITY_BACKGROUND,
                    scene_tags=list(spec.tags),
                    comment=spec.comment,
                )
            )
            session.flush()
            row = session.scalar(
                select(DesignEntity).where(
                    DesignEntity.entity_type == ENTITY_BACKGROUND,
                    DesignEntity.slug == spec.slug,
                )
            )
            if row is not None:
                _apply_background_fields(row, spec)


__all__ = [
    "BackgroundDefault",
    "ensure_backgrounds_defaults_file",
    "ensure_default_backgrounds",
    "load_background_defaults",
]
