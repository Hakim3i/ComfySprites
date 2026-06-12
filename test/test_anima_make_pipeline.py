"""Anima Make Lab pipeline composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.anima_make.workflow import (
    anima_make_export_node_id,
    anima_make_patch_roles,
    patch_anima_make_workflow,
)
from webapp.comfyui.pipeline_builder import build_pipeline


def test_build_anima_make_pipeline():
    built = build_pipeline("anima_make")
    assert built.pipeline == "anima_make"
    assert built.workflow["ksampler"]["class_type"] == "KSampler"
    assert built.workflow["diffusion_model"]["class_type"] == "UNETLoader"
    assert built.workflow["anima_clip"]["inputs"]["type"] == "stable_diffusion"
    assert built.workflow["empty_latent"]["class_type"] == "EmptyLatentImage"


def test_patch_anima_make_workflow_sets_models_and_sampling():
    roles = anima_make_patch_roles()
    wf = patch_anima_make_workflow(
        positive="hello anima",
        negative="bad",
        width=1024,
        height=768,
        seed=42,
        steps=40,
        cfg=5.0,
        sampler="er_sde",
        scheduler="normal",
        model_paths={
            "anima-base-v1.0.safetensors": "models/anima.safetensors",
            "qwen_3_06b_base.safetensors": "clip/anima.safetensors",
            "qwen_image_vae.safetensors": "vae/anima.safetensors",
        },
    )
    assert wf[roles["positive"]]["inputs"]["text"] == "hello anima"
    assert wf[roles["ksampler"]]["inputs"]["sampler_name"] == "er_sde"
    assert wf[roles["diffusion_model"]]["inputs"]["unet_name"] == "models/anima.safetensors"
    assert anima_make_export_node_id() == "export_image"


def test_patch_anima_make_workflow_chains_style_loras():
    roles = anima_make_patch_roles()
    wf = patch_anima_make_workflow(
        positive="p",
        negative="n",
        width=1024,
        height=1024,
        seed=1,
        style_loras=[
            {
                "kind": "style",
                "filename": "Epic_Seven_Sprites_Anima.safetensors",
                "strength": 1.0,
            }
        ],
        model_paths={
            "Epic_Seven_Sprites_Anima.safetensors": "loras/epic_anima.safetensors",
        },
    )
    style_node = wf["anima_make_style_lora"]
    assert style_node["class_type"] == "LoraLoaderModelOnly"
    assert style_node["inputs"]["model"] == [roles["diffusion_model"], 0]
    assert wf[roles["ksampler"]]["inputs"]["model"] == ["anima_make_style_lora", 0]
