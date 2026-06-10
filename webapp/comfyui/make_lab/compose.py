"""Request parsing for Make Lab pipeline timing (compose lives in workflow_builder)."""

from __future__ import annotations

from typing import Any

UPSCALE_TIMING_DISABLED = "disabled"
UPSCALE_TIMING_BEFORE = "before"
UPSCALE_TIMING_AFTER = "after"
UPSCALE_TIMING_VALUES = frozenset(
    {UPSCALE_TIMING_DISABLED, UPSCALE_TIMING_BEFORE, UPSCALE_TIMING_AFTER}
)


def refine_enabled_from_request(request: dict[str, Any] | None) -> bool:
    """Default enabled when omitted (backward compatible with saved requests)."""
    if not request or "refine_enabled" not in request:
        return True
    return bool(request.get("refine_enabled"))


def upscale_enabled_from_request(request: dict[str, Any] | None) -> bool:
    """Legacy bool — prefer :func:`resolve_upscale_timing`."""
    return resolve_upscale_timing(request) != UPSCALE_TIMING_DISABLED


def resolve_upscale_timing(
    request: dict[str, Any] | None,
    *,
    refine_on: bool | None = None,
) -> str:
    """``disabled`` | ``before`` (pre-refine pixels) | ``after`` (post-refine decode)."""
    req = request or {}
    raw = str(req.get("upscale_timing") or "").strip().lower()
    if raw in UPSCALE_TIMING_VALUES:
        timing = raw
    elif "upscale_enabled" in req:
        timing = (
            UPSCALE_TIMING_AFTER
            if bool(req.get("upscale_enabled"))
            else UPSCALE_TIMING_DISABLED
        )
    else:
        timing = UPSCALE_TIMING_AFTER

    if refine_on is None:
        refine_on = refine_enabled_from_request(request)
    if timing == UPSCALE_TIMING_BEFORE and not refine_on:
        return UPSCALE_TIMING_AFTER
    return timing


def upscale_output_dimensions(
    width: int, height: int, upscale_by: float
) -> tuple[int, int]:
    """Target width/height after neural upscale (for ComfyUI ImageScale)."""
    by = max(1.0, float(upscale_by))
    return (
        max(1, int(round(int(width) * by))),
        max(1, int(round(int(height) * by))),
    )
