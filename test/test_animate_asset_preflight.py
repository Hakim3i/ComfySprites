"""Animate Lab: download LTX catalog assets before generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui import animate_generate


@patch("webapp.comfyui.animate_generate._finish_animate_job")
@patch("webapp.comfyui.animate_generate.start_ws_progress_listener")
@patch(
    "webapp.comfyui.diffusion_asset_preflight.connect_comfyui_ws",
    return_value=(None, None),
)
@patch("webapp.comfyui.animate_generate.connect_comfyui_ws", return_value=(None, None))
@patch(
    "webapp.comfyui.diffusion_asset_preflight.queue_prompt",
    side_effect=[("dl-id", "c1")],
)
@patch("webapp.comfyui.animate_generate.queue_prompt", return_value=("anim-id", "c1"))
@patch("webapp.comfyui.diffusion_asset_preflight.wait_for_execution")
@patch("webapp.comfyui.animate_generate.resolve_diffusion_model_paths", return_value={})
@patch(
    "webapp.comfyui.diffusion_asset_preflight.build_asset_download_workflow",
    return_value={"asset_downloader": {}, "asset_download_output": {}},
)
@patch("webapp.comfyui.asset_inventory.list_loras", return_value=[])
@patch("webapp.comfyui.diffusion_asset_preflight.missing_diffusion_model_assets")
@patch("webapp.comfyui.animate_generate.patch_ltx_studio_workflow", return_value={"n": {}})
@patch("webapp.comfyui.animate_generate.build_ltx_progress_plan")
@patch("webapp.comfyui.animate_generate.resolve_ltx_fields", return_value={})
@patch("webapp.comfyui.animate_generate.build_ltx_from_generation")
@patch("webapp.comfyui.animate_generate._upload_source_image", return_value="upload.png")
def test_run_animate_job_queues_download_then_ltx(
    _upload,
    mock_build,
    _fields,
    _plan,
    _patch_wf,
    mock_missing,
    _list_loras,
    _dl_wf,
    _paths,
    mock_wait_exec,
    _anim_queue,
    _dl_queue,
    _ws_anim,
    _ws_dl,
    _ws_listen,
    _finish,
):
    empty_missing = {
        "diffusion_models": [],
        "text_encoders": [],
        "vae": [],
        "loras": [],
    }
    mock_missing.side_effect = [
        {
            "diffusion_models": [{"filename": "ltx2310eros_v1_FP8.safetensors"}],
            "text_encoders": [],
            "vae": [],
            "loras": [],
        },
        empty_missing,
    ]
    mock_build.return_value = {"ltx": {"loras": []}}
    store = animate_generate.job_store()
    job_id = "anim-job-1"
    store.create(
        job_id,
        "client-1",
        lab="animate",
        base_url="http://127.0.0.1:8188",
        build=None,
    )
    payload = type(
        "Payload",
        (),
        {
            "source_prompt_id": "src-1",
            "model_id": "ltx23_eros",
            "animation_slug": None,
            "lora_strengths": {},
            "width": None,
            "height": None,
            "length_seconds": 5,
            "fps": 24,
            "seed": 1,
            "image_strength": 0.95,
            "audio_volume": 100,
            "cfg": 1.0,
            "loras": None,
            "use_sulphur_experimental_lora": False,
        },
    )()
    source = MagicMock()
    with patch("webapp.comfyui.animate_generate.session_scope") as scope:
        scope.return_value.__enter__.return_value = MagicMock()
        animate_generate._run_animate_job(
            job_id,
            source=source,
            payload=payload,
            base_url="http://127.0.0.1:8188",
            wait_timeout=30.0,
            client_id="client-1",
        )
    mock_wait_exec.assert_called_once()
    job = store.get(job_id)
    assert job is not None
    assert job.asset_download_prompt_id == "dl-id"
    assert job.comfy_prompt_id == "anim-id"
