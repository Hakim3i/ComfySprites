"""LTX Studio progress plan."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.comfyui.ltx_studio.progress import build_ltx_progress_plan
from webapp.comfyui.ltx_studio.workflow import patch_ltx_studio_workflow
from webapp.comfyui.make_lab.progress import PHASE_INFERENCE, ProgressTracker
from webapp.comfyui.jobs import job_store


def _patched_workflow():
    build = {
        "ltx": {
            "caption": "Test.",
            "negative": "#Video\nbad\n\n#Audio\nnoise",
            "loras": [],
        },
        "sdxl": {"width": 832, "height": 1216},
    }
    return patch_ltx_studio_workflow(
        comfy_image_name="source.png",
        model="ltx23_eros",
        width=832,
        height=1216,
        length_seconds=5,
        fps=24,
        seed=42,
        image_strength=0.95,
        audio_volume=100,
        cfg=1.0,
        loras=[],
        build=build,
        use_sulphur_experimental_lora=False,
    )


def test_ltx_progress_plan_splits_inference_phase():
    workflow = _patched_workflow()
    plan = build_ltx_progress_plan(workflow, {})
    inference_nodes = plan.phase_node_ids[PHASE_INFERENCE]
    assert "sampler_first_pass" in inference_nodes
    assert len(inference_nodes) >= 5
    assert len(plan.phase_node_ids["load"]) < len(workflow)


def test_ltx_sampler_steps_report_nonzero_progress():
    workflow = _patched_workflow()
    plan = build_ltx_progress_plan(workflow, {})
    tracker = ProgressTracker(plan=plan)
    tracker.ws_prompt_active = True
    tracker.active_node = "sampler_first_pass"
    tracker.value = 25
    tracker.max = 50
    assert tracker.overall_pct() > 0


def test_ltx_ws_progress_updates_job_pct():
    workflow = _patched_workflow()
    titles = {
        nid: str((node.get("_meta") or {}).get("title") or nid)
        for nid, node in workflow.items()
        if isinstance(node, dict)
    }
    plan = build_ltx_progress_plan(workflow, titles)
    store = job_store()
    job_id = "ltx-progress-test"
    store.create(
        job_id,
        "client-1",
        lab="animate",
        base_url="http://127.0.0.1:8188",
        build={},
        request={},
        workflow_node_count=len(workflow),
        node_titles=titles,
        progress_plan=plan,
    )
    store.update_progress(
        job_id,
        node="sampler_first_pass",
        value=20,
        max_steps=50,
        status="running",
        ws_prompt_active=True,
    )
    job = store.get(job_id)
    assert job is not None
    assert job.progress_pct() > 0
