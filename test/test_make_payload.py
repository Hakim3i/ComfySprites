"""Make tab build payload contract tests."""

from __future__ import annotations

from webapp.db.seed_constants import (
    DEFAULT_ANIMATION_SLUG,
    DEFAULT_BACKGROUND_SLUG,
    DEFAULT_CHARACTER_SLUG,
    DEFAULT_OBJECT_SLUG,
    DEFAULT_STYLE_SLUG,
)


def test_build_rejects_legacy_ui_field_names(client):
    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": DEFAULT_STYLE_SLUG,
            "background": DEFAULT_BACKGROUND_SLUG,
            "skin": "casual",
        },
    )
    assert r.status_code == 422
    assert "Extra inputs" in r.text


def test_build_accepts_location_and_act_none(client):
    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "subject_type": "character",
            "style": DEFAULT_STYLE_SLUG,
            "animation": "none",
            "location": DEFAULT_BACKGROUND_SLUG,
            "seed": 42,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"]["animation"] is None
    assert body["scene"]["location"] == DEFAULT_BACKGROUND_SLUG


def test_build_object_subject_type(client):
    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_OBJECT_SLUG,
            "subject_type": "object",
            "style": DEFAULT_STYLE_SLUG,
            "animation": DEFAULT_ANIMATION_SLUG,
            "location": DEFAULT_BACKGROUND_SLUG,
            "seed": 7,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["scene"]["character"] == DEFAULT_OBJECT_SLUG
