"""SDXL prompt segment metadata (category → editor field)."""

from __future__ import annotations

from .labels import outfit_zone_labels, sdxl_segment_labels


def sdxl_segment_origin(source: str) -> str:
    """Human-readable DB field path for a segment ``source`` key."""
    if source.startswith("outfit_"):
        zone = source.removeprefix("outfit_")
        label = outfit_zone_labels().get(zone, zone)
        return f"Character → {label}"
    return sdxl_segment_labels().get(source, source)
