"""Workflow patching for Make Lab."""

from __future__ import annotations

import pytest

from webapp.comfyui.outputs import batch_storage_id
from webapp.comfyui.workflow import (
    MAKE_LAB_SAVE_NODE_ID,
    build_result_to_make_lab,
    comfyui_sampler_name,
    load_make_lab_workflow,
    patch_make_lab,
    make_lab_loras_from_build,
    prepare_make_lab_workflow,
    validate_make_lab_workflow,
)


def test_comfyui_sampler_name_mapping():
    assert comfyui_sampler_name("Euler a") == "euler_ancestral"
    assert comfyui_sampler_name("DPM++ 2M") == "dpmpp_2m"
    assert comfyui_sampler_name("DPM++ SDE") == "dpmpp_sde"
    assert comfyui_sampler_name("DPM++ SDE Karras") == "dpmpp_sde"
    assert comfyui_sampler_name("UniPC") == "uni_pc"


def test_all_style_sampler_hints_map_to_comfyui_ids():
    """Every Make dropdown hint must translate to a ComfyUI sampler_name."""
    from webapp.services.catalog.style_defaults import sampler_hints

    for label in sampler_hints():
        comfy = comfyui_sampler_name(label)
        assert " " not in comfy
        assert "++" not in comfy
        assert all(c.islower() or c in "_0123456789" for c in comfy)


def test_load_make_lab_validates_titles():
    wf = load_make_lab_workflow()
    validate_make_lab_workflow(wf)
    assert MAKE_LAB_SAVE_NODE_ID in wf
    assert wf[MAKE_LAB_SAVE_NODE_ID]["class_type"] == "PreviewImage"
    assert wf[MAKE_LAB_SAVE_NODE_ID]["_meta"]["title"] == "Preview Image"
    assert wf["export_image"]["class_type"] == "ComfySpritesExportImage"
    assert wf[MAKE_LAB_SAVE_NODE_ID]["inputs"]["images"] == ["export_image", 0]


def test_patch_make_lab_nodes():
    wf = prepare_make_lab_workflow()
    patch_make_lab(
        wf,
        positive="pos tags",
        negative="neg tags",
        refine_positive="refine pos",
        refine_negative="refine neg",
        ckpt_name="model.safetensors",
        width=1024,
        height=768,
        seed=42,
        steps=30,
        cfg=6.5,
        sampler="Euler a",
        scheduler="normal",
    )
    assert wf["checkpoint_main"]["inputs"]["ckpt_name"] == "model.safetensors"
    assert wf["latent_empty"]["inputs"]["width"] == 1024
    assert wf["prompt_main_positive"]["inputs"]["text"] == "pos tags"
    assert wf["prompt_refine_positive"]["inputs"]["text"] == "refine pos"
    assert wf["prompt_refine_negative"]["inputs"]["text"] == "refine neg"
    assert wf["sampler_main"]["inputs"]["sampler_name"] == "euler_ancestral"
    assert wf["sampler_main"]["inputs"]["steps"] == 30
    assert wf["sampler_refine"]["inputs"]["steps"] == 15
    assert wf["sampler_refine"]["inputs"]["denoise"] == 0.35
    assert wf["upscale_scale"]["inputs"]["width"] == 1536
    assert wf["upscale_restore"]["inputs"]["width"] == 1024
    assert wf["upscale_restore"]["inputs"]["height"] == 768
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]


def test_patch_make_lab_batch_size():
    wf = prepare_make_lab_workflow()
    patch_make_lab(
        wf,
        positive="p",
        negative="n",
        ckpt_name="m.safetensors",
        width=512,
        height=512,
        seed=1,
        steps=20,
        cfg=7,
        sampler="Euler",
        scheduler="normal",
        batch_size=4,
    )
    assert wf["latent_empty"]["inputs"]["batch_size"] == 4


def test_build_result_to_make_lab():
    build = {
        "scene": {"seed": 99},
        "sdxl": {
            "positive": "hello",
            "negative": "bad",
            "width": 512,
            "height": 512,
            "checkpoint": {
                "filename": "test.ckpt",
                "sampler": "Euler",
                "scheduler": "normal",
                "steps": 20,
                "cfg_scale": 7,
            },
        },
    }
    wf = build_result_to_make_lab(build)
    assert wf["prompt_main_positive"]["inputs"]["text"] == "hello"
    assert wf["checkpoint_main"]["inputs"]["ckpt_name"] == "test.ckpt"
    assert wf["checkpoint_main"]["class_type"] == "CheckpointLoaderSimple"
    assert "downloader" not in wf
    assert wf["sampler_main"]["inputs"]["seed"] == 99
    assert wf["sampler_main"]["inputs"]["sampler_name"] == "euler"


