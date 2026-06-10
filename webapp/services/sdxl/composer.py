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
   assembled SDXL negative (style + act extras) is dropped before emit.
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

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..design import animation_fields  # noqa: F401 — used via module attrs
from ...make.limits import (
    MAKE_LAB_GENERATION_COUNT_MAX,
    MAKE_LAB_GENERATION_COUNT_MIN,
    MAKE_LAB_IMAGES_MAX,
    MAKE_LAB_IMAGES_MIN,
)
from ..design import attributes as char_attrs
from ..design.outfit import outfit_zone_segments
from ..design.scene import (
    acts_for_location,
    pick_location,
)
from ...db.models import (
    ENTITY_BACKGROUND,
    ENTITY_CHARACTER,
    ROLE_MAIN,
    SUBJECT_TYPES,
    Animation,
    Character,
    DesignEntity,
    Location,
    Lora,
    Style,
    View,
)

# Protocol sentinels (NOT content). These are the strings the HTTP/UI
# layer passes to mean "let me pick" / "skip this slot".
RANDOM = "random"
NONE = "none"
# Make Lab refine model: use the rolled inference style checkpoint stack.
REFINE_SAME_AS_INFERENCE = "_inference"


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
    background_color: str = "#222222"


class BuildPayload(BaseModel):
    """User choices for one scene roll."""

    model_config = ConfigDict(extra="forbid")

    character: str | None = None
    subject_type: Literal["character", "monster", "object"] | None = None
    animation: str | None = None
    location: str | None = None
    style: str | None = None
    refine_style: str | None = None
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
    character: Character | None = None
    animation: Animation | None = None
    style: Style | None = None
    location: Location | None = None
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


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _slug_of(row) -> str | None:
    if row is None:
        return None
    return getattr(row, "slug", None) or getattr(row, "key", None)


def _resolved_controlnets_summary(animation: Animation | None) -> dict[str, Any]:
    from ..catalog.controlnet_types import normalize_controlnets_map

    if animation is None:
        return {}
    return normalize_controlnets_map(animation.controlnets or {})


def resolve_controlnets_for_build(
    animation: Animation | None,
    payload: BuildPayload,
) -> dict[str, dict[str, Any]]:
    """Merge animation defaults with Make toggles (enabled types only)."""
    from ..catalog.controlnet_types import (
        controlnet_defaults_for_type,
        normalize_controlnets_map,
    )

    stored = normalize_controlnets_map(
        (animation.controlnets or {}) if animation else {}
    )
    req = payload.controlnet
    if req is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, entry in stored.items():
        toggle = getattr(req, key, None)
        if toggle is None or not toggle.enabled:
            continue
        defaults = controlnet_defaults_for_type(key)
        out[key] = {
            "image_path": entry["image_path"],
            "strength": float(
                toggle.strength
                if toggle.strength is not None
                else entry.get("strength", defaults["strength"])
            ),
            "start_percent": float(
                toggle.start_percent
                if toggle.start_percent is not None
                else entry.get("start_percent", defaults["start_percent"])
            ),
            "end_percent": float(
                toggle.end_percent
                if toggle.end_percent is not None
                else entry.get("end_percent", defaults["end_percent"])
            ),
        }
    return out


def _normalize_choice(raw: str | None) -> str | None:
    """Map raw UI strings to a canonical choice; ``""`` / ``"random"`` -> ``None``."""
    if raw is None:
        return None
    v = raw.strip().lower()
    if not v or v == RANDOM:
        return None
    return v


def _is_explicit_random(raw: str | None) -> bool:
    return (raw or "").strip().lower() == RANDOM


def _is_refine_same_as_inference(raw: str | None) -> bool:
    """True when refine should reuse the inference style row (Make Lab default)."""
    v = (raw or "").strip().lower()
    if not v:
        return True
    if v == RANDOM:
        return False
    return v in (REFINE_SAME_AS_INFERENCE, "same_as_inference", "same as inference")


