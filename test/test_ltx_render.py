"""LTX caption and negative composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db.models import Animation, DesignEntity, Lora, Style
from webapp.services.ltx.render import render_ltx_block, render_ltx_caption


def test_render_ltx_caption_orders_segments():
    style = Style(slug="s1", display_name="S1", video_register="Lifelike cinematic")
    character = DesignEntity(
        slug="c1",
        display_name="Miyu",
        video_prompt="young woman in a red school uniform",
    )
    location = DesignEntity(
        slug="loc1",
        display_name="Classroom",
        video_prompt="bright classroom",
    )
    ltx_lora = Lora(
        kind="animation_ltx",
        name="walk",
        filename="walk.safetensors",
        caption_trigger="She walks forward slowly.",
    )
    animation = Animation(
        slug="act1",
        menu_name="Walk",
        video_prompt="She steps toward the camera.",
        ltx_lora=ltx_lora,
    )
    caption = render_ltx_caption(
        style=style,
        character=character,
        location=location,
        animation=animation,
    )
    assert caption.startswith("Lifelike cinematic")
    assert "Video of Miyu" in caption
    assert "walk forward" in caption.lower() or "walks forward" in caption.lower()
    assert caption.endswith(".")


def test_render_ltx_negative_blocks():
    style = Style(
        slug="s1",
        display_name="S1",
        ltx_video_negative="blurry, still image",
        ltx_audio_negative="wind noise",
    )
    block = render_ltx_block(style=style, character=None, location=None, animation=None)
    assert block["negative"].startswith("#Video")
    assert "blurry" in block["negative"]
    assert "#Audio" in block["negative"]
    assert "wind noise" in block["negative"]
