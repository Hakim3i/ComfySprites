"""Animation HTML form save — regression for page POST handlers."""

from __future__ import annotations

from pathlib import Path

from webapp.config import UPLOADS_DIR, UPLOADS_URL_PREFIX
from webapp.db.test_seed import TEST_ANIMATION_FRAMINGS, TEST_ANIMATION_TAGS, TEST_SIDE_VIEW_KEY


def _purge_upload(public_url: str | None) -> None:
    if not public_url or not public_url.startswith(UPLOADS_URL_PREFIX + "/"):
        return
    rel = public_url[len(UPLOADS_URL_PREFIX) + 1 :]
    path = UPLOADS_DIR / rel
    if path.is_file():
        path.unlink()


def test_act_form_update_round_trip(client):
    r = client.post(
        "/animations/test_act",
        data={
            "slug": "test_act",
            "menu_name": "Sprite idle",
            "subject_type": "character",
            "tags": "\n".join(TEST_ANIMATION_TAGS),
            f"framings_angle": TEST_SIDE_VIEW_KEY,
            "orientation": "portrait",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]

    act = next(a for a in client.get("/api/animations").json() if a["slug"] == "test_act")
    assert act["tags"] == list(TEST_ANIMATION_TAGS)
    assert act["framings"] == list(TEST_ANIMATION_FRAMINGS)
    assert act["subject_type"] == "character"


def test_act_lora_settings_tab_round_trip(client):
    r = client.post(
        "/animations/test_act",
        data={
            "slug": "test_act",
            "menu_name": "Sprite idle",
            "subject_type": "character",
            "tags": "\n".join(TEST_ANIMATION_TAGS),
            f"framings_angle": TEST_SIDE_VIEW_KEY,
            "orientation": "portrait",
            "tab": "lora",
            "lora_filename": "anim-test.safetensors",
            "lora_name": "Anim Test",
            "lora_trigger": "animtest",
            "lora_strength": "0.85",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]

    act = next(a for a in client.get("/api/animations").json() if a["slug"] == "test_act")
    lora = act.get("lora") or act.get("sdxl_lora")
    assert lora is not None
    assert lora["filename"] == "anim-test.safetensors"
    assert lora["trigger"] == "animtest"
    assert float(lora["strength"]) == 0.85


def test_act_controlnet_image_upload(client):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = client.post(
        "/animations/test_act",
        data={
            "slug": "test_act",
            "menu_name": "Sprite idle",
            "subject_type": "character",
            "tags": "\n".join(TEST_ANIMATION_TAGS),
            f"framings_angle": TEST_SIDE_VIEW_KEY,
            "orientation": "portrait",
            "tab": "controlnet",
        },
        files={"controlnet_openpose_image": ("pose.png", png, "image/png")},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]

    act = next(a for a in client.get("/api/animations").json() if a["slug"] == "test_act")
    openpose = (act.get("controlnets") or {}).get("openpose") or {}
    image_path = openpose.get("image_path")
    assert image_path
    assert "/uploads/animations/controlnet/openpose/" in image_path
    _purge_upload(image_path)
    assert not Path(UPLOADS_DIR / image_path[len(UPLOADS_URL_PREFIX) + 1 :]).is_file()


def test_animation_api_subject_type_round_trip(client):
    r = client.post(
        "/api/animations",
        json={
            "slug": "monster_idle_test",
            "menu_name": "Monster idle",
            "subject_type": "monster",
            "tags": ["idle"],
            "framings": [],
            "orientation": "portrait",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["subject_type"] == "monster"
    assert body["slug"] == "monster_idle_test"
    client.delete("/api/animations/monster_idle_test")
