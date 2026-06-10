"""Animation pacing, visibility, and exposure helpers.

Single source of truth for animation-form option lists and composer logic.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...db.models import Animation, Character, View
else:
    Session = Any  # noqa: A008
    View = Any

from ...db.models import (
    ENTITY_CHARACTER,
    SUBJECT_TYPES,
    VIEW_KINDS,
)

ANIMATION_SUBJECT_TYPE_LABELS: dict[str, str] = {
    "character": "Character animation",
    "monster": "Monster animation",
    "object": "Object animation",
}


def animation_subject_type_options() -> list[tuple[str, str]]:
    return [(key, ANIMATION_SUBJECT_TYPE_LABELS[key]) for key in SUBJECT_TYPES]


def normalize_animation_subject_type(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in SUBJECT_TYPES:
        return value
    return ENTITY_CHARACTER

# Animation camera picker: at most one view key per kind (stored in animation.framings in this order).
CAMERA_VIEW_KINDS = VIEW_KINDS

# LTX arc + phase keys: ``AnimationPhase.phase``, audio tiers, sex voice types.
_PHASE_KEY_RE = re.compile(r"^phase_(\d+)$", re.IGNORECASE)

ANIMATION_ORIENTATIONS: tuple[tuple[str, str], ...] = (
    ("portrait", "Portrait"),
    ("landscape", "Landscape"),
    ("both", "Both"),
)


def animation_orientations() -> tuple[tuple[str, str], ...]:
    return ANIMATION_ORIENTATIONS


# Which character body regions may contribute to SDXL when checked.
VISIBLE_CHARACTER_PARTS: tuple[tuple[str, str], ...] = (
    ("core", "Core identity"),
    ("head", "Head / face / hair"),
    ("upper", "Upper body"),
    ("lower", "Lower body"),
)


def unique_tags(*groups: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            tag = (str(raw) if raw is not None else "").strip()
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                out.append(tag)
    return out


def normalize_visible_parts(values: Iterable[str] | None) -> list[str]:
    """Dedupe visibility keys (core / head / upper / lower)."""
    out: list[str] = []
    for raw in values or []:
        key = (str(raw) if raw is not None else "").strip().lower()
        if key and key not in out:
            out.append(key)
    return out


def parse_phase_index(key: str) -> int | None:
    """Return 1-based index from ``phase_N``, or None if invalid."""
    m = _PHASE_KEY_RE.match((key or "").strip().lower())
    if not m:
        return None
    return int(m.group(1))


def phase_key(index: int) -> str:
    return f"phase_{index}"


def ordered_phase_keys(keys: Iterable[str]) -> tuple[str, ...]:
    """Sort ``phase_N`` keys numerically (``phase_1``, ``phase_2``, …)."""
    indexed = sorted(
        (i, k)
        for k in keys
        if (i := parse_phase_index(k)) is not None
    )
    return tuple(k for _, k in indexed)


def ordered_phases(animation: Animation) -> tuple[str, ...]:
    """Active LTX phases for an act — rows with text, ordered by index."""
    keys = [
        p.phase
        for p in getattr(animation, "phases", []) or []
        if (p.text or "").strip()
    ]
    ordered = ordered_phase_keys(keys)
    return ordered if ordered else (phase_key(1),)


def phases_are_contiguous(phases: Iterable[str]) -> bool:
    """True when phase keys are ``phase_1`` .. ``phase_N`` with no gaps."""
    indices = [i for k in phases if (i := parse_phase_index(k)) is not None]
    if not indices:
        return False
    indices.sort()
    return indices == list(range(1, indices[-1] + 1))


def phase_count(animation: Animation) -> int:
    return len(ordered_phases(animation))


def phases_up_to_depth(
    phases: tuple[str, ...],
    depth: int | None,
) -> tuple[str, ...]:
    """First ``depth`` phases (``phase_1`` … ``phase_N``); ``None``/0 = all."""
    if not phases:
        return (phase_key(1),)
    if depth is None or int(depth) <= 0:
        return phases
    top = parse_phase_index(phases[-1]) or len(phases)
    n = max(1, min(int(depth), top))
    return tuple(phase_key(i) for i in range(1, n + 1))


def phase_list_for_form(animation: Animation) -> list[dict[str, str]]:
    """Ordered phase cards for the animation form — text + audio + sex voice type per phase."""
    phase_rows = getattr(animation, "phases", []) or []
    phases = {p.phase: p.text or "" for p in phase_rows}
    sex_voice = {p.phase: (p.sex_voice_type or "") for p in phase_rows}
    audio = {
        t.phase: t.text or ""
        for t in getattr(animation, "audio_tiers", []) or []
        if (t.kind or "normal") == "normal"
    }
    all_keys = set(phases) | set(audio) | set(sex_voice)
    ordered = ordered_phase_keys(all_keys)
    if not ordered:
        ordered = (phase_key(1),)
    return [
        {
            "key": key,
            "text": phases.get(key, ""),
            "audio": audio.get(key, ""),
            "sex_voice_type": sex_voice.get(key, ""),
        }
        for key in ordered
    ]


def filter_character_regions(
    regions: dict[str, list[str]],
    visible_parts: Iterable[str] | None,
) -> dict[str, list[str]]:
    """Subset character region tags by checked visibility keys.

    ``visible_parts is None`` (no act) keeps all regions. An act with an
    empty list injects nothing.
    """
    from . import attributes as ca

    if visible_parts is None:
        return regions
    empty = {k: [] for k in regions}
    if not visible_parts:
        return empty
    allowed = {
        (str(p) if p is not None else "").strip().lower()
        for p in visible_parts
        if (p or "").strip()
    }
    mapping = {
        "core": ca.REGION_CORE,
        "head": ca.REGION_HEAD,
        "upper": ca.REGION_UPPER,
        "lower": ca.REGION_LOWER,
    }
    for part, region_key in mapping.items():
        if part in allowed:
            empty[region_key] = list(regions.get(region_key) or [])
    return empty


def visible_region_tags(
    character: Character | None,
    visible_parts: Iterable[str] | None,
) -> list[str]:
    """Tags from core/head/upper/lower when act visibility checkboxes allow.

    ``visible_parts is None``
    (no act) keeps all regions; an act with an empty list injects nothing.
    """
    if character is None:
        return []

    from . import attributes as ca

    regions = ca.merge_into_region_lists(character)
    filtered = filter_character_regions(regions, visible_parts)
    return unique_tags(
        filtered[ca.REGION_CORE],
        filtered[ca.REGION_HEAD],
        filtered[ca.REGION_UPPER],
        filtered[ca.REGION_LOWER],
    )


def parse_framings_form(form) -> list[str]:
    """Read one optional framing key per camera kind from the animation form."""
    keys: list[str] = []
    for kind in CAMERA_VIEW_KINDS:
        key = (form.get(f"framings_{kind}") or "").strip()
        if key:
            keys.append(key)
    return keys


def normalize_animation_framings(session: Session, keys: Iterable[str]) -> list[str]:
    """Keep at most one view key per kind; return keys in shot → angle → pov → focus order."""
    from sqlalchemy import select

    from ...db.models import View

    raw = [k.strip() for k in keys if (k or "").strip()]
    if not raw:
        return []
    rows = session.scalars(select(View).where(View.key.in_(raw))).all()
    by_key = {v.key: v for v in rows}
    by_kind_lists: dict[str, list[str]] = {k: [] for k in CAMERA_VIEW_KINDS}
    for key in raw:
        view = by_key.get(key)
        if view is None:
            continue
        kind = (view.kind or "").strip().lower()
        if kind in CAMERA_VIEW_KINDS:
            by_kind_lists[kind].append(key)

    def _pick_one(kind: str, candidates: list[str]) -> str | None:
        if not candidates:
            return None
        if kind == "pov" and len(candidates) > 1:
            specific = [k for k in candidates if k.strip().lower() != "pov"]
            if specific:
                return specific[-1]
        return candidates[-1]

    by_kind: dict[str, str] = {}
    for kind in CAMERA_VIEW_KINDS:
        picked = _pick_one(kind, by_kind_lists[kind])
        if picked:
            by_kind[kind] = picked
    return [by_kind[k] for k in CAMERA_VIEW_KINDS if k in by_kind]


def views_for_animation_framings(session: Session, animation: Animation | None) -> list[View]:
    """Resolve animation.framings to View rows (one per kind, shot → angle → pov → focus)."""
    from sqlalchemy import select

    from ...db.models import View

    if animation is None or not animation.framings:
        return []
    keys = normalize_animation_framings(session, animation.framings)
    if not keys:
        return []
    rows = session.scalars(select(View).where(View.key.in_(keys))).all()
    by_key = {v.key: v for v in rows}
    return [by_key[k] for k in keys if k in by_key]
