"""Canonical shipped styles — upserted on startup (separate from test fixtures)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..config import DATASET_DIR, PROJECT_ROOT
from .models import LORA_KIND_STYLE, Lora, Style

DEFAULTS_PATH = DATASET_DIR / "styles_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "styles_defaults.json"

_CANONICAL_STYLE_SLUGS: tuple[str, ...] = ()


@dataclass(frozen=True)
class StyleLoraDefault:
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
class StyleDefault:
    slug: str
    display_name: str
    filename: str
    base_model: str
    civitai_url: str | None
    model_id: int | None
    version_id: int | None
    download_url: str | None
    sampler: str
    scheduler: str
    steps: int
    cfg_scale: float
    clip_skip: int
    width: int
    height: int
    prefix: str
    negative: str
    image_path: str | None
    comment: str | None
    lora: StyleLoraDefault | None


def ensure_styles_defaults_file() -> None:
    """Copy shipped ``styles_defaults.json`` into the workspace dataset when missing."""
    if DEFAULTS_PATH.is_file():
        return
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SHIPPED_DEFAULTS_PATH.is_file():
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)


def _load_raw() -> dict[str, Any]:
    ensure_styles_defaults_file()
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("styles"), list):
        raise ValueError("styles_defaults.json: expected object with non-empty 'styles' list")
    return data


def _parse_lora(raw: dict[str, Any] | None) -> StyleLoraDefault | None:
    if not isinstance(raw, dict):
        return None
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return None
    trigger = str(raw.get("trigger") or "").strip() or None
    fallback = str(raw.get("download_fallback_url") or "").strip() or None
    return StyleLoraDefault(
        name=str(raw.get("name") or filename).strip(),
        filename=filename,
        url=str(raw.get("url") or "").strip() or None,
        download_url=str(raw.get("download_url") or "").strip() or None,
        download_fallback_url=fallback,
        model_id=int(raw["model_id"]) if raw.get("model_id") is not None else None,
        version_id=int(raw["version_id"]) if raw.get("version_id") is not None else None,
        trigger=trigger,
        strength=float(raw.get("strength") if raw.get("strength") is not None else 1.0),
    )


def load_style_defaults() -> tuple[StyleDefault, ...]:
    out: list[StyleDefault] = []
    for raw in _load_raw()["styles"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        if not slug:
            continue
        out.append(
            StyleDefault(
                slug=slug,
                display_name=str(raw.get("display_name") or slug).strip(),
                filename=str(raw.get("filename") or "").strip(),
                base_model=str(raw.get("base_model") or "sdxl").strip().lower(),
                civitai_url=str(raw.get("civitai_url") or "").strip() or None,
                model_id=int(raw["model_id"]) if raw.get("model_id") is not None else None,
                version_id=int(raw["version_id"]) if raw.get("version_id") is not None else None,
                download_url=str(raw.get("download_url") or "").strip() or None,
                sampler=str(raw.get("sampler") or "Euler a").strip(),
                scheduler=str(raw.get("scheduler") or "normal").strip(),
                steps=int(raw.get("steps") or 25),
                cfg_scale=float(raw.get("cfg_scale") if raw.get("cfg_scale") is not None else 5.0),
                clip_skip=int(raw.get("clip_skip") if raw.get("clip_skip") is not None else 2),
                width=int(raw.get("width") or 832),
                height=int(raw.get("height") or 1216),
                prefix=str(raw.get("prefix") or "").strip(),
                negative=str(raw.get("negative") or "").strip(),
                image_path=str(raw.get("image_path") or "").strip() or None,
                comment=str(raw["comment"]).strip() if raw.get("comment") else None,
                lora=_parse_lora(raw.get("lora")),
            )
        )
    if not out:
        raise ValueError("styles_defaults.json: no valid style rows")
    return tuple(out)


def canonical_style_slugs() -> tuple[str, ...]:
    global _CANONICAL_STYLE_SLUGS
    if not _CANONICAL_STYLE_SLUGS:
        _CANONICAL_STYLE_SLUGS = tuple(spec.slug for spec in load_style_defaults())
    return _CANONICAL_STYLE_SLUGS


def _upsert_lora(session, spec: StyleLoraDefault) -> Lora:
    row = session.scalar(select(Lora).where(Lora.filename == spec.filename))
    if row is None:
        row = Lora(
            kind=LORA_KIND_STYLE,
            filename=spec.filename,
            name=spec.name,
            strength=spec.strength,
        )
        session.add(row)
        session.flush()
    row.kind = LORA_KIND_STYLE
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


def _apply_style_fields(st: Style, spec: StyleDefault, lora_id: int | None) -> None:
    st.display_name = spec.display_name
    st.filename = spec.filename
    st.base_model = spec.base_model
    st.civitai_url = spec.civitai_url
    st.model_id = spec.model_id
    st.version_id = spec.version_id
    st.download_url = spec.download_url
    st.sampler = spec.sampler
    st.scheduler = spec.scheduler
    st.steps = spec.steps
    st.cfg_scale = spec.cfg_scale
    st.clip_skip = spec.clip_skip
    st.width = spec.width
    st.height = spec.height
    st.prefix = spec.prefix
    st.negative = spec.negative
    st.image_path = spec.image_path
    st.comment = spec.comment
    st.lora_id = lora_id


def ensure_default_styles(session) -> None:
    """Insert or refresh shipped canonical style rows (never deletes user-added styles)."""
    existing = {s.slug: s for s in session.scalars(select(Style))}
    for spec in load_style_defaults():
        lora_id = None
        if spec.lora is not None:
            lora_id = _upsert_lora(session, spec.lora).id
        row = existing.get(spec.slug)
        if row is None:
            session.add(
                Style(
                    slug=spec.slug,
                    display_name=spec.display_name,
                    lora_id=lora_id,
                )
            )
            session.flush()
            row = session.scalar(select(Style).where(Style.slug == spec.slug))
        if row is not None:
            _apply_style_fields(row, spec, lora_id)


__all__ = [
    "StyleDefault",
    "StyleLoraDefault",
    "canonical_style_slugs",
    "ensure_default_styles",
    "ensure_styles_defaults_file",
    "load_style_defaults",
]
