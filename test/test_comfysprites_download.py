"""ComfyUI-ComfySprites asset download helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_NODES_ROOT = Path(__file__).resolve().parents[1] / "ComfyUI-ComfySprites"
if str(_NODES_ROOT) not in sys.path:
    sys.path.insert(0, str(_NODES_ROOT))

from comfysprites_assets.download import (  # noqa: E402
    _DownloadProgress,
    checkpoint_entry_for_name,
    count_pending_assets,
    ensure_all_assets,
    ensure_checkpoints_from_json,
    ensure_controlnets_from_json,
    ensure_diffusion_models_from_json,
    lora_entry_for_name,
)


def test_ensure_all_assets_calls_each_kind(tmp_path: Path):
    ckpt = tmp_path / "ckpt.safetensors"
    lora = tmp_path / "lora.safetensors"
    cn = tmp_path / "cn.safetensors"
    ckpt.write_bytes(b"x" * 8)
    lora.write_bytes(b"x" * 8)
    cn.write_bytes(b"x" * 8)
    with (
        patch("comfysprites_assets.download.checkpoints_dir", return_value=tmp_path),
        patch("comfysprites_assets.download.loras_dir", return_value=tmp_path),
        patch("comfysprites_assets.download.controlnet_dir", return_value=tmp_path),
    ):
        applied = ensure_all_assets(
            checkpoints_json=json.dumps([{"filename": "ckpt.safetensors"}]),
            loras_json=json.dumps([{"filename": "lora.safetensors"}]),
            controlnets_json=json.dumps([{"filename": "cn.safetensors"}]),
        )
    assert applied["checkpoints"] == ["ckpt.safetensors"]
    assert applied["loras"] == ["lora.safetensors"]
    assert applied["controlnets"] == ["cn.safetensors"]


def test_ensure_checkpoints_skips_existing(tmp_path: Path):
    target = tmp_path / "test_ckpt.safetensors"
    target.write_bytes(b"x" * 16)
    payload = json.dumps(
        [{"filename": "test_ckpt.safetensors", "download_url": "https://example.com/x"}]
    )
    with patch("comfysprites_assets.download.checkpoints_dir", return_value=tmp_path):
        applied = ensure_checkpoints_from_json(payload)
    assert applied == ["test_ckpt.safetensors"]


def test_ensure_controlnets_skips_existing(tmp_path: Path):
    target = tmp_path / "test_cn.safetensors"
    target.write_bytes(b"x" * 16)
    payload = json.dumps(
        [{"filename": "test_cn.safetensors", "download_url": "https://example.com/x"}]
    )
    with patch("comfysprites_assets.download.controlnet_dir", return_value=tmp_path):
        applied = ensure_controlnets_from_json(payload)
    assert applied == ["test_cn.safetensors"]


@pytest.mark.parametrize(
    "fn",
    [ensure_checkpoints_from_json, ensure_controlnets_from_json],
)
def test_ensure_assets_invalid_json(fn):
    with pytest.raises(RuntimeError, match=r"invalid JSON"):
        fn("not-json")


def test_checkpoint_entry_for_name_case_insensitive():
    payload = json.dumps(
        [{"filename": "Model.SafeTensors", "download_url": "https://example.com/x"}]
    )
    entry = checkpoint_entry_for_name(payload, "model.safetensors")
    assert entry is not None
    assert entry["filename"] == "Model.SafeTensors"


def test_lora_entry_for_name_case_insensitive():
    payload = json.dumps(
        [{"filename": "Style.safetensors", "download_url": "https://example.com/x"}]
    )
    entry = lora_entry_for_name(payload, "style.safetensors")
    assert entry is not None
    assert entry["filename"] == "Style.safetensors"


def test_count_pending_assets_skips_on_disk(tmp_path, monkeypatch):
    ckpt = tmp_path / "ckpt.safetensors"
    ckpt.write_bytes(b"x")
    monkeypatch.setattr("comfysprites_assets.download.checkpoints_dir", lambda: tmp_path)
    monkeypatch.setattr("comfysprites_assets.download.loras_dir", lambda: tmp_path)
    monkeypatch.setattr("comfysprites_assets.download.controlnet_dir", lambda: tmp_path)

    pending = count_pending_assets(
        checkpoints_json='[{"filename": "ckpt.safetensors"}]',
        loras_json='[{"filename": "lora.safetensors"}]',
        controlnets_json="[]",
    )
    assert pending == 1


def test_ensure_diffusion_models_skips_existing(tmp_path: Path):
    sub = tmp_path / "QWEN"
    sub.mkdir()
    target = sub / "unet.safetensors"
    target.write_bytes(b"x" * 16)
    payload = json.dumps(
        [
            {
                "filename": "QWEN/unet.safetensors",
                "download_url": "https://example.com/x",
            }
        ]
    )
    with patch(
        "comfysprites_assets.download.diffusion_models_dir",
        return_value=tmp_path,
    ):
        applied = ensure_diffusion_models_from_json(payload)
    assert applied == ["QWEN/unet.safetensors"]


def test_count_pending_assets_includes_diffusion_models(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "comfysprites_assets.download.diffusion_models_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "comfysprites_assets.download.checkpoints_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr("comfysprites_assets.download.loras_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "comfysprites_assets.download.controlnet_dir",
        lambda: tmp_path,
    )
    pending = count_pending_assets(
        diffusion_models_json='[{"filename": "QWEN/unet.safetensors"}]',
    )
    assert pending == 1


def test_download_progress_divides_across_files():
    seen: list[float] = []
    progress = _DownloadProgress(total=2, on_progress=seen.append)

    progress.file_bytes(0.5)
    assert seen[-1] == 0.25
    progress.file_finished()
    assert seen[-1] == 0.5
    progress.file_bytes(0.5)
    assert seen[-1] == 0.75
    progress.file_finished()
    assert seen[-1] == 1.0
