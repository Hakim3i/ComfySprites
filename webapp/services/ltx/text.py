"""LTX caption and negative text formatting."""

from __future__ import annotations

import re
from typing import Any

_NEGATIVE_CLAUSE_RE = re.compile(
    r"\s*[-–—]\s*(?:no|never|not)\b[^.]*(?=\.|$)",
    re.IGNORECASE,
)
_NEGATIVE_COMMA_RE = re.compile(
    r",\s*(?:no|never|not)\s+[^.]*(?=\.|$)",
    re.IGNORECASE,
)
_UNICODE_DASHES = str.maketrans({
    "\u2014": "-",
    "\u2013": "-",
    "\u2212": "-",
})

_LTX_NEG_VIDEO_SOURCES = frozenset({
    "style_ltx_video",
    "ltx_video",
    "character_negative",
    "location_negative",
    "animation_negative",
})
_LTX_NEG_AUDIO_SOURCES = frozenset({"style_ltx_audio", "ltx_audio"})


def sanitize_positive(text: str) -> str:
    if not (text or "").strip():
        return ""
    text = text.translate(_UNICODE_DASHES)
    cleaned = _NEGATIVE_CLAUSE_RE.sub("", text)
    cleaned = _NEGATIVE_COMMA_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return re.sub(r"\s+\.", ".", cleaned)


def format_cue(text: str) -> str:
    text = sanitize_positive(text).strip().rstrip(".")
    if not text:
        return ""
    return f"{text[0].upper()}{text[1:]}."


def format_ltx_negative(negative_segments: list[dict[str, Any]]) -> str:
    video = ", ".join(
        s["text"].strip()
        for s in negative_segments
        if s.get("source") in _LTX_NEG_VIDEO_SOURCES and (s.get("text") or "").strip()
    )
    audio = ", ".join(
        s["text"].strip()
        for s in negative_segments
        if s.get("source") in _LTX_NEG_AUDIO_SOURCES and (s.get("text") or "").strip()
    )
    if not video and not audio:
        return ""
    lines = ["#Video"]
    if video:
        lines.append(video)
    lines.append("")
    lines.append("#Audio")
    if audio:
        lines.append(audio)
    return "\n".join(lines)


def parse_ltx_negative_blocks(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return "", ""
    if not raw.startswith("#Video"):
        return raw, ""
    if "#Audio" not in raw:
        video = raw.replace("#Video", "", 1).strip()
        return video, ""
    before_audio, after_audio = raw.split("#Audio", 1)
    video = before_audio.replace("#Video", "", 1).strip()
    audio = after_audio.strip()
    return video, audio
