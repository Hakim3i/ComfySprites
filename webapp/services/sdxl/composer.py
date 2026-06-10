"""Pure data-driven scene composer (facade re-exports)."""

from .build import (
    build,
    payload_from_stored_build,
    resolve_controlnets_for_build,
    scene_from_stored_build,
)
from .payload import (
    NONE,
    RANDOM,
    REFINE_SAME_AS_INFERENCE,
    BuildPayload,
    ControlNetPayload,
    ControlNetTypePayload,
    RmbgPayload,
    Scene,
)
from .roll import roll

__all__ = [
    "BuildPayload",
    "ControlNetPayload",
    "ControlNetTypePayload",
    "RmbgPayload",
    "Scene",
    "RANDOM",
    "NONE",
    "REFINE_SAME_AS_INFERENCE",
    "build",
    "payload_from_stored_build",
    "scene_from_stored_build",
    "roll",
    "resolve_controlnets_for_build",
]
