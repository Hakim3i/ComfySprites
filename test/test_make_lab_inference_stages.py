"""Make Lab refine / upscale stage injection."""

from __future__ import annotations

from webapp.comfyui.make_lab.compose import (
    UPSCALE_TIMING_AFTER,
    UPSCALE_TIMING_BEFORE,
    UPSCALE_TIMING_DISABLED,
)
from webapp.comfyui.workflow_builder import infer_upscale_timing
from webapp.comfyui.make_lab.detailers import compose_detailer_stages
from webapp.comfyui.make_lab.compose import (
    refine_enabled_from_request,
    resolve_upscale_timing,
    upscale_enabled_from_request,
)
from webapp.comfyui.workflow import (
    _MAKE_LAB_NODES,
    load_make_lab_workflow,
    prepare_make_lab_workflow,
)


def test_stage_flags_default_enabled_for_legacy_requests():
    assert refine_enabled_from_request({}) is True
    assert upscale_enabled_from_request({}) is True
    assert resolve_upscale_timing({}) == UPSCALE_TIMING_AFTER
    assert refine_enabled_from_request(None) is True


def test_stage_flags_read_explicit_booleans():
    assert refine_enabled_from_request({"refine_enabled": False}) is False
    assert resolve_upscale_timing({"upscale_enabled": True}) == UPSCALE_TIMING_AFTER
    assert resolve_upscale_timing({"upscale_timing": "before", "refine_enabled": True}) == UPSCALE_TIMING_BEFORE


def test_upscale_before_requires_refine():
    assert (
        resolve_upscale_timing(
            {"upscale_timing": "before", "refine_enabled": False}
        )
        == UPSCALE_TIMING_AFTER
    )


def test_both_disabled_exports_base_decode():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "disabled"}
    )
    compose_detailer_stages(wf, [])
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_main", 0]
    assert wf["export_image"]["inputs"]["images"] == ["vae_decode_output", 0]
    assert "upscale_model_loader" not in wf
    assert "sampler_refine" not in wf


def test_upscale_only_exports_scaled_image():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "after"}
    )
    compose_detailer_stages(
        wf,
        [],
        upscale_enabled=True,
        upscale_timing=UPSCALE_TIMING_AFTER,
        refine_enabled=False,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]
    assert "sampler_refine" not in wf


def test_refine_only_latent_pass_through_and_shared_clip():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": True, "upscale_timing": "disabled"}
    )
    compose_detailer_stages(wf, [])
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["sampler_main", 0]
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_refine", 0]
    assert wf["prompt_refine_positive"]["inputs"]["clip"] == ["clip_skip", 0]
    assert wf["prompt_refine_negative"]["inputs"]["clip"] == ["clip_skip", 0]
    assert wf["export_image"]["inputs"]["images"] == ["vae_decode_output", 0]
    assert "upscale_model_loader" not in wf
    assert "vae_encode" not in wf
    assert "vae_decode_main" not in wf


def test_upscale_before_refine_decodes_encodes_latents():
    wf = prepare_make_lab_workflow(
        {
            "refine_enabled": True,
            "upscale_timing": "before",
        }
    )
    compose_detailer_stages(
        wf,
        [],
        upscale_enabled=True,
        upscale_timing=UPSCALE_TIMING_BEFORE,
        refine_enabled=True,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["vae_decode_main"]["inputs"]["samples"] == ["sampler_main", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_main", 0]
    assert wf["vae_encode"]["inputs"]["pixels"] == ["upscale_scale", 0]
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["vae_encode", 0]
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_refine", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]
    assert wf["upscale_restore"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert infer_upscale_timing(wf) == UPSCALE_TIMING_BEFORE


def test_both_enabled_full_pipeline_after_refine():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": True, "upscale_timing": "after"}
    )
    compose_detailer_stages(
        wf,
        [],
        upscale_enabled=True,
        upscale_timing=UPSCALE_TIMING_AFTER,
        refine_enabled=True,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["sampler_main", 0]
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_refine", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]
    assert infer_upscale_timing(wf) == UPSCALE_TIMING_AFTER
    assert "vae_decode_main" not in wf


def test_refine_disabled_detailers_after_use_inference_stack():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "disabled"}
    )
    compose_detailer_stages(
        wf,
        ["face"],
        timing="after",
        upscale_enabled=False,
        upscale_timing=UPSCALE_TIMING_DISABLED,
        refine_enabled=False,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["detail:face:fd"]["inputs"]["model"] == ["checkpoint_main", 0]
    assert wf["export_image"]["inputs"]["images"] == ["detail:face:fd", 0]


def test_refine_fragment_nodes_present_when_enabled():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": True, "upscale_timing": "after"}
    )
    for node_id in ("checkpoint_refine", "lora_refine", "prompt_refine_positive", "prompt_refine_negative", "sampler_refine"):
        assert node_id in wf


def test_upscale_fragment_nodes_present_when_enabled():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "after"}
    )
    for node_id in (
        "upscale_model_loader",
        "upscale_with_model",
        "upscale_scale",
        "upscale_restore",
    ):
        assert node_id in wf


def test_detailers_before_refine_off_upscale_on_exports_scaled():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "after"}
    )
    compose_detailer_stages(
        wf,
        ["face"],
        timing="before",
        upscale_enabled=True,
        upscale_timing=UPSCALE_TIMING_AFTER,
        refine_enabled=False,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["upscale_with_model"]["inputs"]["image"] == ["detail:face:fd", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_restore", 0]


def test_detailers_before_refine_off_upscale_off_exports_detailer():
    wf = prepare_make_lab_workflow(
        {"refine_enabled": False, "upscale_timing": "disabled"}
    )
    compose_detailer_stages(
        wf,
        ["face"],
        timing="before",
        upscale_enabled=False,
        upscale_timing=UPSCALE_TIMING_DISABLED,
        refine_enabled=False,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert wf["export_image"]["inputs"]["images"] == ["detail:face:fd", 0]


def test_base_workflow_has_no_optional_stages():
    wf = load_make_lab_workflow()
    assert len(wf) == 9
    assert "upscale_model_loader" not in wf
    assert "sampler_refine" not in wf