def resolve_refine_style(
    session: Session,
    rng: random.Random,
    payload: BuildPayload,
    inference_style: Style,
    *,
    installed_checkpoints: Iterable[str] | None = None,
) -> Style:
    """Pick the refine checkpoint style; defaults to *inference_style*."""
    if _is_refine_same_as_inference(payload.refine_style):
        return inference_style
    installed = _installed_checkpoint_keys(installed_checkpoints)
    all_styles = session.scalars(
        select(Style).options(joinedload(Style.lora)).order_by(Style.slug)
    ).all()
    styles = _styles_usable_on_comfy(all_styles, installed)
    if _is_explicit_random(payload.refine_style):
        picked = _pick(
            rng,
            None,
            styles,
            lambda s: s.slug,
            label="refine_style",
            allow_none=False,
        )
    else:
        choice = _normalize_choice(payload.refine_style)
        if choice is None:
            return inference_style
        picked = _pick(
            rng,
            choice,
            styles,
            lambda s: s.slug,
            label="refine_style",
            allow_none=False,
        )
    if picked.lora is None and picked.lora_id is not None:
        session.refresh(picked, attribute_names=["lora"])
    return picked


def _ensure_style_lora(session: Session, style: Style | None) -> None:
    """Load inline style LoRA before rendering SDXL payloads."""
    if style is not None and style.lora_id is not None and style.lora is None:
        session.refresh(style, attribute_names=["lora"])


def _refine_sdxl_payload(refine_style: Style, scene: Scene) -> dict[str, Any]:
    """Checkpoint + LoRAs for refine/detailers (refine style + character only)."""
    loras: list[dict[str, Any]] = []
    char_lora = scene.character.character_lora if scene.character else None
    for lora, kind in (
        (refine_style.lora, "style"),
        (char_lora, "character"),
    ):
        payload = _lora_to_payload(lora, kind=kind)
        if payload:
            loras.append(payload)
    return {
        "checkpoint": _style_checkpoint_payload(refine_style),
        "loras": loras,
    }


def _installed_checkpoint_keys(names: Iterable[str] | None) -> frozenset[str] | None:
    if names is None:
        return None
    return frozenset(str(n).strip().lower() for n in names if str(n).strip())


def _style_checkpoint_downloadable(style: Style) -> bool:
    if (style.download_url or "").strip():
        return True
    return style.version_id is not None


def _styles_usable_on_comfy(
    styles: Sequence[Style],
    installed: frozenset[str] | None,
) -> list[Style]:
    """Style rows eligible for RNG rolls (non-empty filename, optional ComfyUI filter)."""
    usable = [
        s
        for s in styles
        if (s.filename or "").strip()
        and (s.slug or "").strip().lower() != RANDOM
    ]
    if not usable:
        raise KeyError(
            "no style entries with checkpoint filenames in DB; create one in Styles first"
        )
    if installed is None:
        return list(usable)
    matched = [s for s in usable if s.filename.strip().lower() in installed]
    if matched:
        return matched
    downloadable = [s for s in usable if _style_checkpoint_downloadable(s)]
    if downloadable:
        return downloadable
    raise ValueError(
        "No dataset style matches a checkpoint installed on ComfyUI. "
        "Install a model under models/checkpoints, add download_url/version_id "
        "on a Style row, or fix style filenames in Settings."
    )


def _pick(
    rng: random.Random,
    choice: str | None,
    rows: Sequence,
    key_fn: Callable,
    *,
    label: str,
    allow_none: bool,
) -> Any:
    """Resolve a user choice against a list of rows.

    - ``choice is None``               -> RNG pick from ``rows`` (None if empty
                                          and ``allow_none``, else KeyError).
    - ``choice == "none"`` & ``allow`` -> returns ``None``.
    - any other string                 -> exact match via ``key_fn``; KeyError
                                          on miss. Comparison is
                                          case-insensitive.
    """
    if choice == NONE:
        if allow_none:
            return None
        raise KeyError(f"{label} cannot be 'none'")
    if choice is None:
        if not rows:
            if allow_none:
                return None
            raise KeyError(f"no {label} entries in DB; create one first")
        return rng.choice(list(rows))
    target = choice.lower()
    for row in rows:
        if str(key_fn(row)).strip().lower() == target:
            return row
    raise KeyError(f"unknown {label}: {choice!r}")


