"""Make Lab history and gallery APIs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from conftest import boot_webapp_client


@pytest.fixture
def client(tmp_path_factory):
    yield from boot_webapp_client(tmp_path_factory, mktemp_name="make_lab_history")


def test_make_history_returns_saved_generations(client, monkeypatch):
    import webapp.config as cfg
    import webapp.services.generations as gen_mod

    root = cfg.DATASET_DIR.parent
    photos = root / "outputs" / "photos"
    photos.mkdir(parents=True)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", root)
    monkeypatch.setattr(gen_mod, "PROJECT_ROOT", root)

    from webapp.db import session_scope
    from webapp.services.generations import save_photo_generation

    build = {
        "scene": {
            "seed": 7,
            "character": "test_character",
            "animation": "test_act",
            "style": "test_style",
            "location": "test_background",
            "views": [],
        },
        "sdxl": {"width": 512, "height": 512, "checkpoint": {}},
    }
    (photos / "hist-1.png").write_bytes(b"\x89PNG\r\n")
    with session_scope() as session:
        save_photo_generation(
            session,
            prompt_id="hist-1",
            image_path="outputs/photos/hist-1.png",
            request={
                "character": "test_character",
                "animation": "test_act",
                "location": "test_background",
                "seed": 7,
            },
            build=build,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
        )

    r = client.get("/api/make/history?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["prompt_id"] == "hist-1"
    assert item["image_url"] == "/outputs/photos/hist-1.png"
    assert item["animation_slug"] == "test_act"
    assert item["character_slug"] == "test_character"
    assert item["location_slug"] == "test_background"
    assert item["request"]["seed"] == 7
    assert item["build"]["scene"]["character"] == "test_character"


def test_gallery_item_get_and_delete(client, monkeypatch):
    import webapp.config as cfg
    import webapp.services.generations as gen_mod

    root = cfg.DATASET_DIR.parent
    photos = root / "outputs" / "photos"
    photos.mkdir(parents=True)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", root)
    monkeypatch.setattr(gen_mod, "PROJECT_ROOT", root)

    from webapp.db import session_scope
    from webapp.services.generations import save_photo_generation

    build = {
        "scene": {"seed": 1, "character": "test_character", "animation": "test_act", "style": "test_style"},
        "sdxl": {"width": 512, "height": 512, "checkpoint": {}},
    }
    image_path = photos / "hist-del.png"
    image_path.write_bytes(b"\x89PNG\r\n")
    with session_scope() as session:
        save_photo_generation(
            session,
            prompt_id="hist-del",
            image_path="outputs/photos/hist-del.png",
            request={"character": "test_character", "animation": "test_act", "seed": 1},
            build=build,
        )

    got = client.get("/api/gallery/items/hist-del")
    assert got.status_code == 200
    assert got.json()["prompt_id"] == "hist-del"

    deleted = client.delete("/api/gallery/items/hist-del")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert not image_path.is_file()

    missing = client.get("/api/gallery/items/hist-del")
    assert missing.status_code == 404
