"""Inline character outfit tags (head / upper / lower / extra)."""

from __future__ import annotations

from ...db.models import DesignEntity

OUTFIT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("outfit_head", "outfit_head", "Outfit — head"),
    ("outfit_upper", "outfit_upper", "Outfit — upper body"),
    ("outfit_lower", "outfit_lower", "Outfit — lower body"),
    ("outfit_extra", "outfit_extra", "Outfit — extra"),
)


def parse_outfit_form(form) -> dict[str, list[str]]:
    from .forms import parse_taglist

    return {key: parse_taglist(form.get(field)) for key, field, _label in OUTFIT_FIELDS}


def outfit_form_context(character) -> dict[str, str]:
    from .forms import joined

    return {
        "outfit_values": {
            key: joined(list(getattr(character, key, None) or []))
            for key, _field, _label in OUTFIT_FIELDS
        }
    }


def outfit_zone_segments(
    character: DesignEntity | None,
) -> list[tuple[str, str, list[str]]]:
    """Outfit tag zones as SDXL segments: ``(source, label, tags)``."""
    if character is None:
        return []
    segments: list[tuple[str, str, list[str]]] = []
    for col, source, label in OUTFIT_FIELDS:
        tags = list(getattr(character, col, None) or [])
        if tags:
            segments.append((source, label, tags))
    return segments
