"""Canonical shipped characters — upserted on startup."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from .models import (
    ENTITY_CHARACTER,
    LORA_KIND_CHARACTER,
    ROLE_MAIN,
    DesignEntity,
    Lora,
)

DEFAULTS_PATH = DATASET_DIR / "characters_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "characters_defaults.json"

_PHYSICAL_STRING_FIELDS = (
    "hair_color",
    "hair_length",
    "hair_style",
    "eye_color",
    "eye_shape",
    "glasses",
    "makeup",
    "age_band",
    "ethnicity",
    "skin_tone",
    "height",
    "breast_size",
    "body_type",
    "muscle",
    "hip_size",
    "butt_size",
    "thigh_type",
)
_PHYSICAL_LIST_FIELDS = ("facial_marks", "piercings", "tattoos")
_OUTFIT_FIELDS = ("outfit_head", "outfit_upper", "outfit_lower", "outfit_extra")


@dataclass(frozen=True)
class CharacterLoraDefault:
    name: str
    filename: str
    url: str | None
    download_url: str | None
    download_fallback_url: str | None
    model_id: int | None
    version_id: int | None
    trigger: str | None
    strength: float


@dataclass(frozen=True)
class CharacterDefault:
    slug: str
    display_name: str
    comment: str | None
    name_tag: str
    identity_core: tuple[str, ...]
    outfit_head: tuple[str, ...]
    outfit_upper: tuple[str, ...]
    outfit_lower: tuple[str, ...]
    outfit_extra: tuple[str, ...]
    physical: dict[str, str | tuple[str, ...] | None]
    lora: CharacterLoraDefault | None


def ensure_characters_defaults_file() -> None:
    """Copy shipped ``characters_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_characters_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("characters"), list):
        raise ValueError(
            "characters_defaults.json: expected object with non-empty 'characters' list"
        )
    return data


def _lines(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    val = raw.get(key)
    if not isinstance(val, list):
        return ()
    return tuple(str(v).strip() for v in val if str(v).strip())


def _parse_lora(raw: dict[str, Any] | None) -> CharacterLoraDefault | None:
    if not isinstance(raw, dict):
        return None
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return None
    trigger = str(raw.get("trigger") or "").strip() or None
    fallback = str(raw.get("download_fallback_url") or "").strip() or None
    return CharacterLoraDefault(
        name=str(raw.get("name") or filename).strip(),
        filename=filename,
        url=str(raw.get("url") or "").strip() or None,
        download_url=str(raw.get("download_url") or "").strip() or None,
        download_fallback_url=fallback,
        model_id=int(raw["model_id"]) if raw.get("model_id") is not None else None,
        version_id=int(raw["version_id"])
        if raw.get("version_id") is not None
        else None,
        trigger=trigger,
        strength=float(raw.get("strength") if raw.get("strength") is not None else 1.0),
    )


def _parse_physical(raw: dict[str, Any]) -> dict[str, str | tuple[str, ...] | None]:
    out: dict[str, str | tuple[str, ...] | None] = {}
    for key in _PHYSICAL_STRING_FIELDS:
        val = raw.get(key)
        if val is None:
            out[key] = None
            continue
        text = str(val).strip()
        out[key] = text or None
    for key in _PHYSICAL_LIST_FIELDS:
        out[key] = _lines(raw, key) or None
    return out


def load_character_defaults() -> tuple[CharacterDefault, ...]:
    out: list[CharacterDefault] = []
    for raw in _load_raw()["characters"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        if not slug:
            continue
        name_tag = str(raw.get("name_tag") or slug).strip()
        out.append(
            CharacterDefault(
                slug=slug,
                display_name=str(raw.get("display_name") or slug).strip(),
                comment=str(raw["comment"]).strip() if raw.get("comment") else None,
                name_tag=name_tag,
                identity_core=_lines(raw, "identity_core"),
                outfit_head=_lines(raw, "outfit_head"),
                outfit_upper=_lines(raw, "outfit_upper"),
                outfit_lower=_lines(raw, "outfit_lower"),
                outfit_extra=_lines(raw, "outfit_extra"),
                physical=_parse_physical(raw),
                lora=_parse_lora(raw.get("lora")),
            )
        )
    if not out:
        raise ValueError("characters_defaults.json: no valid character rows")
    return tuple(out)


def _upsert_lora(session, spec: CharacterLoraDefault) -> Lora:
    row = session.scalar(select(Lora).where(Lora.filename == spec.filename))
    if row is None:
        row = Lora(
            kind=LORA_KIND_CHARACTER,
            filename=spec.filename,
            name=spec.name,
            strength=spec.strength,
        )
        session.add(row)
        session.flush()
    row.kind = LORA_KIND_CHARACTER
    row.name = spec.name
    row.filename = spec.filename
    row.url = spec.url
    row.download_url = spec.download_url
    row.download_fallback_url = spec.download_fallback_url
    row.model_id = spec.model_id
    row.version_id = spec.version_id
    row.trigger = spec.trigger
    row.strength = spec.strength
    return row


def _apply_character_fields(
    row: DesignEntity,
    spec: CharacterDefault,
    *,
    lora_id: int | None,
) -> None:
    row.display_name = spec.display_name
    row.comment = spec.comment
    row.name_tag = spec.name_tag
    row.identity_core = list(spec.identity_core)
    row.outfit_head = list(spec.outfit_head)
    row.outfit_upper = list(spec.outfit_upper)
    row.outfit_lower = list(spec.outfit_lower)
    row.outfit_extra = list(spec.outfit_extra)
    row.lora_id = lora_id
    for key in _PHYSICAL_STRING_FIELDS:
        val = spec.physical.get(key)
        setattr(row, key, val if isinstance(val, str) else None)
    for key in _PHYSICAL_LIST_FIELDS:
        val = spec.physical.get(key)
        setattr(row, key, list(val) if isinstance(val, tuple) else [])


def ensure_default_characters(session) -> None:
    """Insert shipped character rows that are not already in the database."""
    existing = {
        row.slug: row
        for row in session.scalars(
            select(DesignEntity).where(
                DesignEntity.entity_type == ENTITY_CHARACTER,
                DesignEntity.role == ROLE_MAIN,
            )
        )
    }
    for spec in load_character_defaults():
        lora_id = (
            _upsert_lora(session, spec.lora).id if spec.lora is not None else None
        )
        row = existing.get(spec.slug)
        if row is None:
            session.add(
                DesignEntity(
                    slug=spec.slug,
                    display_name=spec.display_name,
                    entity_type=ENTITY_CHARACTER,
                    role=ROLE_MAIN,
                    name_tag=spec.name_tag,
                    identity_core=list(spec.identity_core),
                    comment=spec.comment,
                    lora_id=lora_id,
                )
            )
            session.flush()
            row = session.scalar(
                select(DesignEntity).where(
                    DesignEntity.entity_type == ENTITY_CHARACTER,
                    DesignEntity.slug == spec.slug,
                )
            )
            if row is not None:
                _apply_character_fields(row, spec, lora_id=lora_id)


__all__ = [
    "CharacterDefault",
    "CharacterLoraDefault",
    "ensure_characters_defaults_file",
    "ensure_default_characters",
    "load_character_defaults",
]
