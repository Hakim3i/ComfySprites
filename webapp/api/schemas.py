"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..services.design import attributes as char_attrs
from ..db import ROLE_MAIN, VIEW_KIND_SHOT


class LoraStrengthPatch(BaseModel):
    """Patch only ``strength`` on an existing LoRA row (Photo / Video Lab save)."""

    strength: float


class AnimationOrientationPatch(BaseModel):
    """Patch animation default orientation from Make Lab (portrait / landscape only)."""

    orientation: str


ActOrientationPatch = AnimationOrientationPatch


class LoraIn(BaseModel):
    """Inline LoRA payload — embedded inside character / partner / act / style
    payloads. ``filename`` is required; set the whole object to ``null`` to
    unlink the LoRA from the parent.
    """

    filename: str = Field(..., description="Must match a file under ComfyUI/models/loras/<kind>/")
    name: str | None = None
    trigger: str | None = None
    caption_trigger: str | None = None
    strength: float = 1.0
    url: str | None = None
    download_url: str | None = None
    download_fallback_url: str | None = None
    model_id: int | None = None
    version_id: int | None = None
    comment: str | None = None


class CharacterIn(BaseModel):
    """Create or upsert payload for a main or partner character."""

    slug: str = Field(..., min_length=1)
    display_name: str | None = None
    name_tag: str | None = None
    comment: str | None = None
    role: str = ROLE_MAIN
    identity_core: list[str] = Field(default_factory=list)
    outfit_head: list[str] = Field(default_factory=list)
    outfit_upper: list[str] = Field(default_factory=list)
    outfit_lower: list[str] = Field(default_factory=list)
    outfit_extra: list[str] = Field(default_factory=list)
    partner_position: int = 0
    lora: LoraIn | None = None
    hair_color: str | None = None
    hair_length: str | None = None
    hair_style: str | None = None
    eye_color: str | None = None
    eye_shape: str | None = None
    facial_marks: list[str] = Field(default_factory=list)
    glasses: str | None = None
    makeup: str | None = None
    age_band: str | None = None
    ethnicity: str | None = None
    skin_tone: str | None = None
    height: str | None = None
    breast_size: str | None = None
    body_type: str | None = None
    muscle: str | None = None
    piercings: list[str] = Field(default_factory=list)
    tattoos: list[str] = Field(default_factory=list)
    hip_size: str | None = None
    butt_size: str | None = None
    thigh_type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_physical_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in list(data.keys()):
            attr = char_attrs.ATTRIBUTES_BY_KEY.get(key)
            if attr is not None:
                data[key] = char_attrs.coerce_physical_incoming(attr, data[key])
        return data


class AnimationIn(BaseModel):
    slug: str = Field(..., min_length=1)
    menu_name: str | None = None
    subject_type: str = "character"
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)
    framings: list[str] = Field(default_factory=list)
    orientation: str | None = None
    controlnets: dict[str, dict[str, Any]] | None = None
    lora: LoraIn | None = None


ActIn = AnimationIn


class ViewIn(BaseModel):
    key: str = Field(..., min_length=1)
    kind: str = VIEW_KIND_SHOT
    label: str | None = None
    position: int = 0
    comment: str | None = None
    framing_clause: str | None = None


def _style_in_defaults():
    from ..services.catalog.style_defaults import new_style_defaults

    return new_style_defaults()


class StyleIn(BaseModel):
    slug: str = Field(..., min_length=1)
    name: str | None = None
    filename: str = ""
    base_model: str = Field(default_factory=lambda: _style_in_defaults().base_model)
    civitai_url: str | None = None
    model_id: int | None = None
    version_id: int | None = None
    download_url: str | None = None
    sampler: str = Field(default_factory=lambda: _style_in_defaults().sampler)
    scheduler: str = Field(default_factory=lambda: _style_in_defaults().scheduler)
    steps: int = Field(default_factory=lambda: _style_in_defaults().steps)
    cfg_scale: float = Field(default_factory=lambda: _style_in_defaults().cfg_scale)
    clip_skip: int = Field(default_factory=lambda: _style_in_defaults().clip_skip)
    width: int = Field(default_factory=lambda: _style_in_defaults().width)
    height: int = Field(default_factory=lambda: _style_in_defaults().height)
    denoise_strength: float | None = None
    prefix: str = ""
    negative: str = ""
    comment: str | None = None
    lora: LoraIn | None = None


class LocationIn(BaseModel):
    key: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
