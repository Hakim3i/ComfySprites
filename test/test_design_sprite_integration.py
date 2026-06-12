"""Integration tests against canonical shipped defaults."""

from __future__ import annotations

import pytest

from webapp.db.animations_defaults import load_animation_defaults
from webapp.db.backgrounds_defaults import load_background_defaults
from webapp.db.characters_defaults import load_character_defaults
from webapp.db.models import ENTITY_BACKGROUND, ENTITY_CHARACTER, ENTITY_OBJECT
from webapp.db.seed_constants import (
    DEFAULT_ANIMATION_SLUG,
    DEFAULT_BACKGROUND_SLUG,
    DEFAULT_CHARACTER_SLUG,
    DEFAULT_OBJECT_SLUG,
    DEFAULT_SIDE_VIEW_KEY,
    DEFAULT_STYLE_SLUG,
)
from webapp.db.styles_defaults import load_style_defaults

_ASUNA = next(c for c in load_character_defaults() if c.slug == DEFAULT_CHARACTER_SLUG)
_STANDING_IDLE = next(
    a for a in load_animation_defaults() if a.slug == DEFAULT_ANIMATION_SLUG
)
_GREY_BG = next(b for b in load_background_defaults() if b.slug == DEFAULT_BACKGROUND_SLUG)
_WAI_STYLE = next(s for s in load_style_defaults() if s.slug == DEFAULT_STYLE_SLUG)

DESIGN_SPRITE_TYPES = (
    ("character", ENTITY_CHARACTER, DEFAULT_CHARACTER_SLUG),
    ("object", ENTITY_OBJECT, DEFAULT_OBJECT_SLUG),
    ("background", ENTITY_BACKGROUND, DEFAULT_BACKGROUND_SLUG),
)

_BUILD_PAYLOAD = {
    "character": DEFAULT_CHARACTER_SLUG,
    "subject_type": "character",
    "style": DEFAULT_STYLE_SLUG,
    "animation": DEFAULT_ANIMATION_SLUG,
    "location": DEFAULT_BACKGROUND_SLUG,
    "seed": 88,
}


@pytest.mark.parametrize("label,entity_type,entity_slug", DESIGN_SPRITE_TYPES)
def test_seeded_design_sprite_builds(client, label, entity_type, entity_slug):
    if entity_type == ENTITY_BACKGROUND:
        build_payload = {
            "character": DEFAULT_CHARACTER_SLUG,
            "style": DEFAULT_STYLE_SLUG,
            "animation": DEFAULT_ANIMATION_SLUG,
            "location": entity_slug,
            "seed": 42,
        }
        expected_scene_key = "location"
        expected_scene_value = entity_slug
    else:
        build_payload = {
            "character": entity_slug,
            "style": DEFAULT_STYLE_SLUG,
            "animation": DEFAULT_ANIMATION_SLUG,
            "location": DEFAULT_BACKGROUND_SLUG,
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
    assert body["scene"]["style"] == DEFAULT_STYLE_SLUG
    assert body["scene"]["animation"] == DEFAULT_ANIMATION_SLUG


def test_sprite_build_positive_prompt_contract(client):
    r = client.post("/api/build", json=_BUILD_PAYLOAD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"]["views"] == list(_STANDING_IDLE.framings)
    positive = body["sdxl"]["positive"]
    assert "1girl" in positive
    assert "brown hair" in positive
    assert "knights of blood uniform (sao)" in positive
    assert "ultra-detailed" in positive
    assert "4k" in positive
    assert DEFAULT_SIDE_VIEW_KEY in positive
    for tag in _STANDING_IDLE.tags:
        assert tag in positive, tag
    for tag in _GREY_BG.tags:
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
    style = next(r for r in rows if r["slug"] == DEFAULT_STYLE_SLUG)
    assert style["name"] == _WAI_STYLE.display_name
    assert style["prefix"] == _WAI_STYLE.prefix
    assert style.get("lora") is None


def test_seeded_background_canonical_fields(client):
    rows = client.get("/api/backgrounds").json()
    bg = next(r for r in rows if r["key"] == DEFAULT_BACKGROUND_SLUG)
    assert bg["display_name"] == _GREY_BG.display_name
    assert bg["tags"] == list(_GREY_BG.tags)


def test_seeded_character_canonical_fields(client):
    rows = client.get("/api/characters").json()
    char = next(r for r in rows if r["slug"] == DEFAULT_CHARACTER_SLUG)

    assert char["name_tag"] == _ASUNA.name_tag
    assert char["identity_core"] == list(_ASUNA.identity_core)
    for key in (
        "hair_color",
        "hair_length",
        "hair_style",
        "eye_color",
        "age_band",
        "skin_tone",
        "height",
        "breast_size",
        "body_type",
        "muscle",
        "hip_size",
        "butt_size",
        "thigh_type",
    ):
        assert char.get(key) == _ASUNA.physical.get(key), key
    assert char.get("outfit_upper") == list(_ASUNA.outfit_upper)
    assert char.get("outfit_lower") == list(_ASUNA.outfit_lower)
    assert char.get("outfit_extra") == list(_ASUNA.outfit_extra)


def test_character_edit_page_shows_api_lora(client):
    filename = "integration-test-lora.safetensors"
    trigger = "integration_test_char"
    put = client.put(
        f"/api/characters/{DEFAULT_CHARACTER_SLUG}",
        json={
            "slug": DEFAULT_CHARACTER_SLUG,
            "lora": {
                "filename": filename,
                "name": "Integration Test LoRA",
                "trigger": trigger,
            },
        },
    )
    assert put.status_code == 200, put.text
    page = client.get(f"/characters/{DEFAULT_CHARACTER_SLUG}")
    assert page.status_code == 200
    assert filename in page.text
    assert trigger in page.text
