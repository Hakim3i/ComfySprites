"""Qwen Image Edit pipeline composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.pipeline_builder import build_pipeline
from webapp.comfyui.qwen_edit.workflow import (
    patch_qwen_edit_workflow,
    qwen_edit_patch_roles,
)


def test_build_qwen_edit_pipeline_uses_comfy_lora_loader():
    built = build_pipeline("qwen_edit")
    assert built.pipeline == "qwen_edit"
    assert built.workflow["lora"]["class_type"] == "LoraLoader"
    assert "Power Lora Loader" not in str(built.workflow["lora"])


def test_patch_qwen_edit_workflow_chains_loras():
    roles = qwen_edit_patch_roles()
    wf = patch_qwen_edit_workflow(
        comfy_image_name="source.png",
        qwen_edit_prompt="make the cape red",
        loras=[
            {
                "kind": "qwen_edit",
                "filename": "edit-motion.safetensors",
                "strength": 0.85,
            }
        ],
        seed=7,
        steps=4,
        cfg=1.0,
        shift=3.1,
        image_strength=1.0,
    )
    assert wf[roles["positive"]]["inputs"]["prompt"] == "make the cape red"
    assert wf[roles["negative"]]["inputs"]["prompt"] == "make the cape red"
    assert wf[roles["lora"]]["class_type"] == "LoraLoader"
    assert wf[roles["lora"]]["inputs"]["lora_name"] == "edit-motion.safetensors"
    assert wf[roles["lora"]]["inputs"]["strength_model"] == 0.85
    assert wf[roles["model_sampling"]]["inputs"]["model"] == [roles["lora"], 0]


def test_patch_qwen_edit_workflow_resolves_random_seed():
    roles = qwen_edit_patch_roles()
    wf = patch_qwen_edit_workflow(
        comfy_image_name="source.png",
        seed=-1,
    )
    assert wf[roles["ksampler"]]["inputs"]["seed"] >= 0


def test_patch_qwen_edit_workflow_chains_multiple_loras():
    roles = qwen_edit_patch_roles()
    wf = patch_qwen_edit_workflow(
        comfy_image_name="source.png",
        loras=[
            {
                "kind": "qwen_edit",
                "filename": "edit-a.safetensors",
                "strength": 0.7,
            },
            {
                "kind": "qwen_edit",
                "filename": "edit-b.safetensors",
                "strength": 0.5,
            },
        ],
    )
    stack_a = "qwen_edit_lora:0"
    assert stack_a in wf
    assert wf[stack_a]["class_type"] == "LoraLoader"
    assert wf[stack_a]["inputs"]["lora_name"] == "edit-a.safetensors"
    assert wf[roles["lora"]]["inputs"]["lora_name"] == "edit-b.safetensors"
    assert wf[roles["model_sampling"]]["inputs"]["model"] == [roles["lora"], 0]


def test_patch_qwen_edit_workflow_skips_lora_node_when_empty():
    roles = qwen_edit_patch_roles()
    wf = patch_qwen_edit_workflow(
        comfy_image_name="source.png",
        loras=[],
        build={"qwen_edit": {"loras": []}},
    )
    assert roles["lora"] not in wf
    assert wf[roles["model_sampling"]]["inputs"]["model"] == [
        roles["lightning_lora"],
        0,
    ]
