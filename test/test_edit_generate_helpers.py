"""Edit generate helpers — data URL decode, request sanitization, ephemeral paths."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui import edit_generate as eg


def _png_data_url(payload: bytes = b"\x89PNG\r\n\x1a\n") -> str:
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def test_decode_png_data_url_accepts_valid_png():
    data = eg._decode_png_data_url(_png_data_url())
    assert data.startswith(b"\x89PNG")


def test_decode_png_data_url_rejects_bad_prefix():
    with pytest.raises(ValueError, match="Expected data:image/png"):
        eg._decode_png_data_url("data:image/jpeg;base64,abcd")


def test_decode_png_data_url_rejects_invalid_base64():
    with pytest.raises(ValueError, match="Invalid base64"):
        eg._decode_png_data_url("data:image/png;base64,!!!not-base64!!!")


def test_decode_png_data_url_rejects_oversized_decoded_payload():
    huge = b"x" * 200
    with pytest.raises(ValueError, match="maximum size"):
        eg._decode_png_data_url(_png_data_url(huge), max_bytes=100)


def test_sanitize_edit_request_strips_image_data_url():
    raw = {"source_prompt_id": "abc", "image_data_url": _png_data_url()}
    clean = eg._sanitize_edit_request(raw)
    assert "image_data_url" not in clean
    assert clean["source_prompt_id"] == "abc"


def test_is_ephemeral_gen_path():
    path = eg.EDIT_OUTPUT_DIR / "_gen_deadbeef.png"
    assert eg._is_ephemeral_gen_path(path)
    assert not eg._is_ephemeral_gen_path(eg.EDIT_OUTPUT_DIR / "edit_out.png")


def test_resolve_generate_source_path_writes_ephemeral_file(tmp_path, monkeypatch):
    monkeypatch.setattr(eg, "EDIT_OUTPUT_DIR", tmp_path)
    payload = MagicMock()
    payload.image_data_url = _png_data_url(b"\x89PNG\x01")
    session = MagicMock()
    path = eg._resolve_generate_source_path(session, payload)
    assert path.exists()
    assert eg._is_ephemeral_gen_path(path)
    eg._unlink_ephemeral_gen(path)
    assert not path.exists()


def test_resolve_generate_source_path_falls_back_without_data_url(monkeypatch):
    expected = Path("outputs/make/still.png")
    monkeypatch.setattr(
        eg,
        "resolve_source_image_path",
        lambda session, source_prompt_id, source_kind: expected,
    )
    payload = MagicMock()
    payload.image_data_url = ""
    session = MagicMock()
    assert eg._resolve_generate_source_path(session, payload) == expected
