"""Asset inventory vs ComfyUI installed models."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.asset_inventory import (
    assets_ready,
    installed_assets,
    missing_assets,
    resolve_diffusion_model_paths,
)
from webapp.comfyui.asset_manifest import (
    make_lab_checkpoints_manifest,
    make_lab_loras_manifest,
)
from webapp.comfyui.asset_inventory import required_assets
from webapp.comfyui.client import ComfyUIRequestError


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


def _build_with_qwen_make():
    return {
        "qwen_make": {
            "positive": "p",
            "negative": "n",
            "width": 1328,
            "height": 1328,
            "steps": 4,
            "cfg": 1.0,
            "shift": 3.1,
        },
        "sdxl": {
            "checkpoint": {"filename": ""},
            "loras": [
                {"kind": "character", "filename": "char-lora.safetensors"},
                {"kind": "style", "filename": "style-lora.safetensors"},
            ],
        },
        "request": {"refine_enabled": False, "upscale_timing": "disabled"},
    }


def test_qwen_required_assets_uses_style_unet_not_catalog_default():
    build = {
        **_build_with_qwen_make(),
        "sdxl": {
            "checkpoint": {
                "filename": "custom_qwen_finetune.safetensors",
                "download_url": "https://huggingface.co/example/finetune.safetensors",
            },
            "loras": [],
        },
    }
    required = required_assets(build)
    dm_names = {row["filename"] for row in required["diffusion_models"]}
    assert "custom_qwen_finetune.safetensors" in dm_names
    assert "qwen_image_2512_fp8_e4m3fn.safetensors" not in dm_names


def test_qwen_refine_off_manifest_skips_sdxl_inference_loras():
    build = _build_with_qwen_make()
    assert make_lab_loras_manifest(build) == []
    assert make_lab_checkpoints_manifest(build) == []


@patch("webapp.comfyui.asset_inventory.list_vae_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_text_encoders", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_diffusion_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=[])
def test_qwen_refine_off_missing_assets_skips_sdxl_inference_loras(
    _ckpt, _loras, _cn, _up, _ult, _sam, _diff, _enc, _vae
):
    missing = missing_assets(_build_with_qwen_make(), "http://127.0.0.1:8188")
    lora_names = {row["filename"] for row in missing["loras"]}
    assert "char-lora.safetensors" not in lora_names
    assert "style-lora.safetensors" not in lora_names


@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch(
    "webapp.comfyui.asset_inventory.list_ultralytics_models",
    side_effect=ComfyUIRequestError(404, "unknown folder", url="http://x/models/ultralytics"),
)
@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
@patch(
    "webapp.comfyui.asset_inventory.list_loras",
    return_value=["e7sprites-000005.safetensors"],
)
@patch(
    "webapp.comfyui.asset_inventory.list_checkpoints",
    return_value=["waiIllustriousSDXL_v170.safetensors"],
)
def test_assets_ready_when_ultralytics_folder_missing(
    _ckpt, _loras, _cn, _up, _ult, _sam
):
    build = {
        "sdxl": {
            "checkpoint": {"filename": "waiIllustriousSDXL_v170.safetensors"},
            "loras": [{"kind": "style", "filename": "e7sprites-000005.safetensors"}],
        },
        "request": {"upscale_timing": "disabled"},
    }
    assert assets_ready(build, "http://127.0.0.1:8188")


@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
@patch(
    "webapp.comfyui.asset_inventory.list_loras",
    return_value=["subfolder/e7sprites-000005.safetensors"],
)
@patch(
    "webapp.comfyui.asset_inventory.list_checkpoints",
    return_value=["sdxl/waiIllustriousSDXL_v170.safetensors"],
)
def test_assets_ready_matches_subfolder_model_paths(_ckpt, _loras, _cn, _up, _ult, _sam):
    build = {
        "sdxl": {
            "checkpoint": {"filename": "waiIllustriousSDXL_v170.safetensors"},
            "loras": [{"kind": "style", "filename": "e7sprites-000005.safetensors"}],
        },
        "request": {"upscale_timing": "disabled"},
    }
    assert assets_ready(build, "http://127.0.0.1:8188")


def test_installed_assets_tolerates_optional_folder_errors():
    with patch(
        "webapp.comfyui.asset_inventory.list_checkpoints",
        return_value=["base.safetensors"],
    ), patch(
        "webapp.comfyui.asset_inventory.list_loras",
        return_value=["style.safetensors"],
    ), patch(
        "webapp.comfyui.asset_inventory.list_controlnets",
        return_value=[],
    ), patch(
        "webapp.comfyui.asset_inventory.list_upscale_models",
        return_value=[],
    ), patch(
        "webapp.comfyui.asset_inventory.list_ultralytics_models",
        side_effect=ComfyUIRequestError(404, "missing"),
    ), patch(
        "webapp.comfyui.asset_inventory.list_sams_models",
        side_effect=ComfyUIRequestError(404, "missing"),
    ):
        installed = installed_assets("http://127.0.0.1:8188")
    assert installed is not None
    assert "base.safetensors" in installed["checkpoints"]


@patch(
    "webapp.comfyui.asset_inventory._installed_diffusion_assets",
    return_value={
        "diffusion_models": frozenset(),
        "text_encoders": frozenset(),
        "vae": frozenset(),
        "loras": frozenset(),
    },
)
@patch("webapp.comfyui.asset_inventory.list_upscale_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_ultralytics_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_sams_models", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_checkpoints", return_value=["base.safetensors"])
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.asset_inventory.list_controlnets", return_value=[])
def test_missing_assets_reports_qwen_catalog_files(
    _cn, _loras, _ckpt, _sam, _ult, _up, _diff
):
    missing = missing_assets(_build_with_qwen_make(), "http://127.0.0.1:8188")
    diffusion = {row["filename"] for row in missing["diffusion_models"]}
    assert "qwen_image_2512_fp8_e4m3fn.safetensors" in diffusion
    encoders = {row["filename"] for row in missing["text_encoders"]}
    assert "qwen_2.5_vl_7b_fp8_scaled.safetensors" in encoders
    vae = {row["filename"] for row in missing["vae"]}
    assert "qwen_image_vae.safetensors" in vae
    loras = {row["filename"] for row in missing["loras"]}
    assert "Qwen-Image-2512-Lightning-4steps-V1.0-fp32.safetensors" in loras


@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch(
    "webapp.comfyui.asset_inventory.list_vae_models",
    return_value=["qwen_image_vae.safetensors"],
)
@patch(
    "webapp.comfyui.asset_inventory.list_text_encoders",
    return_value=["QWEN\\qwen_2.5_vl_7b_fp8_scaled.safetensors"],
)
@patch(
    "webapp.comfyui.asset_inventory.list_diffusion_models",
    return_value=["QWEN\\qwen_image_2512_fp8_e4m3fn.safetensors"],
)
def test_resolve_diffusion_model_paths_single_fetch_subfolder(
    _diff, _enc, _vae, _loras
):
    paths = resolve_diffusion_model_paths("qwen_image_2512", "http://127.0.0.1:8188")
    assert paths["qwen_image_2512_fp8_e4m3fn.safetensors"] == (
        "QWEN\\qwen_image_2512_fp8_e4m3fn.safetensors"
    )
    assert paths["qwen_2.5_vl_7b_fp8_scaled.safetensors"] == (
        "QWEN\\qwen_2.5_vl_7b_fp8_scaled.safetensors"
    )
    _diff.assert_called_once()
    _enc.assert_called_once()
    _vae.assert_called_once()
    _loras.assert_called_once()
