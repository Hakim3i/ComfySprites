"""Make Lab engine routing for Qwen Image 2512."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db.models import LORA_KIND_STYLE, Lora, Style
from webapp.db.seed_constants import DEFAULT_CHARACTER_SLUG, DEFAULT_STYLE_SLUG
from webapp.db.styles_defaults import load_style_defaults

WAI_V17_FILENAME = next(
    s for s in load_style_defaults() if s.slug == DEFAULT_STYLE_SLUG
).filename
from webapp.services.sdxl.payload import MAKE_ENGINE_ANIMA, MAKE_ENGINE_QWEN
from webapp.comfyui.workflow import build_result_to_make_lab

QWEN_UNET_FILENAME = "qwen_image_2512_fp8_e4m3fn.safetensors"
ANIMA_UNET_FILENAME = "anima-base-v1.0.safetensors"


def _qwen_build_base():
    return {
        "qwen_make": {
            "positive": "qwen positive",
            "negative": "qwen negative",
            "width": 1328,
            "height": 1328,
            "steps": 4,
            "cfg": 1.0,
            "shift": 3.1,
        },
        "sdxl": {
            "positive": "qwen positive",
            "negative": "qwen negative",
            "width": 1328,
            "height": 1328,
            "checkpoint": {
                "filename": QWEN_UNET_FILENAME,
                "download_url": "https://huggingface.co/example/unet.safetensors",
            },
        },
        "refine_sdxl": {
            "positive": "refine positive",
            "negative": "refine negative",
            "checkpoint": {
                "filename": WAI_V17_FILENAME,
                "sampler": "Euler a",
                "scheduler": "normal",
                "steps": 25,
                "cfg_scale": 6.0,
                "clip_skip": 2,
            },
        },
        "scene": {"seed": 11},
    }


@patch(
    "webapp.comfyui.asset_inventory.resolve_diffusion_model_paths",
    return_value={},
)
def test_build_result_to_make_lab_qwen_refine_off(_paths):
    build_dict = {
        **_qwen_build_base(),
        "request": {"refine_enabled": False},
    }
    wf = build_result_to_make_lab(build_dict)
    assert wf["export_image"]["inputs"]["images"] == ["vae_decode", 0]
    assert wf["preview_save"]["class_type"] == "PreviewImage"
    assert wf["preview_save"]["inputs"]["images"] == ["export_image", 0]
    assert "sampler_refine" not in wf
    assert wf["ksampler"]["inputs"]["steps"] == 4


@patch(
    "webapp.comfyui.asset_inventory.resolve_diffusion_model_paths",
    return_value={},
)
def test_build_result_to_make_lab_qwen_refine_on(_paths):
    build_dict = {
        **_qwen_build_base(),
        "request": {
            "refine_enabled": True,
            "refine_steps": 12,
            "refine_denoise": 0.35,
            "upscale_timing": "disabled",
        },
    }
    wf = build_result_to_make_lab(build_dict)
    assert wf["ksampler"]["inputs"]["steps"] == 4
    assert wf["sampler_refine"]["inputs"]["steps"] == 12
    assert wf["vae_encode"]["inputs"]["pixels"] == ["vae_decode", 0]
    assert wf["export_image"]["inputs"]["images"] == ["vae_decode_output", 0]
    assert wf["checkpoint_main"]["inputs"]["ckpt_name"] == WAI_V17_FILENAME
    assert wf["checkpoint_main"]["inputs"]["ckpt_name"] != "placeholder.safetensors"
    assert wf["vae_decode_output"]["inputs"]["vae"] == ["checkpoint_refine", 2]
    assert wf["clip_skip"]["inputs"]["clip"] == ["checkpoint_refine", 1]
    assert wf["sampler_refine"]["inputs"]["sampler_name"] == "euler_ancestral"
    assert wf["sampler_refine"]["inputs"]["scheduler"] == "normal"
    assert "sampler_main" not in wf
    assert wf["ksampler"]["_meta"]["title"] == "Main Sampling"
    assert (
        wf["diffusion_model"]["inputs"]["unet_name"] == QWEN_UNET_FILENAME
    )


@patch(
    "webapp.comfyui.asset_inventory.resolve_diffusion_model_paths",
    return_value={},
)
def test_build_result_to_make_lab_qwen_refine_upscale_before(_paths):
    build_dict = {
        **_qwen_build_base(),
        "request": {
            "refine_enabled": True,
            "refine_steps": 12,
            "refine_denoise": 0.35,
            "upscale_timing": "before",
            "upscale_by": 2.0,
        },
    }
    wf = build_result_to_make_lab(build_dict)
    assert wf["vae_encode"]["inputs"]["pixels"] == ["upscale_scale", 0]
    assert wf["upscale_with_model"]["inputs"]["image"] == ["vae_decode", 0]


def test_composer_emits_qwen_make_block(client):
    from webapp.db import session_scope

    qwen_slug = "test-qwen-style"
    with session_scope() as session:
        lora = Lora(
            kind=LORA_KIND_STYLE,
            name="Qwen test LoRA",
            filename="qwen-style.safetensors",
            trigger="qwenstyle",
            strength=1.0,
        )
        session.add(lora)
        session.flush()
        session.add(
            Style(
                slug=qwen_slug,
                display_name="Qwen test",
                filename=QWEN_UNET_FILENAME,
                download_url="https://huggingface.co/example/unet.safetensors",
                base_model=MAKE_ENGINE_QWEN,
                sampler="euler",
                scheduler="simple",
                steps=4,
                cfg_scale=1.0,
                width=1328,
                height=1328,
                prefix="qwen test",
                negative="bad",
                lora_id=lora.id,
            )
        )
        session.commit()

    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": qwen_slug,
            "engine": MAKE_ENGINE_QWEN,
            "animation": "none",
            "seed": 99,
            "width": 1328,
            "height": 1328,
            "refine_enabled": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("qwen_make")
    assert body["scene"]["engine"] == MAKE_ENGINE_QWEN
    assert "controlnet" not in body
    assert body["qwen_make"]["shift"] == 3.1

    with session_scope() as session:
        row = session.query(Style).filter(Style.slug == qwen_slug).one()
        session.delete(row)
        session.delete(session.query(Lora).filter(Lora.id == row.lora_id).one())
        session.commit()


def test_composer_qwen_refine_style_none_picks_illustrious(client):
    from webapp.db import session_scope

    qwen_slug = "test-qwen-refine-none"
    with session_scope() as session:
        lora = Lora(
            kind=LORA_KIND_STYLE,
            name="Qwen refine none LoRA",
            filename="qwen-refine-none.safetensors",
            trigger="qwn",
            strength=1.0,
        )
        session.add(lora)
        session.flush()
        session.add(
            Style(
                slug=qwen_slug,
                display_name="Qwen refine none",
                filename=QWEN_UNET_FILENAME,
                download_url="https://huggingface.co/example/unet.safetensors",
                base_model=MAKE_ENGINE_QWEN,
                sampler="euler",
                scheduler="simple",
                steps=4,
                cfg_scale=1.0,
                width=1328,
                height=1328,
                prefix="qwen",
                negative="bad",
                lora_id=lora.id,
            )
        )
        session.commit()

    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": qwen_slug,
            "engine": MAKE_ENGINE_QWEN,
            "refine_style": "none",
            "animation": "none",
            "seed": 77,
            "refine_enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    refine_ckpt = (body.get("refine_sdxl") or {}).get("checkpoint") or {}
    assert refine_ckpt.get("filename")
    assert body["scene"]["refine_style"] != "_inference"
    assert body["scene"]["refine_style"] != qwen_slug

    with session_scope() as session:
        row = session.query(Style).filter(Style.slug == qwen_slug).one()
        session.delete(row)
        session.delete(session.query(Lora).filter(Lora.id == row.lora_id).one())
        session.commit()


def test_composer_anima_build_omits_controlnet(client):
    from webapp.db import session_scope

    anima_slug = "test-anima-no-cn"
    with session_scope() as session:
        session.add(
            Style(
                slug=anima_slug,
                display_name="Anima no CN",
                filename=ANIMA_UNET_FILENAME,
                download_url="https://civitai.red/api/download/models/2945208",
                base_model=MAKE_ENGINE_ANIMA,
                sampler="er_sde",
                scheduler="normal",
                steps=40,
                cfg_scale=5.0,
                width=1024,
                height=1024,
                prefix="masterpiece, best quality, ",
                negative="worst quality",
            )
        )
        session.commit()

    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": anima_slug,
            "engine": MAKE_ENGINE_ANIMA,
            "animation": "none",
            "seed": 77,
            "refine_enabled": False,
            "controlnet": {"openpose": {"enabled": True}},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("anima_make")
    assert "controlnet" not in body

    with session_scope() as session:
        row = session.query(Style).filter(Style.slug == anima_slug).one()
        session.delete(row)
        session.commit()


def test_composer_anima_refine_style_none_picks_illustrious(client):
    from webapp.db import session_scope

    anima_slug = "test-anima-refine-none"
    with session_scope() as session:
        session.add(
            Style(
                slug=anima_slug,
                display_name="Anima refine none",
                filename=ANIMA_UNET_FILENAME,
                download_url="https://civitai.red/api/download/models/2945208",
                base_model=MAKE_ENGINE_ANIMA,
                sampler="er_sde",
                scheduler="normal",
                steps=40,
                cfg_scale=5.0,
                width=1024,
                height=1024,
                prefix="masterpiece, best quality, score_7, safe, ",
                negative="worst quality, low quality",
            )
        )
        session.commit()

    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": anima_slug,
            "engine": MAKE_ENGINE_ANIMA,
            "refine_style": "none",
            "animation": "none",
            "seed": 88,
            "refine_enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("anima_make")
    refine_ckpt = (body.get("refine_sdxl") or {}).get("checkpoint") or {}
    assert refine_ckpt.get("filename") == WAI_V17_FILENAME
    assert body["scene"]["refine_style"] != "_inference"
    assert body["scene"]["refine_style"] != anima_slug

    with session_scope() as session:
        row = session.query(Style).filter(Style.slug == anima_slug).one()
        session.delete(row)
        session.commit()


def test_build_with_explicit_engine_mismatch_raises(client):
    """Illustrious style with Qwen engine should fail roll (no qwen styles)."""
    r = client.post(
        "/api/build",
        json={
            "character": DEFAULT_CHARACTER_SLUG,
            "style": DEFAULT_STYLE_SLUG,
            "engine": MAKE_ENGINE_QWEN,
            "animation": "none",
            "seed": 1,
        },
    )
    assert r.status_code == 400, r.text
