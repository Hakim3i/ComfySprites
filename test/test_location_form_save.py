"""Location HTML form save — regression for page POST handlers."""

from __future__ import annotations

from webapp.db.backgrounds_defaults import load_background_defaults
from webapp.db.seed_constants import DEFAULT_BACKGROUND_SLUG

_GREY_BG = next(b for b in load_background_defaults() if b.slug == DEFAULT_BACKGROUND_SLUG)


def test_location_form_update_round_trip(client):
    r = client.post(
        f"/backgrounds/{DEFAULT_BACKGROUND_SLUG}",
        data={
            "key": DEFAULT_BACKGROUND_SLUG,
            "tags": "\n".join(_GREY_BG.tags),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]

    bg = next(
        b
        for b in client.get("/api/backgrounds").json()
        if b["key"] == DEFAULT_BACKGROUND_SLUG
    )
    assert bg["tags"] == list(_GREY_BG.tags)
