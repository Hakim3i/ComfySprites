"""Build a ComfyUI workflow that only downloads missing model files."""

from __future__ import annotations

from typing import Any

from .asset_manifest import (
    checkpoints_json_for_manifest,
    controlnets_json_for_manifest,
    detailers_json_for_manifest,
    loras_json_for_manifest,
    tokens_for_comfyui,
    upscalers_json_for_manifest,
)
from .workflow_builder import load_pipeline_node

ASSET_DOWNLOAD_NODE_ID = "asset_downloader"
ASSET_DOWNLOAD_OUTPUT_NODE_ID = "asset_download_output"
DOWNLOADER_CLASS = "ComfySpritesDownloader"
DOWNLOAD_OUTPUT_CLASS = "ComfySpritesDownloadOutput"


def build_asset_download_workflow(
    missing: dict[str, list[dict[str, Any]]],
    *,
    inference_ckpt_name: str,
    tokens: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Single-node workflow: ``ComfySpritesDownloader`` for *missing* manifest rows."""
    checkpoints = list(missing.get("checkpoints") or [])
    loras = list(missing.get("loras") or [])
    controlnets = list(missing.get("controlnets") or [])
    upscalers = list(missing.get("upscalers") or [])
    detailers = list(missing.get("detailers") or [])
    if (
        not checkpoints
        and not loras
        and not controlnets
        and not upscalers
        and not detailers
    ):
        raise ValueError("missing asset manifest is empty")

    tok = tokens if tokens is not None else tokens_for_comfyui()
    ckpt_name = (inference_ckpt_name or "").strip()
    if not ckpt_name and checkpoints:
        ckpt_name = str(checkpoints[0].get("filename") or "").strip()
    if not ckpt_name:
        raise ValueError(
            "inference checkpoint filename required for downloader workflow"
        )

    raw = load_pipeline_node("asset_downloader")
    workflow = {
        ASSET_DOWNLOAD_NODE_ID: {
            "class_type": DOWNLOADER_CLASS,
            "_meta": dict(raw.get("_meta") or {}),
            "inputs": dict(raw.get("inputs") or {}),
        }
    }
    node = workflow[ASSET_DOWNLOAD_NODE_ID]
    inputs = node.setdefault("inputs", {})
    inputs["ckpt_name"] = ckpt_name
    inputs["checkpoints_json"] = checkpoints_json_for_manifest(checkpoints)
    inputs["loras_json"] = loras_json_for_manifest(loras)
    inputs["controlnets_json"] = controlnets_json_for_manifest(controlnets)
    inputs["upscalers_json"] = upscalers_json_for_manifest(upscalers)
    inputs["detailers_json"] = detailers_json_for_manifest(detailers)
    inputs["civitai_token"] = tok.get("civitai_token") or ""
    inputs["hf_token"] = tok.get("hf_token") or ""
    workflow[ASSET_DOWNLOAD_OUTPUT_NODE_ID] = {
        "class_type": DOWNLOAD_OUTPUT_CLASS,
        "_meta": {"title": "ComfySprites Download Output"},
        "inputs": {
            "message": [ASSET_DOWNLOAD_NODE_ID, 0],
        },
    }
    return workflow
