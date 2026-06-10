"""Asset download workflow builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.download_workflow import (
    ASSET_DOWNLOAD_NODE_ID,
    ASSET_DOWNLOAD_OUTPUT_NODE_ID,
    DOWNLOADER_CLASS,
    DOWNLOAD_OUTPUT_CLASS,
    build_asset_download_workflow,
)


def test_build_asset_download_workflow():
    missing = {
        "checkpoints": [{"filename": "base.safetensors", "download_url": "https://ex/base"}],
        "loras": [{"filename": "style.safetensors", "download_url": "https://ex/l"}],
        "controlnets": [{"filename": "cn.safetensors", "download_url": "https://ex/cn"}],
    }
    wf = build_asset_download_workflow(
        missing,
        inference_ckpt_name="base.safetensors",
        tokens={"civitai_token": "civitai-test", "hf_token": "hf-test"},
    )
    node = wf[ASSET_DOWNLOAD_NODE_ID]
    assert node["class_type"] == DOWNLOADER_CLASS
    assert node["inputs"]["ckpt_name"] == "base.safetensors"
    assert node["inputs"]["civitai_token"] == "civitai-test"
    assert json.loads(node["inputs"]["checkpoints_json"])[0]["filename"] == "base.safetensors"
    assert json.loads(node["inputs"]["loras_json"])[0]["filename"] == "style.safetensors"
    assert json.loads(node["inputs"]["controlnets_json"])[0]["filename"] == "cn.safetensors"
    out = wf[ASSET_DOWNLOAD_OUTPUT_NODE_ID]
    assert out["class_type"] == DOWNLOAD_OUTPUT_CLASS
    assert out["inputs"]["message"] == [ASSET_DOWNLOAD_NODE_ID, 0]