# ---------------------------------------------------------------------------
# Roll: pick concrete entities
# ---------------------------------------------------------------------------


def roll(
    session: Session,
    payload: BuildPayload,
    *,
    installed_checkpoints: Iterable[str] | None = None,
) -> Scene:
    """Resolve every slot in ``payload`` into a concrete DB row.

    The order is deliberate: pick style/character first, then act and location
    (explicit location constrains random acts).
    """
    if payload.seed is not None:
        seed_val = int(payload.seed)
        if seed_val == -1:
            workflow_seed = random.randrange(2**32)
            rng = random.Random(workflow_seed)
        else:
            workflow_seed = seed_val
            rng = random.Random(seed_val)
    else:
        workflow_seed = random.randrange(2**32)
        rng = random.Random(workflow_seed)

    # Style ----------------------------------------------------------------
    installed = _installed_checkpoint_keys(installed_checkpoints)
    all_styles = session.scalars(
        select(Style).options(joinedload(Style.lora)).order_by(Style.slug)
    ).all()
    styles = _styles_usable_on_comfy(all_styles, installed)
    style_choice = _normalize_choice(payload.style)
    if _is_explicit_random(payload.style) or (
        style_choice is None and styles
    ):
        style = _pick(
            rng, None, styles, lambda s: s.slug, label="style", allow_none=False
        )
    else:
        style = _pick(
            rng,
            style_choice,
            styles,
            lambda s: s.slug,
            label="style",
            allow_none=False,
        )

    # Character / monster / object subject ---------------------------------
    subject_types: tuple[str, ...] = SUBJECT_TYPES
    if payload.subject_type:
        subject_types = (payload.subject_type,)
    chars = session.scalars(
        select(DesignEntity)
        .where(
            DesignEntity.entity_type.in_(subject_types),
            DesignEntity.role == ROLE_MAIN,
        )
        .order_by(Character.slug)
    ).all()
    character = _pick(
        rng, _normalize_choice(payload.character), chars, lambda c: c.slug,
        label="character", allow_none=False,
    )

    # Act / location
    acts = session.scalars(select(Animation).order_by(Animation.slug)).all()
    locations = session.scalars(select(DesignEntity).where(DesignEntity.entity_type == ENTITY_BACKGROUND).order_by(DesignEntity.slug)).all()

    animation_choice = _normalize_choice(payload.animation)
    location_choice = _normalize_choice(payload.location)
    explicit_location = (
        location_choice is not None and not _is_explicit_random(payload.location)
    )
    explicit_animation = animation_choice is not None and not _is_explicit_random(payload.animation)

    if explicit_location and not explicit_animation:
        location = pick_location(rng, None, locations, location_choice)
        eligible_acts = acts_for_location(acts, location)
        animation = _pick(
            rng, animation_choice, eligible_acts, lambda a: a.slug,
            label="animation", allow_none=True,
        )
    elif explicit_animation and not explicit_location:
        animation = _pick(
            rng, animation_choice, acts, lambda a: a.slug,
            label="animation", allow_none=True,
        )
        location = pick_location(rng, animation, locations, location_choice)
    else:
        animation = _pick(
            rng, animation_choice, acts, lambda a: a.slug,
            label="animation", allow_none=True,
        )
        location = pick_location(rng, animation, locations, location_choice)

    views = _resolve_views(session, animation, _normalize_choice(payload.view))
    orientation = _resolve_orientation(
        rng,
        animation=animation,
        style=style,
        choice=_normalize_choice(payload.orientation),
    )

    return Scene(
        seed=workflow_seed,
        character=character,
        animation=animation,
        style=style,
        location=location,
        views=views,
        orientation=orientation,
    )