def test_build_result_replaces_seed_minus_one():
    build = {
        "scene": {"seed": -1},
        "request": {},
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {
                "filename": "test.ckpt",
                "sampler": "Euler",
                "scheduler": "normal",
                "steps": 20,
                "cfg_scale": 7,
            },
        },
    }
    wf = build_result_to_make_lab(build)
    seed = wf["sampler_main"]["inputs"]["seed"]
    assert isinstance(seed, int)
    assert seed >= 0
    assert wf["sampler_refine"]["inputs"]["seed"] == seed + 20000


def test_build_result_ksampler_uses_style_when_request_omits_sampler():
    """Make does not send sampler/scheduler; style checkpoint must drive KSampler."""
    build = {
        "request": {},
        "scene": {"seed": 12},
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {
                "filename": "test.ckpt",
                "sampler": "DPM++ 2M",
                "scheduler": "karras",
                "steps": 25,
                "cfg_scale": 5,
            },
        },
    }
    wf = build_result_to_make_lab(build)
    assert wf["sampler_main"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert wf["sampler_main"]["inputs"]["scheduler"] == "karras"


def test_build_result_request_sampler_overrides_checkpoint():
    build = {
        "request": {"sampler": "Euler a", "scheduler": "normal"},
        "scene": {"seed": 3},
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {
                "filename": "test.ckpt",
                "sampler": "DPM++ 2M",
                "scheduler": "karras",
                "steps": 25,
                "cfg_scale": 5,
            },
        },
    }
    wf = build_result_to_make_lab(build)
    assert wf["sampler_main"]["inputs"]["sampler_name"] == "euler_ancestral"
    assert wf["sampler_main"]["inputs"]["scheduler"] == "normal"


def test_build_result_to_make_lab_batch_size():
    build = {
        "scene": {"seed": 1},
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {"filename": "test.ckpt", "sampler": "Euler"},
        },
    }
    wf = build_result_to_make_lab(build, batch_size=3)
    assert wf["latent_empty"]["inputs"]["batch_size"] == 3


def test_batch_storage_id_single_and_multi():
    assert batch_storage_id("pid-1", 0, batch_count=1) == "pid-1"
    assert batch_storage_id("pid-1", 0, batch_count=3) == "pid-1_0"
    assert batch_storage_id("pid-1", 2, batch_count=3) == "pid-1_2"


def test_build_result_requires_checkpoint():
    with pytest.raises(ValueError, match="checkpoint"):
        build_result_to_make_lab({"sdxl": {"checkpoint": {}}})


def test_make_lab_loras_from_build_order():
    sdxl = {
        "loras": [
            {"kind": "animation", "filename": "act.safetensors", "strength": 0.8},
            {"kind": "character", "filename": "char.safetensors", "strength": 1.0},
            {"kind": "style", "filename": "style.safetensors", "strength": 0.5},
        ],
    }
    ordered = make_lab_loras_from_build(sdxl)
    assert [x["kind"] for x in ordered] == ["style", "character", "animation"]
    assert [x["filename"] for x in ordered] == [
        "style.safetensors",
        "char.safetensors",
        "act.safetensors",
    ]


def test_patch_make_lab_loras_slots():
    wf = load_make_lab_workflow()
    patch_make_lab(
        wf,
        positive="p",
        negative="n",
        ckpt_name="m.safetensors",
        width=512,
        height=512,
        seed=1,
        steps=20,
        cfg=7,
        sampler="Euler",
        scheduler="normal",
        loras=[
            {"kind": "style", "filename": "style.safetensors", "strength": 0.6},
            {"kind": "character", "filename": "char.safetensors", "strength": 1.0},
        ],
    )
    assert wf["lora_stack:0"]["class_type"] == "LoraLoader"
    assert wf["lora_stack:0"]["inputs"]["lora_name"] == "style.safetensors"
    assert wf["lora_stack:0"]["inputs"]["strength_model"] == 0.6
    assert wf["lora_main"]["inputs"]["lora_name"] == "char.safetensors"
    assert wf["sampler_main"]["inputs"]["model"] == ["lora_main", 0]


def test_build_result_to_make_lab_wires_loras():
    build = {
        "scene": {"seed": 1},
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {"filename": "test.ckpt", "sampler": "Euler"},
            "loras": [
                {"kind": "character", "filename": "c.safetensors", "strength": 1.0},
                {"kind": "animation", "filename": "a.safetensors", "strength": 0.9},
            ],
        },
    }
    wf = build_result_to_make_lab(build)
    assert wf["lora_stack:0"]["inputs"]["lora_name"] == "c.safetensors"
    assert wf["lora_main"]["inputs"]["lora_name"] == "a.safetensors"
