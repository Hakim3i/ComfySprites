"""HTML form POST smoke — one round-trip per entity editor."""

from __future__ import annotations

import pytest

from conftest import boot_webapp_client
from webapp.db.seed_constants import (
    DEFAULT_ANIMATION_SLUG,
    DEFAULT_BACKGROUND_SLUG,
    DEFAULT_CHARACTER_SLUG,
    DEFAULT_STYLE_SLUG,
)


@pytest.fixture
def client(tmp_path_factory):
    yield from boot_webapp_client(tmp_path_factory, mktemp_name="form_post_smoke")


def test_character_form_update_round_trip(client):
    r = client.post(
        f"/characters/{DEFAULT_CHARACTER_SLUG}",
        data={"key": DEFAULT_CHARACTER_SLUG, "display_name": "Asuna"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_background_form_update_round_trip(client):
    r = client.post(
        f"/backgrounds/{DEFAULT_BACKGROUND_SLUG}",
        data={"key": DEFAULT_BACKGROUND_SLUG, "tags": "indoors"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_animation_form_update_round_trip(client):
    r = client.post(
        f"/animations/{DEFAULT_ANIMATION_SLUG}",
        data={"key": DEFAULT_ANIMATION_SLUG, "label": "Standing idle"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_style_form_update_round_trip(client):
    r = client.post(
        f"/styles/{DEFAULT_STYLE_SLUG}",
        data={"key": DEFAULT_STYLE_SLUG, "name": "WAI Illustrious"},
        follow_redirects=False,
    )
    assert r.status_code == 303
