"""Pure data-driven scene composer.

Design rules (deliberate, enforced):

1. **No content knowledge.** This module does not know what a "mood",
   "bed", "kiss", "doggy", "framing", "gaze" or "pacing" means. It
   never branches on a tag string, an act slug or a location key.
2. **The schema is the contract.** The composer only reads columns
   that map to an output slot (tags, phases, style prefix, etc.).
   Other columns may exist on the model for storage or future use but
   are ignored here.
3. **Composition is concatenation + dedup.** Positive prompts are
   ordered tag groups joined with ``", "``; negatives are comma-separated
   tag lists. Any positive tag whose normalized key appears in the
   assembled SDXL negative (style + character + location + animation) is dropped before emit.
   Captions are sentence blocks joined with spaces. No prose templating,
   no synonym tables, no clever substitution.
4. **Missing user-controlled values fail loudly.** If a roll needs a
   style and there are no styles, we raise ``KeyError`` (surfaced as
   HTTP 400). We never invent defaults like "832x1216" or "english".

Sentinels accepted by :class:`BuildPayload`:

- ``"random"`` (or empty string) -> RNG pick from the matching table.
- ``style`` omitted / ``null`` -> RNG among all styles.
- Other fields: ``None`` / empty -> RNG pick (or optional slot rules).
- ``"none"``                                -> opt out (only meaningful for
   ``animation``, ``location``, ``view`` — fields where "absent" is a valid
   scene shape).

The seed makes every choice deterministic. Same seed + same DB content
-> identical output, by design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...make.limits import (
    MAKE_LAB_GENERATION_COUNT_MAX,
    MAKE_LAB_GENERATION_COUNT_MIN,
    MAKE_LAB_IMAGES_MAX,
    MAKE_LAB_IMAGES_MIN,
)
from ...db.models import Animation, DesignEntity, Style, View

# Protocol sentinels (NOT content). These are the strings the HTTP/UI
# layer passes to mean "let me pick" / "skip this slot".
RANDOM = "random"
NONE = "none"
# Make Lab refine model: use the rolled inference style checkpoint stack.
REFINE_SAME_AS_INFERENCE = "_inference"

MAKE_ENGINE_ILLUSTRIOUS = "illustrious"
MAKE_ENGINE_ANIMA = "anima"
MAKE_ENGINE_QWEN = "qwen_image_2512"
MAKE_ENGINES = (MAKE_ENGINE_ILLUSTRIOUS, MAKE_ENGINE_ANIMA, MAKE_ENGINE_QWEN)
QWEN_MAKE_SHIFT_DEFAULT = 3.1


def uses_illustrious_refine(engine: str | None) -> bool:
    """Qwen/Anima inference uses a diffusion stack; refine/detailers use SDXL."""
    target = (engine or "").strip().lower()
    return target in (MAKE_ENGINE_QWEN, MAKE_ENGINE_ANIMA)


# ---------------------------------------------------------------------------
# Public payload schemas
# ---------------------------------------------------------------------------


class ControlNetTypePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    strength: float | None = None
    start_percent: float | None = None
    end_percent: float | None = None


class ControlNetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openpose: ControlNetTypePayload | None = None
    depth: ControlNetTypePayload | None = None
    canny: ControlNetTypePayload | None = None


class RmbgPayload(BaseModel):
    """Remove-background stage (ComfyUI-RMBG) — optional post upscale."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str = "RMBG-2.0"
    sensitivity: float = 1.0
    process_res: Literal[512, 1024, 2048] = 1024
    mask_blur: int = Field(default=0, ge=0, le=64)
    mask_offset: int = Field(default=0, ge=-64, le=64)
    invert_output: bool = False
    refine_foreground: bool = False
    background: Literal["Alpha", "Color"] = "Alpha"
    background_color: str = "#000000"


class BuildPayload(BaseModel):
    """User choices for one scene roll."""

    model_config = ConfigDict(extra="forbid")

    character: str | None = None
    subject_type: Literal["character", "monster", "object"] | None = None
    animation: str | None = None
    location: str | None = None
    style: str | None = None
    refine_style: str | None = None
    engine: Literal["illustrious", "anima", "qwen_image_2512"] | None = None
    shift: float | None = None
    view: str | None = None
    orientation: str | None = None
    seed: int | None = None
    sampler: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg_scale: float | None = None
    width: int | None = None
    height: int | None = None
    images: int = Field(
        default=MAKE_LAB_IMAGES_MIN,
        ge=MAKE_LAB_IMAGES_MIN,
        le=MAKE_LAB_IMAGES_MAX,
    )
    generation_count: int = Field(
        default=MAKE_LAB_GENERATION_COUNT_MIN,
        ge=MAKE_LAB_GENERATION_COUNT_MIN,
        le=MAKE_LAB_GENERATION_COUNT_MAX,
    )
    upscale_model: str | None = None
    upscale_by: float | None = Field(default=None, ge=1.0, le=4.0)
    refine_steps: int | None = Field(default=None, ge=1, le=60)
    refine_denoise: float | None = Field(default=None, ge=0.0, le=1.0)
    refine_enabled: bool | None = None
    upscale_enabled: bool | None = None
    upscale_timing: Literal["before", "after", "disabled"] | None = None
    detailers: list[str] | None = None
    detailer_timing: Literal["before", "after", "disabled"] | None = None
    lora_strength_overrides: dict[str, float] | None = None
    controlnet: ControlNetPayload | None = None
    rmbg: RmbgPayload | None = None


@dataclass
class Scene:
    """The picked rows for one scene. Exposed for /api/build debug output."""

    seed: int
    character: DesignEntity | None = None
    animation: Animation | None = None
    style: Style | None = None
    location: DesignEntity | None = None
    views: list[View] = field(default_factory=list)
    orientation: str = "portrait"

    @property
    def view(self) -> View | None:
        """First resolved view (shot if present); prefer :attr:`views`."""
        return self.views[0] if self.views else None

    def summary(self) -> dict[str, Any]:
        """A flat dict of slugs/keys for the ``scene`` field on /api/build."""
        return {
            "seed": self.seed,
            "character": _slug_of(self.character),
            "animation": _slug_of(self.animation),
            "style": _slug_of(self.style),
            "location": self.location.key if self.location else None,
            "views": [v.key for v in self.views],
            "orientation": self.orientation,
            "controlnets": _resolved_controlnets_summary(self.animation),
        }



def _slug_of(row) -> str | None:
    if row is None:
        return None
    return getattr(row, "slug", None) or getattr(row, "key", None)


def _resolved_controlnets_summary(animation: Animation | None) -> dict[str, Any]:
    from ..catalog.controlnet_types import normalize_controlnets_map

    if animation is None:
        return {}
    return normalize_controlnets_map(animation.controlnets or {})


