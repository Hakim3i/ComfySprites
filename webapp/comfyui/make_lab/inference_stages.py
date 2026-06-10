"""Backward-compatible re-exports for Make Lab stage toggles."""

from __future__ import annotations

from .compose import (
    UPSCALE_TIMING_AFTER,
    UPSCALE_TIMING_BEFORE,
    UPSCALE_TIMING_DISABLED,
    refine_enabled_from_request,
    resolve_upscale_timing,
    upscale_enabled_from_request,
)
from ..workflow_builder import infer_upscale_timing


