"""Make preview dimensions (mirrors composer orientation swap + form hints)."""

from __future__ import annotations

import re


def parse_dimension(key: str) -> tuple[int, int] | None:
    m = re.match(r"^(\d+)\s*[x×]\s*(\d+)$", (key or "").strip(), re.I)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def canonical_dimension_key(width: int, height: int) -> str:
    if not width or not height:
        return ""
    if width == height:
        return f"{width}x{height}"
    lo, hi = min(width, height), max(width, height)
    return f"{lo}x{hi}"


def swap_dimensions_for_orientation(
    width: int, height: int, orientation: str
) -> tuple[int, int]:
    """Match ``composer._render_sdxl`` resolution swap."""
    w, h = width, height
    o = (orientation or "").strip().lower()
    if o == "landscape" and h > w:
        w, h = h, w
    elif o == "portrait" and w > h:
        w, h = h, w
    return w, h


def expected_preview_dimensions(
    *,
    sdxl_width: int | None,
    sdxl_height: int | None,
    use_build_size: bool,
    dimension_key: str,
    orientation: str,
) -> tuple[int, int]:
    if use_build_size and sdxl_width and sdxl_height:
        return int(sdxl_width), int(sdxl_height)
    dim = parse_dimension(dimension_key)
    if not dim:
        return 1024, 1024
    w, h = swap_dimensions_for_orientation(dim[0], dim[1], orientation)
    return w, h
