"""Make Lab phase-weighted progress plan and calculator."""

from __future__ import annotations

import pytest

from webapp.comfyui.jobs import job_store
from webapp.comfyui.make_lab.detailers import compose_detailer_stages
from webapp.comfyui.make_lab.progress import (
    PHASE_DETAILERS,
    PHASE_EXPORT,
    PHASE_INFERENCE,
    PHASE_LOAD,
    PHASE_REFINE,
    PHASE_UPSCALE,
    INFERENCE_SAMPLER_NODE,
    ProgressTracker,
    build_progress_plan,
    classify_node_phase,
)
from webapp.comfyui.workflow import (
    _MAKE_LAB_NODES,
    load_make_lab_workflow,
    prepare_make_lab_workflow,
    workflow_node_titles,
)


@pytest.fixture(autouse=True)
def _clear_global_job_store():
    job_store()._jobs.clear()
    yield
    job_store()._jobs.clear()


def test_classify_known_nodes():
    wf = load_make_lab_workflow()
    assert (
        classify_node_phase(
            "checkpoint_main",
            {"class_type": "CheckpointLoaderSimple"},
            workflow=wf,
            detailer_timing=None,
            upscale_timing=None,
        )
        == PHASE_LOAD
    )
    assert (
        classify_node_phase(
            "sampler_main",
            {"class_type": "KSampler"},
            workflow=wf,
            detailer_timing=None,
            upscale_timing=None,
        )
        == PHASE_INFERENCE
    )
    assert (
        classify_node_phase(
            "sampler_refine",
            {"class_type": "KSampler"},
            workflow=prepare_make_lab_workflow(),
            detailer_timing=None,
            upscale_timing="after",
        )
        == PHASE_REFINE
    )
    assert (
        classify_node_phase(
            "detail:face:fd",
            {"class_type": "FaceDetailer"},
            workflow=wf,
            detailer_timing="after",
            upscale_timing=None,
        )
        == PHASE_DETAILERS
    )


def test_plan_renormalizes_when_no_detailers():
    workflow = load_make_lab_workflow()
    plan = build_progress_plan(workflow, workflow_node_titles(workflow))
    assert plan.detailer_count == 0
    assert PHASE_DETAILERS not in plan.phase_order
    assert PHASE_DETAILERS not in plan.phase_weights
    assert abs(sum(plan.phase_weights.values()) - 100.0) < 0.01
    assert plan.phase_weights[PHASE_INFERENCE] > 50.0


def test_plan_phase_order_detailers_before_refine():
    wf = prepare_make_lab_workflow()
    compose_detailer_stages(wf, ["face"], timing="before", pipeline_nodes=_MAKE_LAB_NODES)
    plan = build_progress_plan(wf, workflow_node_titles(wf))
    assert plan.phase_order.index(PHASE_DETAILERS) < plan.phase_order.index(PHASE_REFINE)
    assert plan.phase_step_nodes[PHASE_DETAILERS] == ("detail:face:fd",)
    assert "vae_encode" in plan.phase_node_ids[PHASE_REFINE]


def test_plan_phase_order_detailers_after_refine():
    wf = prepare_make_lab_workflow()
    compose_detailer_stages(wf, ["face"], timing="after", pipeline_nodes=_MAKE_LAB_NODES)
    plan = build_progress_plan(wf, workflow_node_titles(wf))
    assert plan.phase_order.index(PHASE_REFINE) < plan.phase_order.index(PHASE_DETAILERS)


def test_inference_only_stays_below_ninety_after_sampler():
    workflow = load_make_lab_workflow()
    plan = build_progress_plan(workflow, workflow_node_titles(workflow))
    tr = ProgressTracker(plan=plan)
    tr.ws_prompt_active = True
    tr.nodes_done.add(INFERENCE_SAMPLER_NODE)
    tr.active_node = "vae_decode_output"
    assert tr.overall_pct() < 90
    tr.nodes_done.add("vae_decode_output")
    tr.active_node = "export_image"
    assert tr.overall_pct() < 95
    assert PHASE_EXPORT in plan.phase_order
    assert "export_image" in plan.phase_node_ids[PHASE_EXPORT]


def test_inference_steps_stay_in_inference_band():
    workflow = load_make_lab_workflow()
    plan = build_progress_plan(workflow, workflow_node_titles(workflow))
    tr = ProgressTracker(plan=plan)
    tr.ws_prompt_active = True
    tr.active_node = INFERENCE_SAMPLER_NODE
    tr.value = 12
    tr.max = 25
    pct = tr.overall_pct()
    infer_w = plan.phase_weights[PHASE_INFERENCE]
    infer_nodes = plan.phase_node_ids[PHASE_INFERENCE]
    infer_frac = sum(
        (12 / 25 if nid == INFERENCE_SAMPLER_NODE else 0.0) for nid in infer_nodes
    ) / len(infer_nodes)
    expected = infer_w * infer_frac
    assert abs(pct - round(expected)) <= 1
    assert pct < 40
    assert plan.phase_weights[PHASE_INFERENCE] > plan.phase_weights[PHASE_LOAD]
    label = tr.executing_label()
    assert label is not None
    assert "Main Sampling" in label
    assert "12/25" in label


def test_detailer_steps_use_detailer_weight():
    wf = prepare_make_lab_workflow()
    compose_detailer_stages(wf, ["face"], timing="after", pipeline_nodes=_MAKE_LAB_NODES)
    plan = build_progress_plan(wf, workflow_node_titles(wf))
    tr = ProgressTracker(plan=plan)
    tr.ws_prompt_active = True
    tr.nodes_done.add("sampler_main")
    tr.nodes_done.add("sampler_refine")
    tr.active_node = "detail:face:fd"
    tr.value = 10
    tr.max = 20
    pct = tr.overall_pct()
    assert pct > 35
    label = tr.executing_label()
    assert label is not None
    assert "Face" in label
    assert "10/20" in label


def test_download_fraction_does_not_affect_workflow_pct():
    workflow = load_make_lab_workflow()
    plan = build_progress_plan(workflow, workflow_node_titles(workflow))
    tr = ProgressTracker(plan=plan)
    tr.mark_inference_complete()
    before = tr.overall_pct()
    tr.set_download_fraction(0.5)
    assert tr.overall_pct() == before == 100
    assert tr.download_pct() == 50
