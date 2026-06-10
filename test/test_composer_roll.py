"""Composer roll() — act/location interlock, seed=-1, checkpoint filtering."""

from __future__ import annotations

import pytest

from conftest import boot_webapp_client
from webapp.db.test_seed import (
    TEST_ANIMATION_SLUG,
    TEST_BACKGROUND_SLUG,
    TEST_CHARACTER_SLUG,
    TEST_STYLE_SLUG,
)
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
                character=TEST_CHARACTER_SLUG,
                location=TEST_BACKGROUND_SLUG,
                style=TEST_STYLE_SLUG,
                seed=100,
            ),
        )
    assert scene.location is not None
    assert scene.location.key == TEST_BACKGROUND_SLUG


def test_roll_seed_minus_one_assigns_workflow_seed(client):
    from webapp.db import session_scope

    with session_scope() as session:
        scene = roll(
            session,
            BuildPayload(
                character=TEST_CHARACTER_SLUG,
                animation=TEST_ANIMATION_SLUG,
                style=TEST_STYLE_SLUG,
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
                character=TEST_CHARACTER_SLUG,
                animation=TEST_ANIMATION_SLUG,
                style=TEST_STYLE_SLUG,
                seed=42,
            ),
            installed_checkpoints=[TEST_STYLE_SLUG],
        )
    assert scene.style is not None
    assert scene.style.slug == TEST_STYLE_SLUG
