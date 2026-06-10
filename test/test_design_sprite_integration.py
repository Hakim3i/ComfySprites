"""Integration tests against canonical seeded test fixtures."""

from __future__ import annotations

import pytest

from webapp.db.models import ENTITY_BACKGROUND, ENTITY_CHARACTER, ENTITY_MONSTER, ENTITY_OBJECT
from webapp.db.test_seed import (
    E7_SPRITES_DOWNLOAD_FALLBACK_URL,
    E7_SPRITES_DOWNLOAD_URL,
    E7_SPRITES_FILENAME,
    E7_SPRITES_TRIGGER,
    E7_SPRITES_VERSION_ID,
    TEST_ANIMATION_FRAMINGS,
    TEST_ANIMATION_SLUG,
    TEST_ANIMATION_TAGS,
    TEST_BACKGROUND_DISPLAY_NAME,
    TEST_BACKGROUND_SCENE_TAGS,
    TEST_BACKGROUND_SLUG,
    TEST_CHARACTER_IDENTITY_CORE,
    TEST_CHARACTER_NAME_TAG,
    TEST_CHARACTER_OUTFIT,
    TEST_CHARACTER_PHYSICAL,
    TEST_CHARACTER_SLUG,
    TEST_MONSTER_SLUG,
    TEST_OBJECT_SLUG,
    TEST_SIDE_VIEW_KEY,
    TEST_STYLE_DISPLAY_NAME,
    TEST_STYLE_PREFIX,
    TEST_STYLE_SLUG,
)

DESIGN_SPRITE_TYPES = (
    ("character", ENTITY_CHARACTER, TEST_CHARACTER_SLUG),
    ("monster", ENTITY_MONSTER, TEST_MONSTER_SLUG),
    ("object", ENTITY_OBJECT, TEST_OBJECT_SLUG),
    ("background", ENTITY_BACKGROUND, TEST_BACKGROUND_SLUG),
)

_BUILD_PAYLOAD = {
    "character": TEST_CHARACTER_SLUG,
    "subject_type": "character",
    "style": TEST_STYLE_SLUG,
    "animation": TEST_ANIMATION_SLUG,
    "location": TEST_BACKGROUND_SLUG,
    "seed": 88,
}


@pytest.mark.parametrize("label,entity_type,entity_slug", DESIGN_SPRITE_TYPES)
def test_seeded_design_sprite_builds(client, label, entity_type, entity_slug):
    if entity_type == ENTITY_BACKGROUND:
        build_payload = {
            "character": TEST_CHARACTER_SLUG,
            "style": TEST_STYLE_SLUG,
            "animation": TEST_ANIMATION_SLUG,
            "location": entity_slug,
            "seed": 42,
        }
        expected_scene_key = "location"
        expected_scene_value = entity_slug
    else:
        build_payload = {
            "character": entity_slug,
            "style": TEST_STYLE_SLUG,
            "animation": TEST_ANIMATION_SLUG,
            "location": TEST_BACKGROUND_SLUG,
            "seed": 42,
        }
        expected_scene_key = "character"
        expected_scene_value = entity_slug

    r = client.post("/api/build", json=build_payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sdxl" in body
    assert body["sdxl"].get("positive")
    assert body["scene"][expected_scene_key] == expected_scene_value
    assert body["scene"]["style"] == TEST_STYLE_SLUG
    assert body["scene"]["animation"] == TEST_ANIMATION_SLUG


def test_sprite_build_positive_prompt_contract(client):
    r = client.post("/api/build", json=_BUILD_PAYLOAD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"]["views"] == list(TEST_ANIMATION_FRAMINGS)
    positive = body["sdxl"]["positive"]
    assert "1girl" in positive
    assert "brown hair" in positive
    assert "sailor collar" in positive
    assert "pleated skirt" in positive
    assert "ultra-detailed" in positive
    assert "4k" in positive
    assert TEST_SIDE_VIEW_KEY in positive
    for tag in TEST_ANIMATION_TAGS:
        assert tag in positive, tag
    for tag in TEST_BACKGROUND_SCENE_TAGS:
        assert tag in positive, tag


def test_workflow_main_positive_includes_character_tags(client):
    from webapp.comfyui.workflow import build_result_to_make_lab

    r = client.post("/api/build", json=_BUILD_PAYLOAD)
    assert r.status_code == 200, r.text
    build = r.json()
    wf = build_result_to_make_lab(build)
    text = wf["prompt_main_positive"]["inputs"]["text"]
    assert "1girl" in text
    assert text == build["sdxl"]["positive"]


def test_seeded_style_canonical_fields(client):
    rows = client.get("/api/styles").json()
    style = next(r for r in rows if r["slug"] == TEST_STYLE_SLUG)
    assert style["name"] == TEST_STYLE_DISPLAY_NAME
    assert style["prefix"] == TEST_STYLE_PREFIX
    lora = style.get("lora")
    assert lora is not None
    assert lora["filename"] == E7_SPRITES_FILENAME
    assert lora["trigger"] == E7_SPRITES_TRIGGER
    assert lora["version_id"] == E7_SPRITES_VERSION_ID
    assert lora["download_url"] == E7_SPRITES_DOWNLOAD_URL
    assert lora["download_fallback_url"] == E7_SPRITES_DOWNLOAD_FALLBACK_URL


def test_seeded_background_canonical_fields(client):
    """Default test background matches the canonical fixture in test_seed."""
    rows = client.get("/api/backgrounds").json()
    bg = next(r for r in rows if r["key"] == TEST_BACKGROUND_SLUG)
    assert bg["display_name"] == TEST_BACKGROUND_DISPLAY_NAME
    assert bg["tags"] == list(TEST_BACKGROUND_SCENE_TAGS)


def test_seeded_character_canonical_fields(client):
    """Default test character matches the canonical fixture in test_seed."""
    rows = client.get("/api/characters").json()
    char = next(r for r in rows if r["slug"] == TEST_CHARACTER_SLUG)

    assert char["name_tag"] == TEST_CHARACTER_NAME_TAG
    assert char["identity_core"] == list(TEST_CHARACTER_IDENTITY_CORE)
    for key, value in TEST_CHARACTER_PHYSICAL.items():
        assert char.get(key) == value, key
    for key, value in TEST_CHARACTER_OUTFIT.items():
        assert char.get(key) == value, key


def test_character_edit_page_shows_api_lora(client):
    filename = "integration-test-lora.safetensors"
    trigger = "integration_test_char"
    put = client.put(
        f"/api/characters/{TEST_CHARACTER_SLUG}",
        json={
            "slug": TEST_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "name": "Integration Test LoRA",
                "trigger": trigger,
            },
        },
    )
    assert put.status_code == 200, put.text
    page = client.get(f"/characters/{TEST_CHARACTER_SLUG}")
    assert page.status_code == 200
    assert filename in page.text
    assert trigger in page.text
