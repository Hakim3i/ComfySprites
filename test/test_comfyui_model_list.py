"""ComfyUI model folder list parsing."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.client import (
    ComfyUIRequestError,
    _list_model_folder,
    _parse_model_list_response,
)


def test_parse_model_list_response_accepts_strings():
    assert _parse_model_list_response(
        ["a.safetensors", "sub/b.safetensors"]
    ) == ["a.safetensors", "sub/b.safetensors"]


def test_parse_model_list_response_accepts_objects():
    assert _parse_model_list_response(
        [{"name": "qwen.safetensors", "pathIndex": 0}]
    ) == ["qwen.safetensors"]


@patch("webapp.comfyui.client._fetch_comfyui")
def test_list_model_folder_returns_empty_on_unknown_folder(mock_fetch):
    mock_fetch.side_effect = ComfyUIRequestError(
        404, "not found", url="http://127.0.0.1:8188/models/ultralytics"
    )
    assert _list_model_folder("http://127.0.0.1:8188", "ultralytics") == []


@patch("webapp.comfyui.client._fetch_comfyui")
def test_list_model_folder_falls_back_to_api_prefix(mock_fetch):
    mock_fetch.side_effect = [
        ComfyUIRequestError(404, "legacy", url="http://127.0.0.1:8188/models/loras"),
        ["style.safetensors"],
    ]
    assert _list_model_folder("http://127.0.0.1:8188", "loras") == ["style.safetensors"]
    assert mock_fetch.call_count == 2
