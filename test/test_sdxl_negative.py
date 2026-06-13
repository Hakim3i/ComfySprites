"""SDXL negative composition from style and entity rows."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db.models import ENTITY_BACKGROUND, Animation, DesignEntity, Style
from webapp.services.prompt.negatives import negative_tags, negative_prose
from webapp.services.sdxl.payload import Scene
from webapp.services.sdxl.render import _render_sdxl


def test_negative_tags_splits_commas_and_newlines():
    assert negative_tags("bad anatomy, blurry\nwatermark") == [
        "bad anatomy",
        "blurry",
        "watermark",
    ]


def test_negative_prose_joins_entity_text():
    character = DesignEntity(slug="c1", display_name="C1", negative="extra fingers")
    animation = Animation(slug="a1", menu_name="A1", negative="static pose")
    assert negative_prose(character, None, animation) == "extra fingers, static pose"


def test_render_sdxl_merges_entity_negative_segments():
    style = Style(
        slug="s1",
        display_name="S1",
        filename="base.safetensors",
        width=832,
        height=1216,
        negative="lowres, worst quality",
    )
    character = DesignEntity(
        slug="c1",
        display_name="C1",
        identity_core=["1girl"],
        negative="extra limbs",
    )
    location = DesignEntity(
        slug="loc1",
        display_name="Loc",
        entity_type=ENTITY_BACKGROUND,
        scene_tags=["classroom"],
        negative="outdoors",
    )
    animation = Animation(
        slug="act1",
        menu_name="Idle",
        tags=["standing"],
        negative="standing",
    )
    scene = Scene(
        seed=1,
        character=character,
        location=location,
        animation=animation,
        style=style,
    )
    result = _render_sdxl(scene)
    sources = {seg["source"] for seg in result["negative_segments"]}
    assert sources == {
        "style",
        "character_negative",
        "location_negative",
        "animation_negative",
    }
    assert "lowres" in result["negative"]
    assert "extra limbs" in result["negative"]
    assert "outdoors" in result["negative"]
    assert "standing" in result["negative"]
    assert "standing" not in result["positive"]
