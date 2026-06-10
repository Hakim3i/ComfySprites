"""In-memory ComfyUI generation jobs for Make progress polling."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .make_lab.progress import (
    PHASE_DOWNLOAD,
    INFERENCE_SAMPLER_NODE,
    PHASE_INFERENCE,
    PhotoStudioProgressPlan,
    ProgressTracker,
    build_progress_plan,
)

from builtins import max as builtins_max

_JOB_TERMINAL = frozenset({"complete", "error", "cancelled"})
_JOB_INFERENCE_DONE = frozenset({"downloading", "complete"})


@dataclass
class GenerationJob:
    prompt_id: str
    client_id: str
    lab: str = "make"  # make | video
    base_url: str = ""
    status: str = "queued"  # queued | fetching_assets | running | downloading | complete | error | cancelled
    comfy_prompt_id: str | None = None
    asset_download_prompt_id: str | None = None
    value: int = 0
    max: int = 0
    node: str | None = None
    workflow_node_count: int = 0
    nodes_finished: int = 0
    node_titles: dict[str, str] = field(default_factory=dict)
    preview_url: str | None = None
    preview_urls: list[str] = field(default_factory=list)
    image_ids: list[str] = field(default_factory=list)
    live_preview_url: str | None = None
    live_preview_bytes: bytes | None = None
    live_preview_mime: str | None = None
    build: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    error: str | None = None
    ws_connected: bool = False
    ws_error: str | None = None
    progress_peak: int = 0
    progress_plan: PhotoStudioProgressPlan | None = None
    tracker: ProgressTracker | None = None

    def _tracker(self) -> ProgressTracker:
        if self.tracker is None:
            plan = self.progress_plan or build_progress_plan(
                {}, node_titles=self.node_titles
            )
            self.tracker = ProgressTracker(plan=plan)
        return self.tracker

    def node_title(self) -> str | None:
        if self.node is None:
            return None
        plan = self.progress_plan
        if plan is not None:
            return plan.node_title(self.node)
        if str(self.node) in self.node_titles:
            return self.node_titles[str(self.node)]
        return str(self.node)

    def sampler_step_label(self) -> str | None:
        return self._tracker().sampler_step_label()

    def executing_label(self) -> str | None:
        if self.status == "fetching_assets":
            return "Fetching models"
        if self.status == "downloading":
            return self._tracker().download_label()
        return self._tracker().executing_label()

    def download_pct(self) -> int:
        return self._tracker().download_pct()

    def animation_slug(self) -> str | None:
        build = self.build or {}
        scene = build.get("scene")
        if isinstance(scene, dict):
            slug = scene.get("animation") or scene.get("act")
            if slug:
                return str(slug)
        req = self.request or {}
        slug = req.get("animation") or req.get("act")
        if slug:
            return str(slug)
        return None

    def act_slug(self) -> str | None:
        return self.animation_slug()

    def progress_pct(self) -> int:
        if self.status in ("complete", "downloading"):
            return 100
        if self.status == "fetching_assets":
            return min(99, self._tracker().download_pct())
        live = builtins_max(self.progress_peak, self._tracker().overall_pct())
        return min(99, live)

    def phase_id(self) -> str | None:
        return self._tracker().active_phase()

    def phase_label(self) -> str | None:
        phase = self.phase_id()
        if not phase:
            return None
        plan = self.progress_plan
        if plan is None:
            return phase
        return plan.phase_label(phase)

    def to_api(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "lab": self.lab,
            "status": self.status,
            "progress_pct": self.progress_pct(),
            "download_pct": self.download_pct(),
            "animation_slug": self.animation_slug(),
            "value": self.value,
            "max": self.max,
            "node": self.node,
            "node_title": self.node_title(),
            "sampler_step_label": self.sampler_step_label(),
            "executing_label": self.executing_label(),
            "phase": self.phase_id(),
            "phase_label": self.phase_label(),
            "preview_url": self.preview_url,
            "preview_urls": list(self.preview_urls),
            "image_ids": list(self.image_ids),
            "live_preview_url": self.live_preview_url,
            "build": self.build,
            "error": self.error,
            "ws_connected": self.ws_connected,
            "ws_error": self.ws_error,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, GenerationJob] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _is_terminal(job: GenerationJob) -> bool:
        return job.status in _JOB_TERMINAL

    def create(
        self,
        prompt_id: str,
        client_id: str,
        *,
        lab: str,
        base_url: str,
        build: dict[str, Any],
        request: dict[str, Any] | None = None,
        workflow_node_count: int = 0,
        node_titles: dict[str, str] | None = None,
        progress_plan: PhotoStudioProgressPlan | None = None,
    ) -> GenerationJob:
        plan = progress_plan
        titles = dict(node_titles or {})
        if plan is None and workflow_node_count > 0:
            plan = build_progress_plan({}, node_titles=titles)
        tracker = ProgressTracker(plan=plan) if plan is not None else None
        job = GenerationJob(
            prompt_id=prompt_id,
            client_id=client_id,
            lab=lab,
            base_url=base_url,
            build=build,
            request=dict(request or {}),
            workflow_node_count=workflow_node_count,
            node_titles=titles,
            progress_plan=plan,
            tracker=tracker,
        )
        with self._lock:
            self._jobs[prompt_id] = job
        return job

    def get(self, prompt_id: str) -> GenerationJob | None:
        with self._lock:
            return self._jobs.get(prompt_id)

    def set_comfy_prompt_id(self, job_id: str, comfy_prompt_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.comfy_prompt_id = comfy_prompt_id

    def set_asset_download_prompt_id(self, job_id: str, prompt_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.asset_download_prompt_id = prompt_id

    def begin_fetching_assets(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or self._is_terminal(job):
                return
            job.status = "fetching_assets"
            job.node = "asset_download"
            job.value = 0
            job.max = 0
            tr = job._tracker()
            tr.set_asset_fetch_fraction(0.0)

    def set_asset_fetch_progress(self, job_id: str, fraction: float) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or self._is_terminal(job) or job.status != "fetching_assets":
                return
            job._tracker().set_asset_fetch_fraction(fraction)

    def attach_workflow_plan(
        self,
        job_id: str,
        *,
        workflow: dict[str, Any],
        node_titles: dict[str, str],
        progress_plan: PhotoStudioProgressPlan,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or self._is_terminal(job):
                return
            job.workflow_node_count = len(workflow)
            job.node_titles = dict(node_titles)
            job.progress_plan = progress_plan
            job.tracker = ProgressTracker(plan=progress_plan)

    def _sync_tracker_from_job(self, job: GenerationJob) -> None:
        tr = job._tracker()
        tr.active_node = job.node
        tr.value = job.value
        tr.max = job.max

    def _bump_peak(self, job: GenerationJob) -> None:
        self._sync_tracker_from_job(job)
        job.progress_peak = builtins_max(
            job.progress_peak, job._tracker().overall_pct()
        )

    def update_progress(
        self,
        prompt_id: str,
        *,
        value: int | None = None,
        max_steps: int | None = None,
        node: str | None = None,
        nodes_finished: int | None = None,
        increment_nodes_finished: int = 0,
        reset_steps: bool = False,
        status: str | None = None,
        ws_connected: bool | None = None,
        ws_error: str | None = None,
        ws_prompt_active: bool | None = None,
        mark_previous_node_done: bool = False,
    ) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or self._is_terminal(job):
                return
            if job.status in _JOB_INFERENCE_DONE:
                return
            fetching_assets = job.status == "fetching_assets"
            if fetching_assets:
                if ws_connected is not None:
                    job.ws_connected = ws_connected
                if ws_error is not None:
                    job.ws_error = ws_error
                tr = job._tracker()
                if ws_prompt_active is not None:
                    tr.ws_prompt_active = ws_prompt_active
                if value is not None:
                    job.value = value
                if max_steps is not None:
                    job.max = max_steps
                if node is not None:
                    job.node = node
                if max_steps is not None and max_steps > 0 and value is not None:
                    tr.set_asset_fetch_fraction(value / max_steps)
                return
            if status:
                job.status = status
            elif job.status == "queued":
                job.status = "running"
            if ws_connected is not None:
                job.ws_connected = ws_connected
            if ws_error is not None:
                job.ws_error = ws_error
            tr = job._tracker()
            if ws_prompt_active is not None:
                tr.ws_prompt_active = ws_prompt_active
            if mark_previous_node_done and job.node:
                tr.mark_node_done(job.node)
            if reset_steps:
                job.value = 0
                job.max = 0
            if value is not None:
                job.value = value
            if max_steps is not None:
                job.max = max_steps
            if node is not None:
                job.node = node
            if nodes_finished is not None:
                job.nodes_finished = builtins_max(job.nodes_finished, nodes_finished)
            elif increment_nodes_finished:
                job.nodes_finished += increment_nodes_finished
            self._bump_peak(job)

    @staticmethod
    def _apply_inference_complete(job: GenerationJob) -> None:
        if job.status in _JOB_INFERENCE_DONE:
            return
        tr = job._tracker()
        tr.mark_inference_complete()
        job.status = "downloading"
        job.progress_peak = 100
        job.node = PHASE_DOWNLOAD

    def set_download_progress(
        self,
        prompt_id: str,
        fraction: float,
        *,
        label_node: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or self._is_terminal(job):
                return
            if job.status not in _JOB_INFERENCE_DONE:
                self._apply_inference_complete(job)
            tr = job._tracker()
            tr.set_download_fraction(fraction)
            if label_node:
                job.node = label_node

    def mark_inference_complete(self, prompt_id: str) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or self._is_terminal(job):
                return
            self._apply_inference_complete(job)

    def begin_finalize(self, prompt_id: str) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or self._is_terminal(job):
                return
            if job.status not in _JOB_INFERENCE_DONE:
                tr = job._tracker()
                tr.begin_finalize()
                job.status = "downloading"
                job.progress_peak = 100
                job.node = PHASE_DOWNLOAD
            else:
                tr = job._tracker()
                if tr.download_fraction <= 0.0:
                    tr.begin_finalize()

    def update_live_preview(
        self, prompt_id: str, image_bytes: bytes, mime: str
    ) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or self._is_terminal(job):
                return
            if job.status in _JOB_INFERENCE_DONE:
                return
            tr = job._tracker()
            if not tr.ws_prompt_active:
                return
            job.live_preview_bytes = image_bytes
            job.live_preview_mime = mime or "image/jpeg"
            job.live_preview_url = f"/api/comfyui/job/{prompt_id}/live-preview"
            if job.status == "queued":
                job.status = "running"
            phase = tr.phase_for_node(tr.active_node)
            if (
                phase == PHASE_INFERENCE
                and tr.active_node == INFERENCE_SAMPLER_NODE
                and tr.max > 0
            ):
                self._bump_peak(job)

    def get_live_preview(self, prompt_id: str) -> tuple[bytes, str] | None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or not job.live_preview_bytes:
                return None
            return job.live_preview_bytes, job.live_preview_mime or "image/jpeg"

    @staticmethod
    def _clear_live_preview(job: GenerationJob) -> None:
        job.live_preview_bytes = None
        job.live_preview_mime = None
        job.live_preview_url = None

    def cancel(self, prompt_id: str, *, message: str = "Cancelled") -> bool:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job or job.status in ("complete", "cancelled"):
                return False
            job.status = "cancelled"
            job.error = message
            self._clear_live_preview(job)
            return True

    def complete(
        self,
        prompt_id: str,
        *,
        preview_url: str,
        build: dict[str, Any] | None = None,
        preview_urls: list[str] | None = None,
        image_ids: list[str] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job:
                return
            if self._is_terminal(job):
                return
            job.status = "complete"
            job.preview_url = preview_url
            job.preview_urls = list(preview_urls if preview_urls is not None else [preview_url])
            job.image_ids = list(image_ids or [])
            job.progress_peak = 100
            tr = job._tracker()
            tr.set_download_fraction(1.0)
            job.value = job.max if job.max > 0 else 1
            job.max = job.max if job.max > 0 else 1
            if build is not None:
                job.build = build
            self._clear_live_preview(job)

    def fail(self, prompt_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(prompt_id)
            if not job:
                return
            if self._is_terminal(job):
                return
            job.status = "error"
            job.error = error
            self._clear_live_preview(job)


_STORE = JobStore()


def job_store() -> JobStore:
    return _STORE
