"""Shared negative prompt parsing and composition for all pipelines."""

from __future__ import annotations

from typing import Any

from ..design.forms import parse_taglist


def negative_tags(text: str | None) -> list[str]:
    """Split comma- or newline-separated negative tags for SDXL."""
    raw = (text or "").strip()
    if not raw:
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for part in parse_taglist(raw.replace(",", "\n")):
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(part)
    return tags


def entity_negative_text(entity: Any) -> str:
    return (getattr(entity, "negative", None) or "").strip()


def negative_prose(*entities: Any) -> str:
    parts = [entity_negative_text(e) for e in entities if e is not None]
    return ", ".join(p for p in parts if p)