def _resolve_views(
    session: Session,
    animation: Animation | None,
    choice: str | None,
) -> list[View]:
    """Shot/angle/pov/focus rows from the act, optionally narrowed to one view key."""
    from ..design.animation_fields import views_for_animation_framings

    base = views_for_animation_framings(session, animation)
    if choice == NONE:
        return []
    if choice is None:
        return base
    view = session.scalar(select(View).where(View.key == choice))
    if view is None:
        raise KeyError(f"unknown view: {choice!r}")
    if base:
        keys = {k.strip().lower() for k in (animation.framings or []) if (k or "").strip()}
        if choice not in keys:
            raise KeyError(f"view {choice!r} is not configured on animation {animation.slug!r}")
        kind = (view.kind or "").strip().lower()
        kept = [v for v in base if (v.kind or "").strip().lower() != kind]
        return kept + [view]
    return [view]


def _resolve_orientation(
    rng: random.Random,
    *,
    animation: Animation | None,
    style: Style | None,
    choice: str | None = None,
) -> str:
    """Portrait/landscape from build override, act (including ``both``), or style aspect."""
    if choice == "both":
        return rng.choice(["portrait", "landscape"])
    if choice in ("portrait", "landscape"):
        return choice
    if animation and (animation.orientation or "").strip().lower() == "both":
        return rng.choice(["portrait", "landscape"])
    if animation and (animation.orientation or "").strip().lower() in ("portrait", "landscape"):
        return animation.orientation.strip().lower()
    if style and style.width and style.height:
        return "portrait" if style.width <= style.height else "landscape"
    return "portrait"


# ---------------------------------------------------------------------------
# Render: serialize a Scene to SDXL + LTX payloads
# ---------------------------------------------------------------------------


def _flatten_unique(groups: Iterable[Iterable[str]]) -> list[str]:
    """Concatenate tag groups preserving order, deduplicate case-insensitively."""
    out: list[str] = []
    seen: set[str] = set()
    for grp in groups:
        for raw in grp or ():
            tag = (raw or "").strip()
            if not tag:
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tag)
    return out


def _csv_split(s: str | None) -> list[str]:
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _character_adetailer_field_tags(
    character: Character,
    field_keys: tuple[str, ...],
    *,
    multi_keys: tuple[str, ...] = (),
) -> list[str]:
    from ..design.forms import parse_taglist

    tags: list[str] = []
    for key in field_keys:
        raw = getattr(character, key, None)
        if not raw:
            continue
        if key in multi_keys:
            tags.extend(char_attrs.parse_multi(raw))
        else:
            tags.extend(parse_taglist(str(raw)))
    return _flatten_unique([tags])


