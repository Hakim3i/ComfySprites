"""Asset inventory vs ComfyUI installed models."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.asset_inventory import assets_ready, missing_assets


def _build():
    return {
        "sdxl": {
            "checkpoint": {"filename": "base.safetensors"},
            "loras": [{"kind": "style", "filename": "style.safetensors"}],
        },
        "controlnet": {
            "openpose": {"image_path": "/uploads/pose.png", "strength": 1.0},
        },
        "request": {"upscale_timing": "disabled"},
    }


@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=["base.safetensors"])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
def test_missing_assets_detects_loras_and_controlnets(_cn, _loras, _ckpt, _sam, _ult, _up):
    missing = missing_assets(_build(), "http://127.0.0.1:8188")
    assert not missing["checkpoints"]
    assert missing["loras"][0]["filename"] == "style.safetensors"
    assert missing["controlnets"]


@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=["base.safetensors"])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=["style.safetensors"])
@patch(
    "webapp.comfyui.asset_inventory.list_controlnets",
    return_value=["noobaiXLControlnet_openposeModel.safetensors"],
)
def test_assets_ready_when_all_installed(_cn, _loras, _ckpt, _sam, _ult, _up):
    assert assets_ready(_build(), "http://127.0.0.1:8188")


def _build_with_face_detailer():
    return {
        "sdxl": {
            "checkpoint": {"filename": "base.safetensors"},
            "loras": [],
        },
        "request": {
            "detailers": ["face"],
            "detailer_timing": "before",
            "upscale_timing": "disabled",
        },
    }


@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=["base.safetensors"])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
def test_missing_assets_detects_detailer_models(_cn, _loras, _ckpt, _sam, _ult, _up):
    missing = missing_assets(_build_with_face_detailer(), "http://127.0.0.1:8188")
    rels = {row["relative_path"] for row in missing["detailers"]}
    assert "bbox/face_yolov9c.pt" in rels
    assert "sam_vit_b_01ec64.pth" in rels


@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch(
    "webapp.comfyui.asset_inventory.list_ultralytics_models",
    return_value=["bbox\\face_yolov9c.pt"],
)
@patch(
    "webapp.comfyui.asset_inventory.list_sams_models",
    return_value=["sam_vit_b_01ec64.pth"],
)
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=["base.safetensors"])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
def test_assets_ready_accepts_windows_ultralytics_paths(_cn, _loras, _ckpt, _sam, _ult, _up):
    assert assets_ready(_build_with_face_detailer(), "http://127.0.0.1:8188")
