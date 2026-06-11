"""Minimal LTX prose fragment helpers (ported from Coomfy)."""

from __future__ import annotations

import re

_STYLE_VIDEO_PREFIX = re.compile(
    r"^(?:(?:a|an)\s+)?(?:lifelike\s+)?(?:cinematic\s+)?video\s+of\s+",
    re.IGNORECASE,
)
_STYLE_MEDIUM_SUFFIX = re.compile(
    r"\s+(?:photo|video|clip|footage|film)s?\s*$",
    re.IGNORECASE,
)
_CHARACTER_PREFIX = re.compile(
    r"^(?:featuring|with)\s+",
    re.IGNORECASE,
)
_LOCATION_PREFIX = re.compile(
    r"^(?:(?:in|inside|at)\s+(?:a|an|the)\s+|(?:a|an|the)\s+)",
    re.IGNORECASE,
)
_VOWELS = frozenset("aeiou")


def _strip_prefix(pattern: re.Pattern[str], text: str) -> str:
    out = text.strip()
    while True:
        nxt = pattern.sub("", out, count=1).strip()
        if nxt == out:
            return out
        out = nxt


def _lcfirst(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text[0].lower() + text[1:]


def _ucfirst(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _no_trailing_period(text: str) -> str:
    return text.rstrip(".").strip()


def style_register_fragment(text: str) -> str:
    raw = _strip_prefix(_STYLE_VIDEO_PREFIX, text or "")
    raw = _STYLE_MEDIUM_SUFFIX.sub("", raw.strip())
    return _ucfirst(_no_trailing_period(raw))


def character_body_fragment(text: str) -> str:
    raw = _strip_prefix(_CHARACTER_PREFIX, text or "")
    return _lcfirst(_no_trailing_period(raw))


def character_segment_text(display_name: str, body: str) -> str:
    name = (display_name or "").strip()
    prose = character_body_fragment(body)
    if name and prose:
        return f"{name}, {prose}"
    if name:
        return name
    return prose


def _article_for(noun_phrase: str) -> str:
    words = noun_phrase.strip().split()
    if not words:
        return "a"
    head = words[0].lower()
    if head.startswith(("honest", "hour", "heir")) or head[0] in _VOWELS:
        return "an"
    return "a"


def _ensure_article(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""
    if re.match(r"^(?:a|an|the)\s+", raw, re.IGNORECASE):
        if raw.lower().startswith("the "):
            rest = raw[4:].strip()
            return f"{_article_for(rest)} {rest}"
        return raw
    return f"{_article_for(raw)} {raw}"


def location_fragment(text: str) -> str:
    raw = _strip_prefix(_LOCATION_PREFIX, text or "")
    raw = _no_trailing_period(raw)
    raw = _ensure_article(raw)
    m = re.match(r"^(a|an)\s+(.*)$", raw, re.IGNORECASE)
    if m:
        return f"{m.group(1).lower()} {_lcfirst(m.group(2))}"
    return _lcfirst(raw)


def scene_opener_text(character_text: str, location_text: str) -> str:
    parts = [p.strip() for p in (character_text, location_text) if (p or "").strip()]
    if not parts:
        return ""
    return ", ".join(parts)
