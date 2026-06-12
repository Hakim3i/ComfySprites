"""Wan 2.2 pipeline graph composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.pipeline_builder import build_pipeline
from webapp.comfyui.wan22.workflow import patch_wan22_workflow
from webapp.db.models import Style
from webapp.services.ltx.render import render_wan_negative


def test_build_wan22_pipeline():
    built = build_pipeline("wan22")
    wf = built.workflow
    assert "wan_i2v" in wf
    assert "unet_high" in wf
    assert "unet_low" in wf
    assert "save_video" in wf
    assert wf["wan_i2v"]["class_type"] == "WanImageToVideo"


def test_patch_wan22_workflow_i2v_only():
    build = {
        "wan": {
            "positive": "A character walks forward.",
            "negative": "blurry",
            "loras": [],
        }
    }
    wf = patch_wan22_workflow(
        comfy_image_name="source.png",
        model="wan22_kj",
        width=832,
        height=1216,
        length_seconds=5,
        fps=16,
        seed=42,
        cfg=1.0,
        steps=4,
        shift=5.0,
        loras=[],
        build=build,
        positive_text="A character walks forward.",
        negative_text="blurry",
    )
    assert wf["wan_i2v"]["class_type"] == "WanImageToVideo"
    assert "end_image" not in wf["wan_i2v"]["inputs"]
    assert "load_end_image" not in wf
    assert "HIGH" in wf["unet_high"]["inputs"]["unet_name"].upper()
    assert "LOW" in wf["unet_low"]["inputs"]["unet_name"].upper()
    assert wf["wan_i2v"]["inputs"]["width"] == 832
    assert wf["wan_i2v"]["inputs"]["height"] == 1216
    assert wf["wan_i2v"]["inputs"]["length"] == 5 * 16 + 1
    assert "get_image_size" not in wf
    assert wf["sampler_high"]["inputs"]["steps"] == 4
    assert wf["sampler_high"]["inputs"]["end_at_step"] == 2
    assert wf["sampler_low"]["inputs"]["start_at_step"] == 2


def test_patch_wan22_workflow_with_fflf():
    build = {
        "wan": {
            "positive": "Morph between poses.",
            "negative": "blurry",
            "loras": [],
        }
    }
    wf = patch_wan22_workflow(
        comfy_image_name="source.png",
        model="wan22_kj",
        width=832,
        height=1216,
        length_seconds=5,
        fps=16,
        seed=42,
        cfg=1.0,
        steps=4,
        shift=5.0,
        loras=[],
        build=build,
        positive_text="Morph between poses.",
        negative_text="blurry",
        end_comfy_image_name="end.png",
    )
    assert wf["wan_i2v"]["class_type"] == "WanFirstLastFrameToVideo"
    assert wf["wan_i2v"]["inputs"]["end_image"] == ["load_end_image", 0]
    assert wf["load_end_image"]["inputs"]["image"] == "end.png"


def test_patch_wan22_workflow_uses_builtin_lora_loader():
    build = {"wan": {"positive": "", "negative": "", "loras": []}}
    loras = [
        {
            "kind": "animation_wan_low",
            "filename": "test_low.safetensors",
            "strength": 0.8,
        }
    ]
    wf = patch_wan22_workflow(
        comfy_image_name="source.png",
        model="wan22_kj",
        width=832,
        height=1216,
        length_seconds=5,
        fps=16,
        seed=42,
        cfg=1.0,
        steps=4,
        shift=5.0,
        loras=loras,
        build=build,
    )
    assert wf["lora_low"]["class_type"] == "LoraLoaderModelOnly"
    assert wf["lora_low"]["inputs"]["lora_name"] == "test_low.safetensors"
    assert wf["model_sampling_low"]["inputs"]["model"] == ["lora_low", 0]
    assert not any(
        isinstance(node, dict)
        and node.get("class_type") == "Power Lora Loader (rgthree)"
        for node in wf.values()
    )


def test_render_wan_negative_uses_style_field():
    assert render_wan_negative(style=Style(wan_negative="custom neg")) == "custom neg"
    fallback = render_wan_negative(style=Style())
    assert "blurry" in fallback
    assert "watermark" in fallback