def _character_adetailer_payload(character: Character | None) -> dict[str, str]:
    """Per-region tag strings for Make Lab FaceDetailer prompts."""
    from ..design.forms import parse_taglist

    empty = {
        "face": "",
        "eyes": "",
        "hands": "",
        "feet": "",
        "penis": "",
        "pussy": "",
        "breasts": "",
        "anus": "",
    }
    if character is None:
        return dict(empty)

    face_tags = _character_adetailer_field_tags(
        character,
        ("eye_color", "eye_shape", "glasses", "makeup", "skin_tone"),
        multi_keys=("facial_marks",),
    )
    eye_tags = _character_adetailer_field_tags(
        character,
        ("eye_color", "eye_shape", "glasses"),
    )

    breast_tags: list[str] = []
    raw_breast = getattr(character, "breast_size", None)
    if raw_breast:
        breast_tags.extend(parse_taglist(str(raw_breast)))

    def _join(tags: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for raw in tags:
            tag = (raw or "").strip()
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                out.append(tag)
        return ", ".join(out)

    return {
        "face": _join(face_tags),
        "eyes": _join(eye_tags),
        "hands": "hands",
        "feet": "feet",
        "penis": "",
        "pussy": "",
        "breasts": _join(breast_tags),
        "anus": "",
    }


def _character_region_tags(c: Character | None) -> dict[str, list[str]]:
    """Return the four identity regions for a character, with structured
    detail fields merged in (eye_color, hair_style, etc.)."""
    if c is None:
        empty = {
            char_attrs.REGION_CORE: [],
            char_attrs.REGION_HEAD: [],
            char_attrs.REGION_UPPER: [],
            char_attrs.REGION_LOWER: [],
        }
        return empty
    return char_attrs.merge_into_region_lists(c)


def _style_checkpoint_payload(style: Style) -> dict[str, Any]:
    """Checkpoint file + sampler metadata for the build response."""
    return {
        "filename": style.filename,
        "name": style.name,
        "sampler": style.sampler,
        "scheduler": style.scheduler,
        "steps": int(style.steps or 25),
        "cfg_scale": float(style.cfg_scale or 5.0),
        "clip_skip": int(style.clip_skip or 2),
        "download_url": style.download_url,
        "version_id": style.version_id,
        "model_id": style.model_id,
        "civitai_url": style.civitai_url,
    }


def _lora_strength_value(strength: float | None) -> float:
    """Resolve DB strength; ``None`` defaults to 1.0 (``0`` stays ``0``)."""
    if strength is None:
        return 1.0
    return float(strength)


def _prune_zero_strength_loras(loras: list[Any]) -> None:
    """Drop build LoRA rows whose effective strength is exactly 0."""
    kept: list[Any] = []
    for item in loras:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        if _lora_strength_value(item.get("strength")) != 0.0:
            kept.append(item)
    loras[:] = kept


def _apply_lora_strength_overrides(
    build_result: dict[str, Any],
    overrides: dict[str, float] | None,
) -> None:
    """Apply Make spin-box strengths to build LoRA lists (saved or session)."""
    if not overrides:
        return
    for block_key in ("sdxl", "refine_sdxl"):
        block = build_result.get(block_key)
        if not isinstance(block, dict):
            continue
        loras = block.get("loras")
        if not isinstance(loras, list):
            continue
        for item in loras:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            if block_key == "refine_sdxl" and kind == "style" and "refine_style" in overrides:
                item["strength"] = float(overrides["refine_style"])
            elif kind in overrides and kind != "refine_style":
                item["strength"] = float(overrides[kind])
        _prune_zero_strength_loras(loras)


def _prune_zero_strength_loras_in_build(build_result: dict[str, Any]) -> None:
    """Remove strength-0 LoRAs from inference + refine lists (after overrides)."""
    for block_key in ("sdxl", "refine_sdxl"):
        block = build_result.get(block_key)
        if isinstance(block, dict) and isinstance(block.get("loras"), list):
            _prune_zero_strength_loras(block["loras"])


def _lora_to_payload(lora: Lora | None, *, kind: str) -> dict[str, Any] | None:
    """Serialize a linked LoRA row for the build response."""
    if lora is None or not (lora.filename or "").strip():
        return None
    strength = _lora_strength_value(lora.strength)
    out: dict[str, Any] = {
        "id": lora.id,
        "kind": kind,
        "filename": lora.filename,
        "strength": strength,
    }
    if lora.name:
        out["name"] = lora.name
    if lora.trigger:
        out["trigger"] = lora.trigger
    if lora.caption_trigger:
        out["caption_trigger"] = lora.caption_trigger
    if lora.url:
        out["url"] = lora.url
    if lora.download_url:
        out["download_url"] = lora.download_url
    if lora.download_fallback_url:
        out["download_fallback_url"] = lora.download_fallback_url
    if lora.model_id is not None:
        out["model_id"] = lora.model_id
    if lora.version_id is not None:
        out["version_id"] = lora.version_id
    return out


def _animation_lora_for(animation: Animation | None, side: str) -> Lora | None:
    if animation is None or side != "sdxl":
        return None
    loras = getattr(animation, "loras", None)
    if loras:
        link = next((l for l in animation.loras if l.kind == side), None)
        return link.lora if link else None
    return animation.lora


def _animation_visibility(animation: Any | None, attr: str) -> list[str] | None:
    """Visibility keys for act-driven SDXL region filtering.

    ``None`` keeps every region (no act, or the act row has no such field yet).
    An empty list means the act explicitly hides all regions for that slot.
    """
    if animation is None:
        return None
    if not hasattr(type(animation), attr):
        return None
    raw = getattr(animation, attr, None)
    if raw is None:
        return None
    return list(raw)


def _segment(source: str, label: str, tags: Iterable[str]) -> dict[str, Any]:
    from .segments import sdxl_segment_origin

    clean = [t.strip() for t in tags if (t or "").strip()]
    return {
        "source": source,
        "label": label,
        "tags": clean,
        "origin": sdxl_segment_origin(source),
    }


def _payload_inference(payload: BuildPayload) -> dict[str, Any]:
    """Map non-empty ``BuildPayload`` inference fields for SDXL render.

    Precedence: explicit payload values override the rolled style row for
    sampler, scheduler, steps, cfg_scale, width, and height. Empty or omitted
    payload fields are ignored so the style record supplies defaults.
    """
    out: dict[str, Any] = {}
    if payload.sampler:
        out["sampler"] = payload.sampler.strip()
    if payload.scheduler is not None and str(payload.scheduler).strip():
        out["scheduler"] = str(payload.scheduler).strip()
    if payload.steps is not None:
        out["steps"] = int(payload.steps)
    if payload.cfg_scale is not None:
        out["cfg_scale"] = float(payload.cfg_scale)
    if payload.width is not None:
        out["width"] = int(payload.width)
    if payload.height is not None:
        out["height"] = int(payload.height)
    return out


def _render_sdxl(
    scene: Scene,
    *,
    inference: dict[str, Any] | None = None,
    style: Style | None = None,
    for_refine: bool = False,
) -> dict[str, Any]:
    """Compose the SDXL payload purely by concatenation.

    When ``for_refine`` is true, act prompt tags/triggers/negative extras are
    kept but the act LoRA is omitted; refine stacks use style + character only.
    """
    style = style if style is not None else scene.style
    if style is None:
        raise KeyError("no style available; create at least one /styles row")
    inf = inference or {}
    eff_width = int(inf["width"]) if "width" in inf else style.width
    eff_height = int(inf["height"]) if "height" in inf else style.height
    if not eff_width or not eff_height:
        raise ValueError(
            f"style {style.slug!r} has no width/height; set them in the editor "
            f"before rolling SDXL prompts."
        )

    animation = scene.animation
    visible_char = _animation_visibility(animation, "visible_character")
    regions = _character_region_tags(scene.character)
    regions = animation_fields.filter_character_regions(regions, visible_char)

    char_lora = scene.character.character_lora if scene.character else None
    animation_sdxl_lora = _animation_lora_for(scene.animation, "sdxl")
    style_lora = style.lora

    trigger_loras = (char_lora, animation_sdxl_lora, style_lora)
    triggers = [l.trigger for l in trigger_loras if l and l.trigger]

    from .enforcement import enforce_sdxl_tags

    animation_tags = (
        enforce_sdxl_tags(scene.animation.tags or []) if scene.animation else []
    )
    location_tags = list(scene.location.tags or []) if scene.location else []
    view_tags = [v.key for v in scene.views if v.key]

    positive_segments: list[dict[str, Any]] = [
        _segment("style", "Style prefix", _csv_split(style.prefix)),
        _segment("triggers", "LoRA triggers", triggers),
        _segment("character_core", "Character — core", regions[char_attrs.REGION_CORE]),
        _segment("character_head", "Character — head", regions[char_attrs.REGION_HEAD]),
        _segment("character_upper", "Character — upper", regions[char_attrs.REGION_UPPER]),
        _segment("character_lower", "Character — lower", regions[char_attrs.REGION_LOWER]),
    ]
    if scene.character and scene.character.entity_type == ENTITY_CHARACTER:
        for source, label, tags in outfit_zone_segments(scene.character):
            positive_segments.append(_segment(source, label, tags))
    if scene.animation:
        positive_segments.append(_segment("animation", "Animation tags", animation_tags))
    positive_segments.extend([
        _segment("location", "Location", location_tags),
        _segment("view", "Camera view", view_tags),
    ])

    neg_segments: list[dict[str, Any]] = [
        _segment("style", "Style negative", _csv_split(style.negative)),
    ]
    if scene.animation:
        for n in getattr(scene.animation, "negatives", []) or []:
            if n.kind == "sdxl_extra":
                neg_segments.append(
                    _segment("animation_extra", "Animation SDXL negative extra", _csv_split(n.value))
                )
    negative = ", ".join(
        _flatten_unique(seg["tags"] for seg in neg_segments if seg["tags"])
    )

    from .enforcement import filter_sdxl_tags_by_ban_keys, sdxl_tag_key

    ban_keys = {
        sdxl_tag_key(t)
        for seg in neg_segments
        for t in (seg.get("tags") or [])
        if sdxl_tag_key(t)
    }
    if ban_keys:
        for seg in positive_segments:
            seg["tags"] = filter_sdxl_tags_by_ban_keys(seg.get("tags") or [], ban_keys)
    positive = ", ".join(
        _flatten_unique(seg["tags"] for seg in positive_segments if seg["tags"])
    )

    # Resolution: swap if user asked for the opposite orientation.
    w, h = eff_width, eff_height
    if scene.orientation == "landscape" and h > w:
        w, h = h, w
    elif scene.orientation == "portrait" and w > h:
        w, h = h, w

    loras: list[dict[str, Any]] = []
    lora_entries = (
        ((char_lora, "character"), (style_lora, "style"))
        if for_refine
        else (
            (char_lora, "character"),
            (animation_sdxl_lora, "animation"),
            (style_lora, "style"),
        )
    )
    for lora, kind in lora_entries:
        payload = _lora_to_payload(lora, kind=kind)
        if payload:
            loras.append(payload)

    checkpoint = _style_checkpoint_payload(style)
    if inf.get("sampler"):
        checkpoint["sampler"] = inf["sampler"]
    if "scheduler" in inf:
        checkpoint["scheduler"] = inf["scheduler"]
    if "steps" in inf:
        checkpoint["steps"] = inf["steps"]
    if "cfg_scale" in inf:
        checkpoint["cfg_scale"] = inf["cfg_scale"]

    return {
        "positive": positive,
        "negative": negative,
        "positive_segments": positive_segments,
        "negative_segments": neg_segments,
        "width": w,
        "height": h,
        "loras": loras,
        "checkpoint": checkpoint,
    }


def payload_from_stored_build(build: dict[str, Any]) -> BuildPayload:
    """Rebuild a :class:`BuildPayload` from a saved photo ``build_json``."""
    request = build.get("request") if isinstance(build.get("request"), dict) else {}
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}

    def _slot(key: str) -> Any:
        if key in scene and scene[key] not in (None, ""):
            return scene[key]
        return request.get(key)

    views = scene.get("views")
    view = views[0] if isinstance(views, list) and views else request.get("view")
    seed = scene.get("seed")
    if seed is None:
        seed = request.get("seed")
    return BuildPayload(
        character=_slot("character"),
        animation=_slot("animation") or _slot("act"),
        location=_slot("location"),
        style=_slot("style"),
        view=view,
        orientation=_slot("orientation"),
        seed=seed,
    )


