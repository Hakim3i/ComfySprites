from __future__ import annotations

import random
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..design.scene import acts_for_location, pick_location
from ...db.models import (
    ENTITY_BACKGROUND,
    ENTITY_CHARACTER,
    ROLE_MAIN,
    SUBJECT_TYPES,
    Animation,
    DesignEntity,
    Style,
    View,
)
from .payload import (
    MAKE_ENGINE_ILLUSTRIOUS,
    MAKE_ENGINE_QWEN,
    NONE,
    RANDOM,
    REFINE_SAME_AS_INFERENCE,
    BuildPayload,
    Scene,
    _resolved_controlnets_summary,
    _slug_of,
)

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
    return v == REFINE_SAME_AS_INFERENCE


def resolve_engine(payload: BuildPayload, inference_style: Style) -> str:
    raw = (payload.engine or "").strip().lower()
    if raw in (MAKE_ENGINE_ILLUSTRIOUS, MAKE_ENGINE_QWEN):
        return raw
    base = (inference_style.base_model or MAKE_ENGINE_ILLUSTRIOUS).strip().lower()
    if base == MAKE_ENGINE_QWEN:
        return MAKE_ENGINE_QWEN
    return MAKE_ENGINE_ILLUSTRIOUS


def _styles_for_engine(styles: Sequence[Style], engine: str) -> list[Style]:
    target = (engine or MAKE_ENGINE_ILLUSTRIOUS).strip().lower()
    return [s for s in styles if (s.base_model or "").strip().lower() == target]


def _illustrious_refine_styles(
    session: Session,
    installed_checkpoints: Iterable[str] | None,
) -> list[Style]:
    installed = _installed_checkpoint_keys(installed_checkpoints)
    all_styles = session.scalars(
        select(Style).options(joinedload(Style.lora)).order_by(Style.slug)
    ).all()
    styles = _styles_for_engine(
        _styles_usable_on_comfy(all_styles, installed), MAKE_ENGINE_ILLUSTRIOUS
    )
    if not styles:
        raise KeyError(
            "no illustrious style for Qwen refine; create an illustrious style row"
        )
    return styles


def _is_qwen_refine_auto_pick(raw: str | None) -> bool:
    """Qwen refine must use SDXL; auto-pick when unset, none, random, or legacy _inference."""
    v = (raw or "").strip().lower()
    if not v:
        return True
    return v in (REFINE_SAME_AS_INFERENCE, NONE, RANDOM)


def resolve_refine_style(
    session: Session,
    rng: random.Random,
    payload: BuildPayload,
    inference_style: Style,
    *,
    installed_checkpoints: Iterable[str] | None = None,
) -> Style:
    """Pick the refine checkpoint style; defaults to *inference_style*."""
    engine = resolve_engine(payload, inference_style)
    if engine == MAKE_ENGINE_QWEN and _is_qwen_refine_auto_pick(payload.refine_style):
        return rng.choice(_illustrious_refine_styles(session, installed_checkpoints))
    if _is_refine_same_as_inference(payload.refine_style):
        return inference_style
    installed = _installed_checkpoint_keys(installed_checkpoints)
    all_styles = session.scalars(
        select(Style).options(joinedload(Style.lora)).order_by(Style.slug)
    ).all()
    styles = _styles_usable_on_comfy(all_styles, installed)
    if engine == MAKE_ENGINE_QWEN:
        styles = _styles_for_engine(styles, MAKE_ENGINE_ILLUSTRIOUS)
        if not styles:
            raise KeyError(
                "no illustrious style for Qwen refine; create an illustrious style row"
            )
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
        if engine == MAKE_ENGINE_QWEN and choice == NONE:
            choice = None
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
    from .render import _lora_to_payload, _style_checkpoint_payload

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
    if (style.download_fallback_url or "").strip():
        return True
    return style.version_id is not None


def _style_row_usable(s: Style) -> bool:
    if (s.slug or "").strip().lower() == RANDOM:
        return False
    return bool((s.filename or "").strip())


def _styles_usable_on_comfy(
    styles: Sequence[Style],
    installed: frozenset[str] | None,
) -> list[Style]:
    """Style rows eligible for RNG rolls (non-empty filename, optional ComfyUI filter)."""
    usable = [s for s in styles if _style_row_usable(s)]
    if not usable:
        raise KeyError(
            "no style entries with checkpoint filenames in DB; create one in Styles first"
        )
    if installed is None:
        return list(usable)
    matched: list[Style] = []
    for s in usable:
        base = (s.base_model or "").strip().lower()
        if base == MAKE_ENGINE_QWEN:
            if _style_checkpoint_downloadable(s):
                matched.append(s)
        elif s.filename.strip().lower() in installed:
            matched.append(s)
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
    engine = (payload.engine or "").strip().lower()
    if engine in (MAKE_ENGINE_ILLUSTRIOUS, MAKE_ENGINE_QWEN):
        styles = _styles_for_engine(styles, engine)
        if not styles:
            raise KeyError(f"no styles for engine {engine!r}")
    style_choice = _normalize_choice(payload.style)
    if _is_explicit_random(payload.style) or (style_choice is None and styles):
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

    # DesignEntity / monster / object subject ---------------------------------
    subject_types: tuple[str, ...] = SUBJECT_TYPES
    if payload.subject_type:
        subject_types = (payload.subject_type,)
    chars = session.scalars(
        select(DesignEntity)
        .where(
            DesignEntity.entity_type.in_(subject_types),
            DesignEntity.role == ROLE_MAIN,
        )
        .order_by(DesignEntity.slug)
    ).all()
    character = _pick(
        rng,
        _normalize_choice(payload.character),
        chars,
        lambda c: c.slug,
        label="character",
        allow_none=False,
    )

    # Act / location
    acts = session.scalars(select(Animation).order_by(Animation.slug)).all()
    locations = session.scalars(
        select(DesignEntity)
        .where(DesignEntity.entity_type == ENTITY_BACKGROUND)
        .order_by(DesignEntity.slug)
    ).all()

    animation_choice = _normalize_choice(payload.animation)
    location_choice = _normalize_choice(payload.location)
    explicit_location = location_choice is not None and not _is_explicit_random(
        payload.location
    )
    explicit_animation = animation_choice is not None and not _is_explicit_random(
        payload.animation
    )

    if explicit_location and not explicit_animation:
        location = pick_location(rng, None, locations, location_choice)
        eligible_acts = acts_for_location(acts, location)
        animation = _pick(
            rng,
            animation_choice,
            eligible_acts,
            lambda a: a.slug,
            label="animation",
            allow_none=True,
        )
    elif explicit_animation and not explicit_location:
        animation = _pick(
            rng,
            animation_choice,
            acts,
            lambda a: a.slug,
            label="animation",
            allow_none=True,
        )
        location = pick_location(rng, animation, locations, location_choice)
    else:
        animation = _pick(
            rng,
            animation_choice,
            acts,
            lambda a: a.slug,
            label="animation",
            allow_none=True,
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
        keys = {
            k.strip().lower() for k in (animation.framings or []) if (k or "").strip()
        }
        if choice not in keys:
            raise KeyError(
                f"view {choice!r} is not configured on animation {animation.slug!r}"
            )
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
    if animation and (animation.orientation or "").strip().lower() in (
        "portrait",
        "landscape",
    ):
        return animation.orientation.strip().lower()
    if style and style.width and style.height:
        return "portrait" if style.width <= style.height else "landscape"
    return "portrait"

