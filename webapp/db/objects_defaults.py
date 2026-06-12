"""Canonical shipped objects — upserted on startup."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from .models import ENTITY_OBJECT, ROLE_MAIN, DesignEntity

DEFAULTS_PATH = DATASET_DIR / "objects_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "objects_defaults.json"


@dataclass(frozen=True)
class ObjectDefault:
    slug: str
    display_name: str
    name_tag: str
    comment: str | None
    identity_core: tuple[str, ...]


def ensure_objects_defaults_file() -> None:
    """Copy shipped ``objects_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_objects_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("objects"), list):
        raise ValueError(
            "objects_defaults.json: expected object with non-empty 'objects' list"
        )
    return data


def _lines(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    val = raw.get(key)
    if not isinstance(val, list):
        return ()
    return tuple(str(v).strip() for v in val if str(v).strip())


def load_object_defaults() -> tuple[ObjectDefault, ...]:
    out: list[ObjectDefault] = []
    for raw in _load_raw()["objects"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        if not slug:
            continue
        name_tag = str(raw.get("name_tag") or slug).strip()
        out.append(
            ObjectDefault(
                slug=slug,
                display_name=str(raw.get("display_name") or slug).strip(),
                name_tag=name_tag,
                comment=str(raw["comment"]).strip() if raw.get("comment") else None,
                identity_core=_lines(raw, "identity_core"),
            )
        )
    if not out:
        raise ValueError("objects_defaults.json: no valid object rows")
    return tuple(out)


def _apply_object_fields(row: DesignEntity, spec: ObjectDefault) -> None:
    row.display_name = spec.display_name
    row.name_tag = spec.name_tag
    row.comment = spec.comment
    row.identity_core = list(spec.identity_core)


def ensure_default_objects(session) -> None:
    """Insert shipped object rows that are not already in the database."""
    existing = {
        row.slug: row
        for row in session.scalars(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_OBJECT,
                DesignEntity.role == ROLE_MAIN,
            )
        )
    }
    for spec in load_object_defaults():
        row = existing.get(spec.slug)
        if row is None:
            session.add(
                DesignEntity(
                    slug=spec.slug,
                    display_name=spec.display_name,
                    name_tag=spec.name_tag,
                    entity_type=ENTITY_OBJECT,
                    role=ROLE_MAIN,
                    identity_core=list(spec.identity_core),
                    comment=spec.comment,
                )
            )
            session.flush()
            row = session.scalar(
                select(DesignEntity).where(
                    DesignEntity.entity_type == ENTITY_OBJECT,
                    DesignEntity.slug == spec.slug,
                )
            )
            if row is not None:
                _apply_object_fields(row, spec)


__all__ = [
    "ObjectDefault",
    "ensure_default_objects",
    "ensure_objects_defaults_file",
    "load_object_defaults",
]
