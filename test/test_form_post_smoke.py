"""HTML form POST smoke — one round-trip per entity editor."""

from __future__ import annotations

import pytest

from conftest import boot_webapp_client
from webapp.db.test_seed import (
    TEST_ANIMATION_SLUG,
    TEST_BACKGROUND_SLUG,
    TEST_CHARACTER_SLUG,
    TEST_STYLE_SLUG,
)


@pytest.fixture
def client(tmp_path_factory):
    yield from boot_webapp_client(tmp_path_factory, mktemp_name="form_post_smoke")


def test_character_form_update_round_trip(client):
    r = client.post(
        f"/characters/{TEST_CHARACTER_SLUG}",
        data={"key": TEST_CHARACTER_SLUG, "display_name": "Test Character"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_background_form_update_round_trip(client):
    r = client.post(
        f"/backgrounds/{TEST_BACKGROUND_SLUG}",
        data={"key": TEST_BACKGROUND_SLUG, "tags": "indoors"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_animation_form_update_round_trip(client):
    r = client.post(
        f"/animations/{TEST_ANIMATION_SLUG}",
        data={"key": TEST_ANIMATION_SLUG, "label": "Test Act"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_style_form_update_round_trip(client):
    r = client.post(
        f"/styles/{TEST_STYLE_SLUG}",
        data={"key": TEST_STYLE_SLUG, "name": "Test Style"},
        follow_redirects=False,
    )
    assert r.status_code == 303
