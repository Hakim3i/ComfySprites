"""Edit Lab: download Qwen edit assets before generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui import edit_generate
from webapp.comfyui.asset_inventory import (
    merge_extra_loras_into_missing,
    missing_diffusion_model_assets,
    missing_loras_from_rows,
)
from webapp.comfyui.download_workflow import build_asset_download_workflow
from webapp.db.models import Lora
from webapp.services.qwen.build import _apply_animation_qwen_edit


def test_missing_diffusion_model_assets_groups_by_folder():
    with (
        patch(
            "webapp.comfyui.asset_inventory.list_diffusion_models",
            return_value=[],
        ),
        patch(
            "webapp.comfyui.asset_inventory.list_text_encoders",
            return_value=[],
        ),
        patch(
            "webapp.comfyui.asset_inventory.list_vae_models",
            return_value=[],
        ),
        patch("webapp.comfyui.asset_inventory.list_loras", return_value=[]),
    ):
        missing = missing_diffusion_model_assets("qwen_edit_2511", "http://127.0.0.1:8188")
    assert missing["diffusion_models"]
    assert missing["text_encoders"]
    assert missing["vae"]
    assert missing["loras"]


def test_qwen_edit_lora_dict_includes_download_url_for_preflight():
    lora = Lora(
        kind="animation_qwen_edit",
        name="Epic Seven Run Qwen Edit",
        filename="Epic_Seven_Run_QwenEdit.safetensors",
        download_url="https://huggingface.co/Hakim3i/epic-seven-loras/resolve/main/Epic_Seven_Run_QwenEdit.safetensors",
        strength=1.0,
    )
    animation = type(
        "Animation",
        (),
        {
            "slug": "run",
            "qwen_edit_prompt": "Make the character run",
            "qwen_edit_lora": lora,
        },
    )()
    build = _apply_animation_qwen_edit({"scene": {}}, animation)
    loras = build["qwen_edit"]["loras"]
    assert loras[0]["download_url"]
    with patch("webapp.comfyui.asset_inventory.list_loras", return_value=[]):
        missing = missing_loras_from_rows(loras, "http://127.0.0.1:8188")
    assert missing[0]["filename"] == "Epic_Seven_Run_QwenEdit.safetensors"


def test_explicit_edit_loras_inherit_download_url_from_build():
    from webapp.comfyui.edit_generate import _loras_from_payload

    payload = type(
        "Payload",
        (),
        {
            "loras": [
                {
                    "kind": "qwen_edit",
                    "filename": "Epic_Seven_Run_QwenEdit.safetensors",
                    "strength": 1.0,
                }
            ],
            "lora_strengths": {},
        },
    )()
    build = {
        "qwen_edit": {
            "loras": [
                {
                    "kind": "qwen_edit",
                    "filename": "Epic_Seven_Run_QwenEdit.safetensors",
                    "download_url": "https://huggingface.co/Hakim3i/epic-seven-loras/resolve/main/Epic_Seven_Run_QwenEdit.safetensors",
                    "strength": 1.0,
                }
            ]
        }
    }
    loras = _loras_from_payload(payload, build)
    assert loras[0]["download_url"].endswith("Epic_Seven_Run_QwenEdit.safetensors")
    with patch("webapp.comfyui.asset_inventory.list_loras", return_value=[]):
        missing = missing_loras_from_rows(loras, "http://127.0.0.1:8188")
    assert missing[0]["filename"] == "Epic_Seven_Run_QwenEdit.safetensors"


def test_extra_loras_merged_into_missing():
    missing = {
        "diffusion_models": [],
        "text_encoders": [],
        "vae": [],
        "loras": [],
    }
    extra = [
        {
            "filename": "custom_qwen_lora.safetensors",
            "download_url": "https://example.com/custom_qwen_lora.safetensors",
        }
    ]
    with patch("webapp.comfyui.asset_inventory.list_loras", return_value=[]):
        merged = merge_extra_loras_into_missing(
            missing,
            extra,
            base_url="http://127.0.0.1:8188",
        )
    assert merged["loras"][0]["filename"] == "custom_qwen_lora.safetensors"


def test_build_edit_download_workflow():
    with (
        patch(
            "webapp.comfyui.asset_inventory.list_diffusion_models",
            return_value=[],
        ),
        patch(
            "webapp.comfyui.asset_inventory.list_text_encoders",
            return_value=[],
        ),
        patch(
            "webapp.comfyui.asset_inventory.list_vae_models",
            return_value=[],
        ),
        patch("webapp.comfyui.asset_inventory.list_loras", return_value=[]),
    ):
        missing = missing_diffusion_model_assets("qwen_edit_2511", "http://127.0.0.1:8188")
    wf = build_asset_download_workflow(missing, tokens={"civitai_token": "", "hf_token": ""})
    node = wf["asset_downloader"]
    assert node["inputs"]["diffusion_models_json"]
    assert node["inputs"]["text_encoders_json"]
    assert node["inputs"]["vae_json"]


@patch("webapp.comfyui.edit_generate.resolve_diffusion_model_paths", return_value={})
@patch("webapp.comfyui.edit_generate._finish_edit_job")
@patch("webapp.comfyui.edit_generate.start_ws_progress_listener")
@patch(
    "webapp.comfyui.diffusion_asset_preflight.connect_comfyui_ws",
    return_value=(None, None),
)
@patch("webapp.comfyui.edit_generate.connect_comfyui_ws", return_value=(None, None))
@patch(
    "webapp.comfyui.diffusion_asset_preflight.queue_prompt",
    side_effect=[("dl-id", "c1")],
)
@patch("webapp.comfyui.edit_generate.queue_prompt", return_value=("edit-id", "c1"))
@patch("webapp.comfyui.diffusion_asset_preflight.wait_for_execution")
@patch(
    "webapp.comfyui.diffusion_asset_preflight.build_asset_download_workflow",
    return_value={"asset_downloader": {}, "asset_download_output": {}},
)
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.diffusion_asset_preflight.missing_diffusion_model_assets")
@patch("webapp.comfyui.edit_generate.patch_qwen_edit_workflow", return_value={"n": {}})
@patch("webapp.comfyui.edit_generate.build_qwen_edit_progress_plan")
@patch("webapp.comfyui.edit_generate.resolve_source_image_path")
@patch("webapp.comfyui.edit_generate._upload_source_image", return_value="upload.png")
@patch("webapp.comfyui.edit_generate.resolve_qwen_edit_fields", return_value={})
@patch("webapp.comfyui.edit_generate.build_qwen_edit_from_generation")
def test_run_edit_job_queues_download_then_edit(
    mock_build,
    _fields,
    _upload,
    _src,
    _plan,
    _patch_wf,
    mock_missing,
    _list_loras,
    _dl_wf,
    mock_wait_exec,
    _edit_queue,
    _dl_queue,
    _ws_edit,
    _ws_dl,
    _ws_listen,
    _finish,
    _resolve_paths,
):
    mock_missing.side_effect = [
        {
            "diffusion_models": [{"filename": "QWEN/unet.safetensors"}],
            "text_encoders": [],
            "vae": [],
            "loras": [],
        },
        {
            "diffusion_models": [],
            "text_encoders": [],
            "vae": [],
            "loras": [],
        },
    ]
    mock_build.return_value = {"qwen_edit": {"loras": []}}
    store = edit_generate.job_store()
    job_id = "edit-job-1"
    store.create(
        job_id,
        "client-1",
        lab="edit",
        base_url="http://127.0.0.1:8188",
        build=None,
    )
    payload = type(
        "Payload",
        (),
        {
            "source_kind": "make",
            "source_prompt_id": "src-1",
            "model_id": "qwen_edit_2511",
            "lora_strengths": {},
            "seed": 1,
            "steps": 4,
            "cfg": 1.0,
            "image_strength": 1.0,
            "shift": 3.1,
            "loras": None,
        },
    )()
    session = MagicMock()
    session.get.return_value = MagicMock()
    with patch("webapp.comfyui.edit_generate.session_scope") as scope:
        scope.return_value.__enter__.return_value = session
        edit_generate._run_edit_job(
            job_id,
            source_path=Path("x.png"),
            payload=payload,
            base_url="http://127.0.0.1:8188",
            wait_timeout=30.0,
            client_id="client-1",
        )
    mock_wait_exec.assert_called_once()
    job = store.get(job_id)
    assert job is not None
    assert job.asset_download_prompt_id == "dl-id"
    assert job.comfy_prompt_id == "edit-id"
