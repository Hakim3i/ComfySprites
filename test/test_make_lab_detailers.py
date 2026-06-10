"""Make Lab detailer composition."""

from __future__ import annotations

from webapp.comfyui.make_lab.detailers import (
    compose_detailer_stages,
    default_detailer_timing,
    detailers_from_request,
    load_detailer_manifest,
    load_detailer_settings,
    patch_detailer_face_detailer,
    patch_detailer_prompts,
    resolve_detailer_timing,
)
from webapp.comfyui.workflow import (
    _MAKE_LAB_NODES,
    build_result_to_make_lab,
    load_make_lab_workflow,
    prepare_make_lab_workflow,
)


def test_load_make_lab_base_has_no_face_detailer():
    wf = load_make_lab_workflow()
    assert not any(
        n.get("class_type") == "FaceDetailer" for n in wf.values() if isinstance(n, dict)
    )
    assert len(wf) == 9


def test_compose_zero_detailers_save_from_refine_decode():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf,
        [],
        upscale_enabled=True,
        upscale_timing="after",
        refine_enabled=True,
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert stages == []
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_scale", 0]
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]


def test_default_detailer_timing():
    assert default_detailer_timing(separate_refine_model=False) == "after"
    assert default_detailer_timing(separate_refine_model=True) == "before"


def test_resolve_detailer_timing():
    assert resolve_detailer_timing({}, separate_refine_model=False) == "after"
    assert resolve_detailer_timing({}, separate_refine_model=True) == "before"
    assert (
        resolve_detailer_timing({"detailer_timing": "before"}, separate_refine_model=False)
        == "before"
    )
    assert (
        resolve_detailer_timing({"detailer_timing": "after"}, separate_refine_model=True)
        == "after"
    )
    assert (
        resolve_detailer_timing({"detailer_timing": "disabled"}, separate_refine_model=False)
        == "disabled"
    )


def test_compose_face_only_after_refine():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf,
        ["face"],
        timing="after",
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert len(stages) == 1
    assert stages[0].face_detailer == "detail:face:fd"
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["detail:face:fd"]["inputs"]["vae"] == ["checkpoint_refine", 2]
    assert "detail:face:to_pipe" not in wf
    assert "detail:face:from_pipe" not in wf
    refine = wf["sampler_refine"]["inputs"]
    assert refine["model"] == ["lora_refine", 0]
    assert refine["positive"] == ["prompt_refine_positive", 0]
    assert refine["negative"] == ["prompt_refine_negative", 0]
    assert wf["export_image"]["inputs"]["images"] == ["detail:face:fd", 0]
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]


def test_compose_face_only_before_refine():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf,
        ["face"],
        timing="before",
        pipeline_nodes=_MAKE_LAB_NODES,
    )
    assert len(stages) == 1
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_main", 0]
    assert wf["detail:face:fd"]["inputs"]["vae"] == ["checkpoint_refine", 2]
    assert wf["vae_encode"]["inputs"]["pixels"] == ["detail:face:fd", 0]
    refine = wf["sampler_refine"]["inputs"]
    assert refine["latent_image"] == ["vae_encode", 0]
    assert refine["model"] == ["detail:face:from_pipe", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_scale", 0]
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]


def test_build_result_to_make_lab_with_detailers_before_refine():
    build = {
        "scene": {"seed": 42, "refine_style": "_inference"},
        "request": {
            "detailers": ["face"],
            "detailer_timing": "before",
            "refine_enabled": True,
        },
        "character_adetailer": {
            "face": "testface",
            "eyes": "",
            "hands": "",
            "feet": "",
            "penis": "",
            "pussy": "",
            "breasts": "",
            "anus": "",
        },
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {"filename": "test.ckpt", "sampler": "Euler"},
        },
    }
    wf = build_result_to_make_lab(build)
    assert "detail:face:fd" in wf
    assert wf["vae_decode_main"]["inputs"]["samples"] == ["sampler_main", 0]
    assert wf["vae_decode_output"]["inputs"]["samples"] == ["sampler_refine", 0]
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_main", 0]
    assert wf["vae_encode"]["inputs"]["pixels"] == ["detail:face:fd", 0]
    assert wf["sampler_refine"]["inputs"]["latent_image"] == ["vae_encode", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["upscale_scale", 0]


def test_compose_face_then_eyes():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf, ["face", "eyes"], pipeline_nodes=_MAKE_LAB_NODES
    )
    assert len(stages) == 2
    assert wf["detail:eyes:fd"]["inputs"]["image"] == ["detail:face:fd", 0]
    assert wf["detail:eyes:fd"]["inputs"]["model"] == ["detail:face:from_pipe", 0]
    assert "detail:face:from_pipe" in wf
    assert "detail:eyes:from_pipe" not in wf
    assert "detail:eyes:to_pipe" not in wf


