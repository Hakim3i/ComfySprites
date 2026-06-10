"""Location HTML form save — regression for page POST handlers."""

from __future__ import annotations

from webapp.db.test_seed import (
    TEST_BACKGROUND_DISPLAY_NAME,
    TEST_BACKGROUND_SCENE_TAGS,
    TEST_BACKGROUND_SLUG,
)


def test_location_form_update_round_trip(client):
    r = client.post(
        f"/backgrounds/{TEST_BACKGROUND_SLUG}",
        data={
            "key": TEST_BACKGROUND_SLUG,
            "display_name": TEST_BACKGROUND_DISPLAY_NAME,
            "tags": "\n".join(TEST_BACKGROUND_SCENE_TAGS),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]

    bg = next(
        b for b in client.get("/api/backgrounds").json() if b["key"] == TEST_BACKGROUND_SLUG
    )
    assert bg["display_name"] == TEST_BACKGROUND_DISPLAY_NAME
    assert bg["tags"] == list(TEST_BACKGROUND_SCENE_TAGS)