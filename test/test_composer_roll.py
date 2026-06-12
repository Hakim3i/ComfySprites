"""Composer roll() — act/location interlock, seed=-1, checkpoint filtering."""

from __future__ import annotations

import pytest

from conftest import boot_webapp_client
from webapp.db.seed_constants import (
    DEFAULT_ANIMATION_SLUG,
    DEFAULT_BACKGROUND_SLUG,
    DEFAULT_CHARACTER_SLUG,
    DEFAULT_STYLE_SLUG,
)
from webapp.db.styles_defaults import load_style_defaults

_WAI_FILENAME = next(
    s for s in load_style_defaults() if s.slug == DEFAULT_STYLE_SLUG
).filename
from webapp.services.sdxl.composer import BuildPayload, roll


@pytest.fixture
def client(tmp_path_factory):
    yield from boot_webapp_client(tmp_path_factory, mktemp_name="composer_roll")


def test_roll_explicit_location_constrains_animation(client):
    from webapp.db import session_scope

    with session_scope() as session:
        scene = roll(
            session,
            BuildPayload(
                character=DEFAULT_CHARACTER_SLUG,
                location=DEFAULT_BACKGROUND_SLUG,
                style=DEFAULT_STYLE_SLUG,
                seed=100,
            ),
        )
    assert scene.location is not None
    assert scene.location.key == DEFAULT_BACKGROUND_SLUG


def test_roll_seed_minus_one_assigns_workflow_seed(client):
    from webapp.db import session_scope

    with session_scope() as session:
        scene = roll(
            session,
            BuildPayload(
                character=DEFAULT_CHARACTER_SLUG,
                animation=DEFAULT_ANIMATION_SLUG,
                style=DEFAULT_STYLE_SLUG,
                seed=-1,
            ),
        )
    assert scene.seed >= 0


def test_roll_filters_styles_to_installed_checkpoints(client):
    from webapp.db import session_scope

    with session_scope() as session:
        scene = roll(
            session,
            BuildPayload(
                character=DEFAULT_CHARACTER_SLUG,
                animation=DEFAULT_ANIMATION_SLUG,
                style=DEFAULT_STYLE_SLUG,
                seed=42,
            ),
            installed_checkpoints=[_WAI_FILENAME],
        )
    assert scene.style is not None
    assert scene.style.slug == DEFAULT_STYLE_SLUG