def _row_by_slug(session: Session, model, slug: str | None):
    if not (slug or "").strip():
        return None
    return session.scalar(
        select(model).where(model.slug == str(slug).strip())  # type: ignore[attr-defined]
    )


def _location_by_key(session: Session, key: str | None) -> Location | None:
    if not (key or "").strip():
        return None
    return session.scalar(select(DesignEntity).where(DesignEntity.entity_type == ENTITY_BACKGROUND, DesignEntity.slug == str(key).strip()))


def scene_from_stored_build(session: Session, build: dict[str, Any]) -> Scene:
    """Reload the rolled scene rows by slug (no re-roll)."""
    stored = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    seed = stored.get("seed")
    if seed is None:
        seed = (build.get("request") or {}).get("seed")
    seed = int(seed or 0)
    animation = _row_by_slug(session, Animation, stored.get("animation") or stored.get("act"))
    views = _resolve_views(session, animation, None)
    view_keys = stored.get("views")
    if isinstance(view_keys, list) and view_keys:
        rows = session.scalars(select(View).where(View.key.in_(view_keys))).all()
        by_key = {v.key: v for v in rows}
        views = [by_key[k] for k in view_keys if k in by_key]
    character = _row_by_slug(session, Character, stored.get("character"))
    return Scene(
        seed=seed,
        character=character,
        animation=animation,
        style=_row_by_slug(session, Style, stored.get("style")),
        location=_location_by_key(session, stored.get("location")),
        views=views,
        orientation=(stored.get("orientation") or "portrait"),
    )


