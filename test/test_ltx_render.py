"""LTX caption and negative composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db.models import Animation, DesignEntity, Lora, Style
from webapp.services.ltx.render import (
    is_animate_video_lora_kind,
    render_ltx_block,
    render_ltx_caption,
    resolve_animate_lora,
)


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


def test_resolve_animate_lora_prefers_style_over_animation():
    style_ltx = Lora(
        kind="style_ltx",
        name="style-motion",
        filename="style-motion.safetensors",
    )
    anim_ltx = Lora(
        kind="animation_ltx",
        name="act-motion",
        filename="act-motion.safetensors",
    )
    style = Style(slug="s1", display_name="S1", ltx_lora=style_ltx)
    animation = Animation(slug="act1", menu_name="Walk", ltx_lora=anim_ltx)
    assert resolve_animate_lora(style, animation, "ltx") is style_ltx


def test_render_ltx_block_includes_style_video_loras():
    style_ltx = Lora(
        kind="style_ltx",
        name="style-motion",
        filename="style-motion.safetensors",
        strength=0.8,
    )
    style = Style(slug="s1", display_name="S1", ltx_lora=style_ltx)
    block = render_ltx_block(style=style, character=None, location=None, animation=None)
    assert len(block["loras"]) == 1
    assert block["loras"][0]["filename"] == "style-motion.safetensors"
    assert block["loras"][0]["kind"] == "style_ltx"


def test_is_animate_video_lora_kind_rejects_still_image_loras():
    assert is_animate_video_lora_kind("ltx")
    assert is_animate_video_lora_kind("style_ltx")
    assert is_animate_video_lora_kind("animation_wan_high")
    assert not is_animate_video_lora_kind("sdxl")
    assert not is_animate_video_lora_kind("style")
    assert not is_animate_video_lora_kind("character")


def test_render_ltx_caption_omits_style_ltx_training_trigger():
    style_ltx = Lora(
        kind="style_ltx",
        name="genshin",
        filename="genshin.safetensors",
        trigger="Genshin_TCG",
        caption_trigger="Genshin_TCG",
    )
    animation = Animation(
        slug="walk",
        menu_name="Walk",
        video_prompt="The character walks in side profile.",
    )
    style = Style(
        slug="epic_seven_sprites_illustrious",
        display_name="E7 Illustrious",
        video_register="Anime video game sprite",
        ltx_lora=style_ltx,
    )
    caption = render_ltx_caption(
        style=style,
        character=None,
        location=None,
        animation=animation,
    )
    assert "Genshin_TCG" not in caption
    assert caption.startswith("Anime video game sprite")
    assert "walks in side profile" in caption


def test_render_ltx_block_includes_style_and_animation_video_loras():
    style_ltx = Lora(
        kind="style_ltx",
        name="genshin",
        filename="genshin.safetensors",
    )
    anim_ltx = Lora(
        kind="animation_ltx",
        name="walk",
        filename="walk.safetensors",
    )
    style = Style(slug="s1", display_name="S1", ltx_lora=style_ltx)
    animation = Animation(slug="act1", menu_name="Walk", ltx_lora=anim_ltx)
    block = render_ltx_block(
        style=style,
        character=None,
        location=None,
        animation=animation,
    )
    kinds = {row["kind"] for row in block["loras"]}
    filenames = {row["filename"] for row in block["loras"]}
    assert kinds == {"style_ltx", "animation_ltx"}
    assert filenames == {"genshin.safetensors", "walk.safetensors"}
