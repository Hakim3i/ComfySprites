"""Segment origin labels for validate/build UI."""

from __future__ import annotations

_SDXL_SEGMENT_LABELS: dict[str, str] = {
    "style": "Style → prefix",
    "triggers": "LoRA triggers (character, animation, style)",
    "character_core": "Character → core identity",
    "character_head": "Character → head / face / hair",
    "character_upper": "Character → upper body",
    "character_lower": "Character → lower body",
    "animation": "Animation → tags",
    "location": "Location → tags",
    "view": "Animation camera views (one per kind: shot, angle, pov, focus)",
    "character_negative": "Character → negative",
    "location_negative": "Location → negative",
    "animation_negative": "Animation → negative",
}

_OUTFIT_ZONE_LABELS: dict[str, str] = {
    "outfit_head": "head",
    "outfit_upper": "upper body",
    "outfit_lower": "lower body",
    "outfit_extra": "extra",
}


def sdxl_segment_labels() -> dict[str, str]:
    return _SDXL_SEGMENT_LABELS


def outfit_zone_labels() -> dict[str, str]:
    return _OUTFIT_ZONE_LABELS
