"""Two-phase Make queue: download workflow before generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui import generate


def _build():
    return {
        "sdxl": {
            "checkpoint": {"filename": "base.safetensors"},
            "positive": "p",
            "negative": "n",
            "width": 512,
            "height": 512,
            "loras": [],
        },
        "scene": {"seed": 1},
    }


@patch("webapp.comfyui.generate._finish_generation_job")
@patch("webapp.comfyui.generate.start_ws_progress_listener")
@patch("webapp.comfyui.generate.connect_comfyui_ws", return_value=(None, None))
@patch(
    "webapp.comfyui.generate.queue_prompt",
    side_effect=[("dl-id", "c1"), ("make-id", "c1")],
)
@patch("webapp.comfyui.generate.wait_for_execution")
@patch("webapp.comfyui.generate.assets_ready", return_value=True)
@patch("webapp.comfyui.generate.missing_assets")
@patch("webapp.comfyui.generate.build_result_to_make_lab", return_value={"n": {}})
@patch("webapp.comfyui.generate.workflow_node_titles", return_value={})
@patch("webapp.comfyui.generate.build_progress_plan")
@patch(
    "webapp.comfyui.generate.build_asset_download_workflow",
    return_value={"asset_downloader": {}, "asset_download_output": {}},
)
def test_run_make_job_queues_download_then_make(
    _dl_wf,
    _plan,
    _titles,
    _make_wf,
    mock_missing,
    _ready,
    mock_wait_exec,
    mock_queue,
    _ws,
    _ws_listen,
    _finish,
):
    mock_missing.return_value = {
        "checkpoints": [{"filename": "base.safetensors"}],
        "loras": [],
        "controlnets": [],
    }
    store = generate.job_store()
    job_id = "job-test-1"
    store.create(
        job_id,
        "client-1",
        lab="make",
        base_url="http://127.0.0.1:8188",
        build=_build(),
    )
    generate._run_make_job(
        job_id,
        _build(),
        base_url="http://127.0.0.1:8188",
        wait_timeout=30.0,
        batch_size=1,
        client_id="client-1",
    )
    assert mock_queue.call_count == 2
    mock_wait_exec.assert_called_once()
    _finish.assert_called_once()
    job = store.get(job_id)
    assert job is not None
    assert job.comfy_prompt_id == "make-id"
    assert job.asset_download_prompt_id == "dl-id"
