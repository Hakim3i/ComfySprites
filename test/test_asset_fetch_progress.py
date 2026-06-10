"""Asset-download progress: per-file bar divided across missing models."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.asset_inventory import count_missing_assets
from webapp.comfyui.jobs import job_store
from webapp.comfyui.ws_progress import _handle_message


def test_count_missing_assets():
    missing = {
        "checkpoints": [{"filename": "a.safetensors"}],
        "loras": [{"filename": "l.safetensors"}, {"filename": "l2.safetensors"}],
        "controlnets": [],
    }
    assert count_missing_assets(missing) == 3


def test_ws_progress_maps_multi_asset_download_fraction():
    store = job_store()
    job_id = "job-asset-progress"
    store.create(
        job_id,
        "client-1",
        lab="make",
        base_url="http://127.0.0.1:8188",
        build={},
    )
    store.begin_fetching_assets(job_id)

    _handle_message(
        store,
        job_id,
        {
            "type": "progress",
            "data": {
                "prompt_id": "dl-prompt",
                "node": "asset_downloader",
                "value": 1,
                "max": 3,
            },
        },
        match_prompt_id="dl-prompt",
    )

    job = store.get(job_id)
    assert job is not None
    assert job.status == "fetching_assets"
    assert job.progress_pct() == 33


def test_ws_execution_success_during_fetch_stays_fetching():
    store = job_store()
    job_id = "job-asset-done"
    store.create(
        job_id,
        "client-1",
        lab="make",
        base_url="http://127.0.0.1:8188",
        build={},
    )
    store.begin_fetching_assets(job_id)
    store.update_progress(job_id, ws_prompt_active=True)

    _handle_message(
        store,
        job_id,
        {"type": "execution_success", "data": {"prompt_id": "dl-prompt"}},
        match_prompt_id="dl-prompt",
    )

    job = store.get(job_id)
    assert job is not None
    assert job.status == "fetching_assets"
    assert job.progress_pct() == 99
