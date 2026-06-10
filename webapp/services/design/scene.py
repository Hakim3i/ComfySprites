"""Animation → location helpers for scene rolls and Make."""

from __future__ import annotations

import random
from typing import Sequence

from ...db.models import Animation, Character, Location


class SceneCompatibilityError(ValueError):
    """Explicit animation/location combination is not allowed."""


def acts_for_location(
    all_acts: Sequence[Animation],
    location: Location | None,
) -> list[Animation]:
    """All animations are eligible at any location (sprite stills — no pose/support gating)."""
    return list(all_acts)


def locations_for_act(
    all_locations: Sequence[Location],
    act: Animation | None,
) -> list[Location]:
    """All locations are eligible for any animation."""
    return list(all_locations)


def pick_location(
    rng: random.Random,
    act: Animation | None,
    all_locations: Sequence[Location],
    choice: str | None,
) -> Location | None:
    """Resolve location from explicit ``choice`` or random roll."""
    eligible = locations_for_act(all_locations, act)
    if choice is not None:
        target = choice.strip().lower()
        match = next((loc for loc in all_locations if loc.key.lower() == target), None)
        if match is None:
            raise KeyError(f"unknown location: {choice!r}")
        eligible_keys = {loc.key.lower() for loc in eligible}
        if match.key.lower() not in eligible_keys:
            raise SceneCompatibilityError(
                f"location {choice!r} is not compatible with the chosen animation"
            )
        return match
    if not eligible:
        return None
    return rng.choice(eligible)
