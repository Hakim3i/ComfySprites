"""Decomposed workflow node library."""

from __future__ import annotations

from webapp.comfyui.workflow_builder import (
    build_pipeline_workflow,
    load_base_workflow_nodes,
    load_registry,
    registry_nodes,
    validate_composed_workflow,
)


def test_registry_loads_stable_ids():
    reg = load_registry()
    assert reg["sampler"] == "sampler_main"
    assert reg["main_decode"] == "vae_decode_main"
    nodes = registry_nodes()
    assert nodes["refine_sampler"] == "sampler_refine"
    assert nodes["positive"] == reg["main_positive"]


def test_base_workflow_has_nine_nodes():
    wf = load_base_workflow_nodes()
    validate_composed_workflow(wf)
    assert len(wf) == 9
    assert "sampler_refine" not in wf
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_main", 0]


def test_build_refine_upscale_after_pipeline():
    from webapp.comfyui.workflow import REFINE_STACK_REWIRE

    result = build_pipeline_workflow(
        refine_on=True,
        upscale_timing="after",
        detailer_timing="disabled",
        enabled_detailers=[],
        refine_rewire=REFINE_STACK_REWIRE,
    )
    wf = result.workflow
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["sampler_main", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]
    assert wf["upscale_restore"]["inputs"]["image"] == ["upscale_scale", 0]
    assert "vae_decode_main" not in wf


def test_build_detailers_before_refine():
    from webapp.comfyui.workflow import REFINE_STACK_REWIRE

    result = build_pipeline_workflow(
        refine_on=True,
        upscale_timing="after",
        detailer_timing="before",
        enabled_detailers=["face"],
        refine_rewire=REFINE_STACK_REWIRE,
    )
    wf = result.workflow
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_main", 0]
    assert wf["vae_encode"]["inputs"]["pixels"] == ["detail:face:fd", 0]
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["vae_encode", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
