"""Qwen Image 2512 Make Lab pipeline composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.pipeline_builder import build_pipeline
from webapp.comfyui.qwen_make.workflow import (
    patch_qwen_make_workflow,
    qwen_make_export_node_id,
    qwen_make_patch_roles,
)


def test_build_qwen_make_pipeline():
    built = build_pipeline("qwen_make")
    assert built.pipeline == "qwen_make"
    assert "ksampler" in built.workflow
    assert "export_image" in built.workflow
    assert built.workflow["export_image"]["class_type"] == "ComfySpritesExportImage"
    assert built.workflow["preview_save"]["class_type"] == "PreviewImage"
    assert built.workflow["preview_save"]["inputs"]["images"] == ["export_image", 0]
    assert built.workflow["positive"]["class_type"] == "CLIPTextEncode"
    assert built.workflow["diffusion_model"]["class_type"] == "UNETLoader"
    assert built.workflow["ksampler"]["_meta"]["title"] == "Main Sampling"


def test_patch_qwen_make_workflow_rewires_sampling():
    roles = qwen_make_patch_roles()
    wf = patch_qwen_make_workflow(
        positive="hello qwen",
        negative="bad",
        width=1664,
        height=928,
        seed=42,
        steps=6,
        cfg=1.25,
        shift=2.5,
        model_paths={
            "qwen_image_2512_fp8_e4m3fn.safetensors": "models/unet.safetensors",
            "qwen_2.5_vl_7b_fp8_scaled.safetensors": "clip/qwen.safetensors",
            "qwen_image_vae.safetensors": "vae/qwen.safetensors",
            "Qwen-Image-2512-Lightning-4steps-V1.0-fp32.safetensors": "loras/lightning.safetensors",
        },
    )
    assert wf[roles["positive"]]["inputs"]["text"] == "hello qwen"
    assert wf[roles["negative"]]["inputs"]["text"] == "bad"
    assert wf[roles["empty_latent"]]["inputs"]["width"] == 1664
    assert wf[roles["empty_latent"]]["inputs"]["height"] == 928
    assert wf[roles["ksampler"]]["inputs"]["seed"] == 42
    assert wf[roles["ksampler"]]["inputs"]["steps"] == 6
    assert wf[roles["ksampler"]]["inputs"]["cfg"] == 1.25
    assert wf[roles["model_sampling"]]["inputs"]["shift"] == 2.5
    assert (
        wf[roles["diffusion_model"]]["inputs"]["unet_name"]
        == "models/unet.safetensors"
    )
    assert qwen_make_export_node_id() == "export_image"


def test_patch_qwen_make_workflow_uses_style_unet_filename():
    roles = qwen_make_patch_roles()
    wf = patch_qwen_make_workflow(
        positive="p",
        negative="n",
        width=1328,
        height=1328,
        seed=1,
        unet_filename="custom_qwen_finetune.safetensors",
        model_paths={"custom_qwen_finetune.safetensors": "QWEN/custom.safetensors"},
    )
    assert (
        wf[roles["diffusion_model"]]["inputs"]["unet_name"] == "QWEN/custom.safetensors"
    )