def build(
    session: Session,
    payload: BuildPayload,
    *,
    installed_checkpoints: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Resolve a scene and render SDXL + refine_sdxl payloads."""
    from ..generations import request_from_payload, resolve_request_from_build

    scene = roll(session, payload, installed_checkpoints=installed_checkpoints)
    _ensure_style_lora(session, scene.style)
    inference = _payload_inference(payload)
    refine_rng = random.Random(scene.seed ^ 0xA91E5EED)
    refine_style = resolve_refine_style(
        session,
        refine_rng,
        payload,
        scene.style,
        installed_checkpoints=installed_checkpoints,
    )
    _ensure_style_lora(session, refine_style)
    refine_same = _slug_of(refine_style) == _slug_of(scene.style)
    scene_summary = scene.summary()
    if refine_same:
        scene_summary["refine_style"] = REFINE_SAME_AS_INFERENCE
    else:
        scene_summary["refine_style"] = _slug_of(refine_style)
    enabled_controlnets = resolve_controlnets_for_build(scene.animation, payload)
    if enabled_controlnets:
        scene_summary["controlnets_enabled"] = list(enabled_controlnets.keys())

    result: dict[str, Any] = {
        "request": request_from_payload(payload),
        "sdxl": _render_sdxl(scene, inference=inference or None),
        "scene": scene_summary,
        "character_adetailer": _character_adetailer_payload(scene.character),
    }
    refine_render = _render_sdxl(
        scene, inference=inference or None, style=refine_style, for_refine=True
    )
    refine_sdxl = _refine_sdxl_payload(refine_style, scene)
    refine_sdxl["positive"] = refine_render["positive"]
    refine_sdxl["negative"] = refine_render["negative"]
    refine_sdxl["positive_segments"] = refine_render["positive_segments"]
    refine_sdxl["negative_segments"] = refine_render["negative_segments"]
    from ...comfyui.make_lab.detailers import detailer_style_positive_from_render
    from ...comfyui.workflow import make_lab_refine_loras_from_build

    refine_sdxl["detailer_style_positive"] = detailer_style_positive_from_render(
        refine_render
    )
    refine_sdxl["loras"] = make_lab_refine_loras_from_build(refine_render, None)
    result["refine_sdxl"] = refine_sdxl
    _apply_lora_strength_overrides(result, payload.lora_strength_overrides)
    _prune_zero_strength_loras_in_build(result)
    if enabled_controlnets:
        result["controlnet"] = enabled_controlnets
    result["request"] = resolve_request_from_build(result["request"], result)
    return result


__all__ = [
    "BuildPayload",
    "ControlNetPayload",
    "ControlNetTypePayload",
    "Scene",
    "RANDOM",
    "NONE",
    "REFINE_SAME_AS_INFERENCE",
    "build",
    "payload_from_stored_build",
    "scene_from_stored_build",
]
