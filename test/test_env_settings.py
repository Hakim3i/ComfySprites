"""Tests for workspace .env read/write."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def env_module(tmp_path, monkeypatch):
    import webapp.env_settings as es

    es = importlib.reload(es)
    monkeypatch.setattr(es, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(es, "ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("CIVITAI_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("COMFYUI_BASE_URL", raising=False)
    monkeypatch.delenv("COMFYUI_PHOTO_BASE_URL", raising=False)
    return es


def test_save_and_load_roundtrip(env_module):
    env_module.save_api_keys(civitai_token="civ-123", hf_token="hf-456")
    assert env_module.ENV_PATH.is_file()
    keys = env_module.load_api_keys()
    assert keys["civitai_token"] == "civ-123"
    assert keys["hf_token"] == "hf-456"


def test_save_preserves_unrelated_keys(env_module):
    env_module.ENV_PATH.write_text("FOO=bar\nCIVITAI_TOKEN=old\n", encoding="utf-8")
    env_module.save_api_keys(civitai_token="new", hf_token="hf")
    text = env_module.ENV_PATH.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert "CIVITAI_TOKEN=new" in text or 'CIVITAI_TOKEN="new"' in text
    assert "HF_TOKEN" in text


def test_comfyui_url_raises_when_unset(env_module):
    with pytest.raises(RuntimeError, match="ComfyUI URL is not configured"):
        env_module.load_comfyui_base_url()


def test_comfyui_url_photo_key(env_module, monkeypatch):
    monkeypatch.setenv("COMFYUI_PHOTO_BASE_URL", "http://photo:8188")
    assert env_module.load_comfyui_base_url() == "http://photo:8188"


def test_comfyui_url_legacy_base_key(env_module, monkeypatch):
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://legacy:8188")
    assert env_module.load_comfyui_base_url() == "http://legacy:8188"


def test_comfyui_urls_dict(env_module):
    env_module.save_comfyui_urls(photo_url="http://photo:8188/")
    urls = env_module.load_comfyui_urls()
    assert urls == {"photo": "http://photo:8188"}


def test_comfyui_url_save_and_load(env_module):
    env_module.save_comfyui_base_url("http://example:8188/")
    assert env_module.load_comfyui_base_url() == "http://example:8188"
    text = env_module.ENV_PATH.read_text(encoding="utf-8")
    assert "COMFYUI_PHOTO_BASE_URL" in text
    assert "COMFYUI_VIDEO_BASE_URL" not in text


def test_comfyui_url_preserves_other_keys(env_module):
    env_module.ENV_PATH.write_text("CIVITAI_TOKEN=keep\n", encoding="utf-8")
    env_module.save_comfyui_urls(photo_url="http://host:8188")
    text = env_module.ENV_PATH.read_text(encoding="utf-8")
    assert "CIVITAI_TOKEN=keep" in text
    assert "COMFYUI_PHOTO_BASE_URL" in text
