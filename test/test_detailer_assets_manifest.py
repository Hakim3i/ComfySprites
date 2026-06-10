"""Detailer detector/SAM asset manifest for Make preflight."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.asset_manifest import make_lab_detailer_assets_manifest


def test_detailer_manifest_includes_face_detector_and_sam():
    build = {
        "request": {"detailers": ["face"], "detailer_timing": "before"},
    }
    rows = make_lab_detailer_assets_manifest(build)
    paths = {row["relative_path"] for row in rows}
    assert "bbox/face_yolov9c.pt" in paths
    assert "sam_vit_b_01ec64.pth" in paths
    face = next(r for r in rows if r["relative_path"] == "bbox/face_yolov9c.pt")
    assert face["folder"] == "ultralytics"
    assert face.get("download_url")


def test_detailer_manifest_empty_when_disabled():
    build = {
        "request": {"detailers": ["face"], "detailer_timing": "disabled"},
    }
    assert make_lab_detailer_assets_manifest(build) == []
