"""Make Lab ControlNet workflow injection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from webapp.comfyui.make_lab.controlnet import (
    apply_controlnet_stage,
    controlnet_settings_from_request,
)
from webapp.comfyui.workflow import build_result_to_make_lab
from webapp.comfyui.workflow_builder import registry_nodes


def _minimal_build(controlnet: dict | None = None) -> dict:
    build = {
        "sdxl": {
            "checkpoint": {"filename": "model.safetensors", "steps": 20, "cfg_scale": 7},
            "positive": "1girl",
            "negative": "bad",
            "width": 512,
            "height": 512,
            "loras": [],
        },
        "scene": {"seed": 1},
        "request": {},
    }
    if controlnet:
        build["controlnet"] = controlnet
    return build


def test_controlnet_disabled_no_nodes():
    build = _minimal_build()
    wf = build_result_to_make_lab(build)
    sampler = registry_nodes()["sampler"]
    assert wf[sampler]["inputs"]["positive"][0] == registry_nodes()["positive"]
    assert not any(k.startswith("controlnet:") for k in wf)


def test_controlnet_enabled_rewires_sampler_positive():
    build = _minimal_build(
        {
            "openpose": {
                "image_path": "/uploads/test.png",
                "strength": 0.8,
                "start_percent": 0.0,
                "end_percent": 1.0,
            }
        }
    )
    with patch(
        "webapp.comfyui.make_lab.controlnet.upload_image_bytes",
        return_value="uploaded.png",
    ), patch(
        "webapp.comfyui.make_lab.controlnet._upload_path_to_local",
    ) as local:
        from pathlib import Path

        fake = Path(__file__)
        local.return_value = fake
        with patch.object(Path, "is_file", return_value=True), patch.object(
            Path, "read_bytes", return_value=b"png"
        ):
            wf = build_result_to_make_lab(build)
    sampler = registry_nodes()["sampler"]
    pos = wf[sampler]["inputs"]["positive"]
    neg = wf[sampler]["inputs"]["negative"]
    assert pos[0].startswith("controlnet:openpose:")
    assert pos[0].endswith(":apply")
    assert pos[1] == 0
    assert neg == [pos[0], 1]
    apply_id = pos[0]
    assert wf[apply_id]["inputs"]["image"] == [apply_id.replace(":apply", ":load"), 0]
    assert not any(k.endswith(":pre") for k in wf)
    loader_id = apply_id.replace(":apply", ":loader")
    assert wf[loader_id]["class_type"] == "ControlNetLoader"


def test_controlnet_settings_from_build():
    cfg = controlnet_settings_from_request(
        None,
        _minimal_build({"canny": {"image_path": "/uploads/x.png", "strength": 1.0}}),
    )
    assert cfg and "canny" in cfg
