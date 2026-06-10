"""Make Lab RMBG composition."""

from __future__ import annotations

from webapp.comfyui.make_lab.detailers import compose_detailer_stages
from webapp.comfyui.make_lab.rmbg import (
    apply_rmbg_stage,
    load_rmbg_defaults,
    rmbg_enabled_from_request,
)
from webapp.comfyui.workflow_builder import load_node_template
from webapp.comfyui.workflow import (
    _MAKE_LAB_NODES,
    load_make_lab_workflow,
    prepare_make_lab_workflow,
)


def test_load_rmbg_defaults_from_node():
    defaults = load_rmbg_defaults()
    tpl = load_node_template("rmbg")
    assert tpl["class_type"] == "RMBG"
    assert defaults["model"] == "RMBG-2.0"


def test_rmbg_disabled_skips_node():
    wf = load_make_lab_workflow()
    assert apply_rmbg_stage(wf, {}) is None
    assert "rmbg:0" not in wf
    assert wf["export_image"]["inputs"]["images"] == ["vae_decode_output", 0]


def test_rmbg_enabled_rewires_export():
    wf = load_make_lab_workflow()
    node_id = apply_rmbg_stage(
        wf,
        {
            "rmbg": {
                "enabled": True,
                "sensitivity": 0.8,
                "background": "Color",
                "background_color": "#111111",
            }
        },
    )
    assert node_id == "rmbg:0"
    assert wf["rmbg:0"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["rmbg:0"]["inputs"]["sensitivity"] == 0.8
    assert wf["rmbg:0"]["inputs"]["background"] == "Color"
    assert wf["rmbg:0"]["inputs"]["background_color"] == "#111111"
    assert wf["export_image"]["inputs"]["images"] == ["rmbg:0", 0]
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]


def test_rmbg_after_detailers():
    wf = prepare_make_lab_workflow()
    compose_detailer_stages(
        wf,
        ["face"],
        timing="after",
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    apply_rmbg_stage(wf, {"rmbg": {"enabled": True}})
    assert wf["rmbg:0"]["inputs"]["image"] == ["detail:face:fd", 0]
    assert wf["export_image"]["inputs"]["images"] == ["rmbg:0", 0]


def test_rmbg_enabled_from_request():
    assert not rmbg_enabled_from_request({})
    assert not rmbg_enabled_from_request({"rmbg": {"enabled": False}})
    assert rmbg_enabled_from_request({"rmbg": {"enabled": True}})


def test_rmbg_alpha_sets_export_png():
    from webapp.comfyui.inject_assets import patch_make_lab_export

    wf = load_make_lab_workflow()
    apply_rmbg_stage(wf, {"rmbg": {"enabled": True, "background": "Alpha"}})
    patch_make_lab_export(wf, request={"rmbg": {"enabled": True, "background": "Alpha"}})
    assert wf["export_image"]["inputs"]["format"] == "png"
