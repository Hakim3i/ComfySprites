"""Canonical option lists for structured character details.

Field registry (which columns exist, labels, regions) lives here.
Tag suggestion banks load from ``dataset/character_suggestions.json``
(editable on Settings).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


# Region keys mirror the four freeform character lists.
REGION_CORE = "identity_core"
REGION_HEAD = "identity_head"
REGION_UPPER = "body_upper"
REGION_LOWER = "body_lower"

REGION_LABELS: dict[str, str] = {
    REGION_CORE: "Overall identity",
    REGION_HEAD: "Face & head",
    REGION_UPPER: "Upper body",
    REGION_LOWER: "Lower body",
}

REGION_ORDER: tuple[str, ...] = (
    REGION_CORE,
    REGION_HEAD,
    REGION_UPPER,
    REGION_LOWER,
)


@dataclass(frozen=True)
class Attribute:
    """One structured detail field on the character form.

    Attributes
    ----------
    key
        DB column name on ``Character``.
    label
        Display label in the form.
    region
        Which freeform list this value merges into when
        :func:`merge_into_region_lists` runs (composer + forms).
    multi
        ``True`` if the value is a list (stored as a JSON column).
        Multi-values render as a comma-separated input.
    help
        Optional one-liner shown next to the field in the form.
    """

    key: str
    label: str
    region: str
    multi: bool = False
    help: str = ""

    @property
    def options(self) -> tuple[str, ...]:
        from ..catalog.character_suggestions import suggestion_tags

        return suggestion_tags(self.key)


# === Field registry =====================================================
# Order here is the order they render in the form. Keep grouped by region
# so the "Face & head" / "Upper body" / etc. fieldset boundaries are clean.

ATTRIBUTES: tuple[Attribute, ...] = (
    # --- Face & head -----------------------------------------------------
    Attribute("hair_color", "Hair color", REGION_HEAD),
    Attribute("hair_length", "Hair length", REGION_HEAD),
    Attribute("hair_style", "Hair style", REGION_HEAD),
    Attribute("eye_color", "Eye color", REGION_HEAD),
    Attribute("eye_shape", "Eye shape", REGION_HEAD),
    Attribute("facial_marks", "Facial marks", REGION_HEAD, multi=True),
    Attribute("glasses", "Eyewear", REGION_HEAD),
    Attribute("makeup", "Makeup", REGION_HEAD),
    # --- Overall identity ------------------------------------------------
    Attribute("age_band", "Age band", REGION_CORE),
    Attribute("ethnicity", "Ethnicity", REGION_CORE),
    Attribute("skin_tone", "Skin tone", REGION_CORE),
    Attribute("height", "Height", REGION_CORE),
    # --- Upper body ------------------------------------------------------
    Attribute("breast_size", "Chest / breasts", REGION_UPPER),
    Attribute("body_type", "Body type", REGION_UPPER),
    Attribute("muscle", "Muscle definition", REGION_UPPER),
    Attribute("piercings", "Piercings", REGION_UPPER, multi=True),
    Attribute("tattoos", "Tattoos", REGION_UPPER, multi=True),
    # --- Lower body ------------------------------------------------------
    Attribute("hip_size", "Hips", REGION_LOWER),
    Attribute("butt_size", "Butt", REGION_LOWER),
    Attribute("thigh_type", "Thighs", REGION_LOWER),
)


ATTRIBUTES_BY_KEY: dict[str, Attribute] = {a.key: a for a in ATTRIBUTES}
REGION_FOR_FIELD: dict[str, str] = {a.key: a.region for a in ATTRIBUTES}


def attributes_for_region(region: str) -> tuple[Attribute, ...]:
    """All attributes that route into the given region (rendered as a fieldset)."""
    return tuple(a for a in ATTRIBUTES if a.region == region)


def options_payload() -> dict[str, dict]:
    """JSON-friendly payload for ``GET /api/character-attributes``."""
    return {
        "regions": [
            {
                "key": region,
                "label": REGION_LABELS[region],
                "fields": [
                    {
                        "key": a.key,
                        "label": a.label,
                        "multi": a.multi,
                        "help": a.help,
                        "options": list(a.options),
                    }
                    for a in attributes_for_region(region)
                ],
            }
            for region in (REGION_HEAD, REGION_CORE, REGION_UPPER, REGION_LOWER)
        ]
    }


def parse_multi(raw: str | Iterable[str] | None) -> list[str]:
    """Normalise a multi-attribute value (comma- or newline-separated) into tags."""
    from .forms import parse_taglist

    if raw is None:
        return []
    if isinstance(raw, str):
        return parse_taglist(raw)
    return parse_taglist("\n".join(str(p) for p in raw))


def format_physical_display(attr: Attribute, value: Any) -> str:
    """Render a stored physical field for the HTML form."""
    if attr.multi:
        if isinstance(value, list):
            return ", ".join(str(v).strip() for v in value if str(v).strip())
        return str(value).strip() if value else ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value else ""


def coerce_physical_incoming(attr: Attribute, value: Any) -> str | list[str] | None:
    """Accept comma/newline text, a JSON list, or (multi only) a bare string."""
    if value is None or value == "":
        return [] if attr.multi else None
    if isinstance(value, list):
        tags = parse_multi(value)
    else:
        tags = parse_multi(str(value))
    if attr.multi:
        return tags
    return ", ".join(tags) if tags else None


def collect_extra_tags(character_obj) -> dict[str, list[str]]:
    """Return ``{region_key: [tags...]}`` extracted from the structured fields.

    Used by the prompt composer to merge structured values into the
    freeform identity lists. Single-value fields contribute one tag (if
    set); multi-value fields contribute their full list. Empty / unset
    fields contribute nothing. Order matches the ATTRIBUTES registry so
    output dicts are stable across runs.
    """
    buckets: dict[str, list[str]] = {
        REGION_CORE: [],
        REGION_HEAD: [],
        REGION_UPPER: [],
        REGION_LOWER: [],
    }
    for attr in ATTRIBUTES:
        value = getattr(character_obj, attr.key, None)
        if attr.multi:
            if value:
                buckets[attr.region].extend(
                    str(v).strip() for v in value if str(v).strip()
                )
        elif value:
            from .forms import parse_taglist

            buckets[attr.region].extend(parse_taglist(str(value)))
    return buckets


def identity_core_tags(character_obj) -> list[str]:
    """Freeform core identity tags for a character."""
    return list(character_obj.identity_core or [])


def freeform_region_lists(character_obj) -> dict[str, list[str]]:
    """Freeform tags per body region — mirrors what the HTML forms persist.

    Core tags live in ``identity_core`` for both roles. Head / upper / lower
    freeform lists are not stored; structured Physical fields merge into those
    regions at compose time via :func:`merge_into_region_lists`.
    """
    return {
        REGION_CORE: identity_core_tags(character_obj),
        REGION_HEAD: [],
        REGION_UPPER: [],
        REGION_LOWER: [],
    }


def merge_into_region_lists(
    character_obj,
    region_lists: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Return a new ``{region: [tags...]}`` map with the freeform lists
    extended by the structured tags. De-duplicates case-insensitively
    while preserving the original order (freeform first, then structured).
    """
    if region_lists is None:
        region_lists = freeform_region_lists(character_obj)
    extras = collect_extra_tags(character_obj)
    merged: dict[str, list[str]] = {}
    for region, freeform in region_lists.items():
        seen: set[str] = set()
        out: list[str] = []
        for tag in list(freeform) + extras.get(region, []):
            if not tag:
                continue
            low = tag.lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(tag)
        merged[region] = out
    return merged
