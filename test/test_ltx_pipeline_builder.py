"""LTX Studio pipeline graph composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.pipeline_builder import build_pipeline
from webapp.comfyui.ltx_studio.workflow import (
    load_ltx_studio_workflow,
    patch_ltx_studio_workflow,
)


def test_build_ltx_studio_pipeline():
    built = build_pipeline("ltx_studio")
    assert "positive" in built.workflow
    assert "negative" in built.workflow
    assert "export_video" in built.workflow
    assert built.workflow["positive"]["class_type"] == "CLIPTextEncode"


def test_patch_ltx_studio_workflow_sets_prompts():
    build = {
        "ltx": {
            "caption": "Test caption.",
            "negative": "#Video\nbad\n\n#Audio\nnoise",
            "loras": [],
        }
    }
    wf = patch_ltx_studio_workflow(
        comfy_image_name="source.png",
        model="ltx23_eros",
        width=832,
        height=1216,
        length_seconds=5,
        fps=24,
        seed=42,
        image_strength=0.95,
        audio_volume=100,
        cfg=1.0,
        loras=[],
        build=build,
        use_sulphur_experimental_lora=False,
    )
    roles = load_ltx_studio_workflow()
    assert roles  # smoke: template loads
    nodes = wf
    positive_id = "positive"
    assert "Test caption." in nodes[positive_id]["inputs"]["text"]
    assert not any(
        isinstance(node, dict) and node.get("class_type") == "CoomfyEnsureLTXLoras"
        for node in wf.values()
    )
