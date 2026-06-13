"""ControlNet preprocessor workflow builder."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.controlnet_preprocess import build_controlnet_preprocess_workflow


def test_build_openpose_preprocess_workflow():
    wf = build_controlnet_preprocess_workflow("source.png", cn_type="openpose")
    assert wf["load_image"]["inputs"]["image"] == "source.png"
    assert wf["preprocess"]["class_type"] == "OpenposePreprocessor"
    assert wf["preprocess"]["inputs"]["image"] == ["load_image", 0]
    assert wf["export_image"]["class_type"] == "SaveImage"
    assert wf["export_image"]["inputs"]["images"] == ["preprocess", 0]
    assert wf["export_image"]["inputs"]["filename_prefix"] == "ControlNet_Preprocess"


def test_build_depth_preprocess_workflow():
    wf = build_controlnet_preprocess_workflow("frame.png", cn_type="depth")
    assert wf["preprocess"]["class_type"] == "MiDaS-DepthMapPreprocessor"


def test_unknown_type_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown"):
        build_controlnet_preprocess_workflow("x.png", cn_type="nope")
