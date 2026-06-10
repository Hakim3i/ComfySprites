"""ControlNet catalog and defaults."""

from webapp.services.catalog.controlnet_types import (
    all_controlnet_type_specs,
    controlnet_defaults_for_type,
    controlnet_type_keys,
    normalize_controlnets_map,
)


def test_controlnet_catalog_loads():
    keys = controlnet_type_keys()
    assert "openpose" in keys
    assert "depth" in keys
    assert "canny" in keys
    specs = all_controlnet_type_specs()
    assert len(specs) == len(keys)
    for spec in specs:
        assert spec.control_net.endswith(".safetensors")
    openpose = next(s for s in specs if s.key == "openpose")
    assert openpose.control_net == "noobaiXLControlnet_openposeModel.safetensors"


def test_controlnet_defaults_merge():
    defaults = controlnet_defaults_for_type("openpose")
    assert defaults["strength"] > 0
    merged = normalize_controlnets_map(
        {
            "openpose": {
                "image_path": "/uploads/animations/controlnet/openpose/x.png",
                "strength": 0.5,
            }
        }
    )
    assert merged["openpose"]["strength"] == 0.5
    assert merged["openpose"]["start_percent"] == defaults["start_percent"]
