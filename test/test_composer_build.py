"""Composer build output — no partner slots after partner removal."""

from __future__ import annotations

from webapp.db.test_seed import (
    TEST_ANIMATION_SLUG,
    TEST_BACKGROUND_SLUG,
    TEST_CHARACTER_SLUG,
    TEST_STYLE_SLUG,
)


def test_build_scene_has_no_partner(client):
    r = client.post(
        "/api/build",
        json={
            "character": TEST_CHARACTER_SLUG,
            "subject_type": "character",
            "style": TEST_STYLE_SLUG,
            "animation": TEST_ANIMATION_SLUG,
            "location": TEST_BACKGROUND_SLUG,
            "seed": 42,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    scene = body["scene"]
    assert "partner" not in scene
    kinds = {x.get("kind") for x in body["sdxl"].get("loras") or []}
    assert kinds <= {"style", "character", "animation"}
    seg_sources = {s.get("source") for s in body["sdxl"].get("positive_segments") or []}
    assert "partner" not in seg_sources


def test_scene_from_stored_build_ignores_legacy_partner(client):
    from webapp.db import session_scope
    from webapp.services.sdxl.composer import scene_from_stored_build

    build = {
        "scene": {
            "seed": 1,
            "character": TEST_CHARACTER_SLUG,
            "partner": "legacy_partner",
            "animation": TEST_ANIMATION_SLUG,
            "style": TEST_STYLE_SLUG,
            "location": TEST_BACKGROUND_SLUG,
            "views": [],
            "orientation": "portrait",
        }
    }
    with session_scope() as session:
        scene = scene_from_stored_build(session, build)
    assert scene.character is not None
    assert scene.character.slug == TEST_CHARACTER_SLUG
