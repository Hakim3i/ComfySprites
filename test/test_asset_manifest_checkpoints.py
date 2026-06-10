"""Checkpoint manifest for ComfyUI ensure injection."""

from __future__ import annotations

from webapp.comfyui.asset_manifest import make_lab_checkpoints_manifest


def test_checkpoints_manifest_inference_only():
    build = {
        "sdxl": {
            "checkpoint": {
                "filename": "infer.safetensors",
                "download_url": "https://example.com/infer",
            }
        }
    }
    manifest = make_lab_checkpoints_manifest(build)
    assert len(manifest) == 1
    assert manifest[0]["filename"] == "infer.safetensors"


def test_checkpoints_manifest_dedupes_shared_refine():
    build = {
        "sdxl": {
            "checkpoint": {"filename": "shared.safetensors", "version_id": 10},
        },
        "refine_sdxl": {
            "checkpoint": {"filename": "shared.safetensors", "version_id": 10},
        },
    }
    manifest = make_lab_checkpoints_manifest(build)
    assert len(manifest) == 1


def test_checkpoints_manifest_separate_refine():
    build = {
        "sdxl": {
            "checkpoint": {"filename": "infer.safetensors"},
        },
        "refine_sdxl": {
            "checkpoint": {"filename": "refine.safetensors", "download_url": "https://x"},
        },
    }
    manifest = make_lab_checkpoints_manifest(build)
    assert len(manifest) == 2
    names = {row["filename"] for row in manifest}
    assert names == {"infer.safetensors", "refine.safetensors"}
