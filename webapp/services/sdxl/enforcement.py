"""SDXL prompt tag enforcement (parentheses weighting)."""

from __future__ import annotations

from typing import Iterable


def _is_wrapped(tag: str) -> bool:
    if len(tag) < 2 or not tag.startswith("(") or not tag.endswith(")"):
        return False
    depth = 0
    for i, ch in enumerate(tag):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(tag) - 1:
                return False
    return depth == 0


def enforce_sdxl_tags(tags: Iterable[str]) -> list[str]:
    """Wrap each tag in ``(…)`` for SDXL emphasis; skip tags already wrapped."""
    out: list[str] = []
    for raw in tags:
        tag = (raw or "").strip()
        if not tag:
            continue
        if _is_wrapped(tag):
            out.append(tag)
        else:
            out.append(f"({tag})")
    return out


def sdxl_tag_key(tag: str) -> str:
    """Normalize a tag for case-insensitive comparison (unwrap ``(…)`` emphasis)."""
    t = (tag or "").strip()
    if _is_wrapped(t):
        t = t[1:-1].strip()
    return t.lower()


def filter_sdxl_tags_by_ban_keys(
    tags: Iterable[str], ban_keys: set[str]
) -> list[str]:
    """Drop tags whose normalized key appears in ``ban_keys``."""
    if not ban_keys:
        return list(tags or [])
    out: list[str] = []
    for raw in tags or ():
        tag = (raw or "").strip()
        if not tag:
            continue
        if sdxl_tag_key(tag) in ban_keys:
            continue
        out.append(tag)
    return out
