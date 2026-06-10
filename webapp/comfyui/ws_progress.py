"""Subscribe to ComfyUI ``/ws`` progress for a queued prompt."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any
from urllib.parse import quote

from .client import _comfyui_root
from .jobs import JobStore, job_store
from .make_lab.progress import INFERENCE_SAMPLER_NODE
from .progress import summarize_progress_state
from .prompt_match import matches_prompt_id
from .ws_binary import parse_preview_frame

_log = logging.getLogger(__name__)

_JOB_WS_TERMINAL = frozenset({"complete", "error", "cancelled"})


def _http_to_ws_url(base_url: str, client_id: str) -> str:
    root = base_url.rstrip("/")
    if root.startswith("https://"):
        ws_root = "wss://" + root[len("https://") :]
    elif root.startswith("http://"):
        ws_root = "ws://" + root[len("http://") :]
    else:
        ws_root = "ws://" + root
    return f"{ws_root}/ws?clientId={quote(client_id)}"


def _send_feature_flags(ws: Any) -> None:
    payload = json.dumps(
        {
            "type": "feature_flags",
            "data": {"supports_preview_metadata": True},
        }
    )
    ws.send(payload)


def connect_comfyui_ws(
    client_id: str,
    *,
    base_url: str | None = None,
    timeout: float = 15.0,
) -> tuple[Any | None, str | None]:
    """Open ``/ws?clientId=…`` and send feature flags before ``POST /prompt``."""
    try:
        import websocket
    except ImportError:
        return None, "websocket-client not installed"

    url = _http_to_ws_url(_comfyui_root(base_url), client_id)
    ws = websocket.WebSocket()
    try:
        ws.connect(url, timeout=timeout)
        _send_feature_flags(ws)
        ws.settimeout(0.25)
        return ws, None
    except Exception as exc:
        try:
            ws.close()
        except Exception:
            pass
        return None, str(exc)


def _job_tracker(store: JobStore, job_id: str):
    job = store.get(job_id)
    if job is None:
        return None, None
    return job, job._tracker()


def _activate_ws_prompt(
    store: JobStore,
    job_id: str,
    *,
    status: str | None = None,
) -> None:
    kwargs: dict[str, Any] = {"ws_prompt_active": True}
    if status is not None:
        kwargs["status"] = status
    store.update_progress(job_id, **kwargs)


def _apply_progress_state(
    store: JobStore,
    job_id: str,
    data: dict[str, Any],
    *,
    match_prompt_id: str,
) -> None:
    if not matches_prompt_id(data, match_prompt_id):
        return
    job, tr = _job_tracker(store, job_id)
    if job is None or tr is None or not tr.ws_prompt_active:
        return
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return
    summary = summarize_progress_state(nodes, match_prompt_id)
    nodes_finished = summary["nodes_finished"]
    if job is not None:
        nodes_finished = max(job.nodes_finished, nodes_finished)
    active_node = summary.get("active_node")
    store.update_progress(
        job_id,
        value=summary["value"],
        max_steps=summary["max"],
        nodes_finished=nodes_finished,
        node=str(active_node) if active_node else None,
        status="running",
    )


def _apply_binary_preview(store: JobStore, job_id: str, raw: bytes) -> None:
    parsed = parse_preview_frame(raw)
    if not parsed:
        return
    mime, image_bytes = parsed
    if not image_bytes:
        return
    store.update_live_preview(job_id, image_bytes, mime)


def _handle_message(
    store: JobStore,
    job_id: str,
    msg: dict[str, Any],
    *,
    match_prompt_id: str,
) -> bool:
    """Apply one WS message. Return True when the listener should stop."""
    msg_type = msg.get("type")
    data = msg.get("data")
    if not isinstance(data, dict):
        return False

    job = store.get(job_id)
    if job and job.status in _JOB_WS_TERMINAL:
        return True

    if msg_type == "execution_start":
        if not matches_prompt_id(data, match_prompt_id):
            return False
        job = store.get(job_id)
        if job and job.status == "fetching_assets":
            _activate_ws_prompt(store, job_id)
        else:
            _activate_ws_prompt(store, job_id, status="running")
        return False

    job, tr = _job_tracker(store, job_id)
    if tr is not None and not tr.ws_prompt_active:
        if msg_type in ("progress", "progress_state", "executing", "execution_cached"):
            if matches_prompt_id(data, match_prompt_id):
                _activate_ws_prompt(store, job_id)
                job, tr = _job_tracker(store, job_id)
        if tr is not None and not tr.ws_prompt_active:
            return False

    if msg_type == "progress_state":
        _apply_progress_state(store, job_id, data, match_prompt_id=match_prompt_id)
    elif msg_type == "progress":
        if not matches_prompt_id(data, match_prompt_id):
            return False
        node = data.get("node")
        job = store.get(job_id)
        kwargs: dict[str, Any] = {
            "value": int(round(float(data.get("value") or 0))),
            "max_steps": int(round(float(data.get("max") or 0))),
            "node": str(node) if node is not None else None,
        }
        if not (job and job.status == "fetching_assets"):
            kwargs["status"] = "running"
        store.update_progress(job_id, **kwargs)
    elif msg_type == "executing":
        if not matches_prompt_id(data, match_prompt_id):
            return False
        node = data.get("node")
        job = store.get(job_id)
        exec_kwargs: dict[str, Any] = {
            "mark_previous_node_done": True,
            "reset_steps": True,
        }
        if not (job and job.status == "fetching_assets"):
            exec_kwargs["status"] = "running"
        if node is None or node == "":
            store.update_progress(job_id, **exec_kwargs)
            return False
        exec_kwargs["node"] = str(node)
        store.update_progress(job_id, **exec_kwargs)
    elif msg_type == "execution_cached":
        if not matches_prompt_id(data, match_prompt_id):
            return False
        store.update_progress(
            job_id,
            mark_previous_node_done=True,
            increment_nodes_finished=1,
            reset_steps=True,
            status="running",
        )
        job, tr = _job_tracker(store, job_id)
        if job is not None and tr is not None and job.node:
            tr.mark_node_done(job.node)
    elif msg_type == "execution_success":
        if not matches_prompt_id(data, match_prompt_id):
            return False
        job = store.get(job_id)
        if job and job.status == "fetching_assets":
            store.set_asset_fetch_progress(job_id, 1.0)
            return False
        store.mark_inference_complete(job_id)

    job = store.get(job_id)
    if job and job.status == "downloading":
        return True
    return bool(job and job.status in _JOB_WS_TERMINAL)


def listen_ws_progress(
    client_id: str,
    job_id: str,
    *,
    ws: Any | None = None,
    base_url: str | None = None,
    stop_event: threading.Event | None = None,
    match_prompt_id: str | None = None,
) -> None:
    """Recv loop until WS closes, *stop_event* is set, or the job finishes."""
    store = job_store()
    match_id = match_prompt_id or job_id
    own_ws = ws is None
    if own_ws:
        ws, err = connect_comfyui_ws(client_id, base_url=base_url)
        if ws is None:
            store.update_progress(
                job_id,
                ws_connected=False,
                ws_error=err or "WebSocket connect failed",
            )
            return
        store.update_progress(job_id, ws_connected=True, ws_error=None)

    assert ws is not None
    try:
        import websocket
    except ImportError:
        if own_ws:
            try:
                ws.close()
            except Exception:
                pass
        return

    try:
        while True:
            if stop_event and stop_event.is_set():
                break
            job = store.get(job_id)
            if job and (job.status in _JOB_WS_TERMINAL or job.status == "downloading"):
                break
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:
                _log.warning("ComfyUI WS recv ended for %s: %s", job_id, exc)
                store.update_progress(job_id, ws_error=str(exc))
                break
            if not raw:
                continue
            if isinstance(raw, bytes):
                job, tr = _job_tracker(store, job_id)
                if tr is not None and tr.ws_prompt_active:
                    if (
                        tr.active_node == INFERENCE_SAMPLER_NODE
                        or tr.phase_for_node(tr.active_node) is not None
                    ):
                        _apply_binary_preview(store, job_id, raw)
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and _handle_message(
                store, job_id, msg, match_prompt_id=match_id
            ):
                break
    finally:
        if own_ws:
            try:
                ws.close()
            except Exception:
                pass


def start_ws_progress_listener(
    client_id: str,
    job_id: str,
    *,
    ws: Any | None = None,
    base_url: str | None = None,
    stop_event: threading.Event | None = None,
    match_prompt_id: str | None = None,
) -> tuple[threading.Thread, threading.Event]:
    """Daemon recv loop on an already-connected socket (or connect in-thread)."""
    event = stop_event or threading.Event()
    thread = threading.Thread(
        target=listen_ws_progress,
        args=(client_id, job_id),
        kwargs={
            "ws": ws,
            "base_url": base_url,
            "stop_event": event,
            "match_prompt_id": match_prompt_id,
        },
        daemon=True,
        name=f"comfyui-ws-{job_id[:8]}",
    )
    thread.start()
    return thread, event
