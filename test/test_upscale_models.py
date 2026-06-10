"""Upscale model catalog and asset manifest."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.asset_manifest import make_lab_upscalers_manifest
from webapp.services.catalog.upscale_models import (
    all_upscale_model_specs,
    upscale_ensure_entry,
    upscale_model_spec_for_filename,
)


def test_catalog_has_six_cmm_models():
    specs = all_upscale_model_specs()
    assert len(specs) == 6
    filenames = {spec.filename for spec in specs}
    assert "RealESRGAN_x2.pth" in filenames
    assert "4x-UltraSharp.pth" in filenames


def test_upscale_ensure_entry_uses_hf_url():
    entry = upscale_ensure_entry("4x-AnimeSharp.pth")
    assert entry is not None
    assert entry["filename"] == "4x-AnimeSharp.pth"
    assert "huggingface.co/Kim2091/AnimeSharp" in entry["download_url"]


def test_manifest_includes_selected_upscaler_when_enabled():
    build = {
        "request": {
            "upscale_timing": "after",
            "upscale_model": "4x-UltraSharp.pth",
        }
    }
    rows = make_lab_upscalers_manifest(build)
    assert len(rows) == 1
    assert rows[0]["filename"] == "4x-UltraSharp.pth"


def test_manifest_skips_when_upscale_disabled():
    build = {
        "request": {
            "upscale_timing": "disabled",
            "upscale_model": "4x-UltraSharp.pth",
        }
    }
    assert make_lab_upscalers_manifest(build) == []


def test_unknown_filename_not_in_catalog():
    assert upscale_model_spec_for_filename("custom_upscaler.pth") is None
    assert upscale_ensure_entry("custom_upscaler.pth") is None
