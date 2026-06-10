"""Canonical shipped animations — upserted on startup (separate from test fixtures)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from ..services.design.animation_fields import (
    normalize_animation_framings,
    normalize_animation_subject_type,
)
from .models import (
    LORA_KIND_ANIMATION,
    LORA_KIND_ANIMATION_LTX,
    LORA_KIND_ANIMATION_WAN_HIGH,
    LORA_KIND_ANIMATION_WAN_LOW,
    Animation,
    Lora,
)

DEFAULTS_PATH = DATASET_DIR / "animations_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "animations_defaults.json"


@dataclass(frozen=True)
class AnimationLoraDefault:
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
class AnimationDefault:
    slug: str
    menu_name: str
    subject_type: str
    comment: str | None
    tags: tuple[str, ...]
    framings: tuple[str, ...]
    orientation: str
    lora: AnimationLoraDefault | None
    ltx_lora: AnimationLoraDefault | None
    wan_high_lora: AnimationLoraDefault | None
    wan_low_lora: AnimationLoraDefault | None


def ensure_animations_defaults_file() -> None:
    """Copy shipped ``animations_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_animations_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("animations"), list):
        raise ValueError(
            "animations_defaults.json: expected object with non-empty 'acts' list"
        )
    return data


def _lines(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    val = raw.get(key)
    if not isinstance(val, list):
        return ()
    return tuple(str(v).strip() for v in val if str(v).strip())


def _parse_lora(raw: dict[str, Any] | None) -> AnimationLoraDefault | None:
    if not isinstance(raw, dict):
        return None
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return None
    trigger = str(raw.get("trigger") or "").strip() or None
    fallback = str(raw.get("download_fallback_url") or "").strip() or None
    return AnimationLoraDefault(
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


def load_animation_defaults() -> tuple[AnimationDefault, ...]:
    out: list[AnimationDefault] = []
    for raw in _load_raw()["animations"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        if not slug:
            continue
        menu_name = str(raw.get("menu_name") or slug).strip()
        orient = str(raw.get("orientation") or "portrait").strip().lower()
        if orient not in ("portrait", "landscape", "both"):
            orient = "portrait"
        out.append(
            AnimationDefault(
                slug=slug,
                menu_name=menu_name,
                subject_type=normalize_animation_subject_type(raw.get("subject_type")),
                comment=str(raw["comment"]).strip() if raw.get("comment") else None,
                tags=_lines(raw, "tags"),
                framings=_lines(raw, "framings"),
                orientation=orient,
                lora=_parse_lora(raw.get("lora")),
                ltx_lora=_parse_lora(raw.get("ltx_lora")),
                wan_high_lora=_parse_lora(raw.get("wan_high_lora")),
                wan_low_lora=_parse_lora(raw.get("wan_low_lora")),
            )
        )
    if not out:
        raise ValueError("animations_defaults.json: no valid animation rows")
    return tuple(out)


def _upsert_lora(session, spec: AnimationLoraDefault, *, kind: str) -> Lora:
    row = session.scalar(select(Lora).where(Lora.filename == spec.filename))
    if row is None:
        row = Lora(
            kind=kind,
            filename=spec.filename,
            name=spec.name,
            strength=spec.strength,
        )
        session.add(row)
        session.flush()
    row.kind = kind
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


def _apply_animation_fields(
    session,
    animation: Animation,
    spec: AnimationDefault,
    *,
    lora_id: int | None,
    ltx_lora_id: int | None,
    wan_high_lora_id: int | None,
    wan_low_lora_id: int | None,
) -> None:
    animation.menu_name = spec.menu_name
    animation.subject_type = spec.subject_type
    animation.comment = spec.comment
    animation.tags = list(spec.tags)
    animation.framings = list(
        normalize_animation_framings(session, list(spec.framings))
    )
    animation.orientation = spec.orientation
    animation.lora_id = lora_id
    animation.ltx_lora_id = ltx_lora_id
    animation.wan_high_lora_id = wan_high_lora_id
    animation.wan_low_lora_id = wan_low_lora_id


def ensure_default_animations(session) -> None:
    """Insert or refresh shipped canonical animation rows (never deletes user-added animations)."""
    existing = {a.slug: a for a in session.scalars(select(Animation))}
    for spec in load_animation_defaults():
        lora_id = (
            _upsert_lora(session, spec.lora, kind=LORA_KIND_ANIMATION).id
            if spec.lora is not None
            else None
        )
        ltx_lora_id = (
            _upsert_lora(session, spec.ltx_lora, kind=LORA_KIND_ANIMATION_LTX).id
            if spec.ltx_lora is not None
            else None
        )
        wan_high_lora_id = (
            _upsert_lora(session, spec.wan_high_lora, kind=LORA_KIND_ANIMATION_WAN_HIGH).id
            if spec.wan_high_lora is not None
            else None
        )
        wan_low_lora_id = (
            _upsert_lora(session, spec.wan_low_lora, kind=LORA_KIND_ANIMATION_WAN_LOW).id
            if spec.wan_low_lora is not None
            else None
        )
        row = existing.get(spec.slug)
        if row is None:
            session.add(
                Animation(
                    slug=spec.slug,
                    menu_name=spec.menu_name,
                    subject_type=spec.subject_type,
                    tags=list(spec.tags),
                    framings=list(spec.framings),
                    orientation=spec.orientation,
                    lora_id=lora_id,
                    ltx_lora_id=ltx_lora_id,
                    wan_high_lora_id=wan_high_lora_id,
                    wan_low_lora_id=wan_low_lora_id,
                )
            )
            session.flush()
            row = session.scalar(select(Animation).where(Animation.slug == spec.slug))
        if row is not None:
            _apply_animation_fields(
                session,
                row,
                spec,
                lora_id=lora_id,
                ltx_lora_id=ltx_lora_id,
                wan_high_lora_id=wan_high_lora_id,
                wan_low_lora_id=wan_low_lora_id,
            )


__all__ = [
    "AnimationDefault",
    "AnimationLoraDefault",
    "ensure_animations_defaults_file",
    "ensure_default_animations",
    "load_animation_defaults",
]
