"""Cover image upload API for animations and backgrounds."""

from __future__ import annotations

from pathlib import Path

from webapp.config import UPLOADS_DIR, UPLOADS_URL_PREFIX
from webapp.db.seed_constants import DEFAULT_ANIMATION_SLUG, DEFAULT_BACKGROUND_SLUG

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _purge_upload(public_url: str | None) -> None:
    if not public_url or not public_url.startswith(UPLOADS_URL_PREFIX + "/"):
        return
    rel = public_url[len(UPLOADS_URL_PREFIX) + 1 :]
    path = UPLOADS_DIR / rel
    if path.is_file():
        path.unlink()


def test_animation_image_upload(client):
    r = client.post(
        f"/api/animations/{DEFAULT_ANIMATION_SLUG}/image",
        files={"file": ("cover.png", _PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["image_path"]
    assert body["image_path"].startswith(UPLOADS_URL_PREFIX)
    _purge_upload(body["image_path"])


def test_background_image_upload(client):
    r = client.post(
        f"/api/backgrounds/{DEFAULT_BACKGROUND_SLUG}/image",
        files={"file": ("cover.png", _PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["image_path"]
    assert body["image_path"].startswith(UPLOADS_URL_PREFIX)
    _purge_upload(body["image_path"])
