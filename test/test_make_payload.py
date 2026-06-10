"""Make tab build payload contract tests."""

from __future__ import annotations

from webapp.db.test_seed import (
    TEST_ANIMATION_SLUG,
    TEST_BACKGROUND_SLUG,
    TEST_CHARACTER_SLUG,
    TEST_STYLE_SLUG,
)


def test_build_rejects_legacy_ui_field_names(client):
    r = client.post(
        "/api/build",
        json={
            "character": TEST_CHARACTER_SLUG,
            "style": TEST_STYLE_SLUG,
            "background": TEST_BACKGROUND_SLUG,
            "skin": "casual",
        },
    )
    assert r.status_code == 422
    assert "Extra inputs" in r.text


def test_build_accepts_location_and_act_none(client):
    r = client.post(
        "/api/build",
        json={
            "character": TEST_CHARACTER_SLUG,
            "subject_type": "character",
            "style": TEST_STYLE_SLUG,
            "animation": "none",
            "location": TEST_BACKGROUND_SLUG,
            "seed": 42,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"]["animation"] is None
    assert body["scene"]["location"] == TEST_BACKGROUND_SLUG


def test_build_monster_subject_type(client):
    from webapp.db.test_seed import TEST_MONSTER_SLUG

    r = client.post(
        "/api/build",
        json={
            "character": TEST_MONSTER_SLUG,
            "subject_type": "monster",
            "style": TEST_STYLE_SLUG,
            "animation": TEST_ANIMATION_SLUG,
            "location": TEST_BACKGROUND_SLUG,
            "seed": 7,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["scene"]["character"] == TEST_MONSTER_SLUG