def test_compose_skip_middle_regions():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf, ["face", "breasts"], pipeline_nodes=_MAKE_LAB_NODES
    )
    assert len(stages) == 2
    assert stages[1].region == "breasts"
    assert wf["detail:breasts:fd"]["inputs"]["image"] == ["detail:face:fd", 0]


def test_detailers_from_request_canonical_order():
    manifest = load_detailer_manifest()
    order = manifest["order"]
    enabled = detailers_from_request({"detailers": ["breasts", "face", "unknown"]})
    assert enabled == ["face", "breasts"]
    assert all(r in order for r in enabled)


def test_patch_detailer_face_detailer_per_region_sweet_spots():
    """Eyes-only uses first_stage template defaults (0.7) until per-region patch."""
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf, ["eyes"], pipeline_nodes=_MAKE_LAB_NODES
    )
    assert wf["detail:eyes:fd"]["inputs"]["bbox_threshold"] == 0.7
    settings = load_detailer_settings()
    patch_detailer_face_detailer(
        wf, stages, regions_cfg=settings.get("regions") or {}
    )
    assert wf["detail:eyes:fd"]["inputs"]["bbox_threshold"] == 0.6
    settings = load_detailer_settings()
    assert (
        wf["detail:eyes:fd"]["inputs"]["bbox_threshold"]
        == settings["regions"]["eyes"]["face_detailer"]["bbox_threshold"]
    )


def test_apply_detailer_patches_eyes_only_bbox_threshold():
    build = {
        "scene": {"seed": 1},
        "request": {"detailers": ["eyes"]},
        "character_adetailer": {
            "face": "",
            "eyes": "green eyes",
            "hands": "",
            "feet": "",
            "penis": "",
            "pussy": "",
            "breasts": "",
            "anus": "",
        },
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {"filename": "test.ckpt", "sampler": "Euler"},
        },
    }
    wf = build_result_to_make_lab(build)
    assert wf["detail:eyes:fd"]["inputs"]["bbox_threshold"] == 0.6


def test_patch_detailer_prompts_uses_refine_style_and_character_adetailer():
    wf = prepare_make_lab_workflow()
    stages = compose_detailer_stages(
        wf, ["face"], pipeline_nodes=_MAKE_LAB_NODES
    )
    settings = load_detailer_settings()
    manifest = load_detailer_manifest()
    patch_detailer_prompts(
        wf,
        stages,
        {
            "face": "blue eyes, smile",
            "eyes": "",
            "hands": "",
            "feet": "",
            "penis": "",
            "pussy": "",
            "breasts": "",
            "anus": "",
        },
        detailer_style_positive="refine style prefix",
        settings=settings,
        manifest=manifest,
    )
    text = wf["detail:face:pos"]["inputs"]["text"]
    assert "refine style prefix" in text
    assert "blue eyes" in text
    assert "1girl" not in text
    assert "standing" not in text
    assert "masterpiece" not in text


def test_compose_detailer_node_titles():
    wf = prepare_make_lab_workflow()
    compose_detailer_stages(
        wf, ["face", "eyes"], pipeline_nodes=_MAKE_LAB_NODES
    )
    assert wf["detail:face:fd"]["_meta"]["title"] == "Detail Face — FaceDetailer"
    assert wf["detail:face:pos"]["_meta"]["title"] == "Detail Face — Positive Prompt"
    assert wf["detail:eyes:det"]["_meta"]["title"] == "Detail Eyes — Detector"


def test_build_result_to_make_lab_with_detailers_after_refine():
    build = {
        "scene": {"seed": 42, "refine_style": "_inference"},
        "request": {"detailers": ["face"], "detailer_timing": "after"},
        "character_adetailer": {
            "face": "testface",
            "eyes": "",
            "hands": "",
            "feet": "",
            "penis": "",
            "pussy": "",
            "breasts": "",
            "anus": "",
        },
        "sdxl": {
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "checkpoint": {"filename": "test.ckpt", "sampler": "Euler"},
        },
    }
    wf = build_result_to_make_lab(build)
    assert "detail:face:fd" in wf
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["detail:face:fd"]["inputs"]["image"] == ["vae_decode_output", 0]
    assert wf["export_image"]["inputs"]["images"] == ["detail:face:fd", 0]
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]
