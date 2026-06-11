"""ComfyUI HTTP client (health, queue, prompt, history, view)."""

from __future__ import annotations

import http.client
import json
import mimetypes
import ssl
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Literal

from ..env_settings import load_comfyui_base_url, normalize_comfyui_base_url

ComfyuiActivityState = Literal["offline", "idle", "generating", "queued"]


class JobCancelled(Exception):
    """Raised when ``wait_for_prompt`` is aborted via ``cancel_event``."""


class ComfyUIRequestError(Exception):
    """ComfyUI returned an HTTP error (server reachable, request rejected)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        body: dict[str, Any] | None = None,
        url: str | None = None,
    ) -> None:
        self.status_code = int(status_code)
        self.message = message
        self.body = body
        self.url = url
        super().__init__(message)


def _read_http_error_body(exc: urllib.error.HTTPError) -> dict[str, Any] | None:
    try:
        raw = exc.read()
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def format_comfyui_error_message(body: dict[str, Any] | None) -> str:
    """Turn ComfyUI ``/prompt`` validation JSON into a short user-facing message."""
    if not body:
        return "ComfyUI rejected the workflow."

    messages: list[str] = []
    node_errors = body.get("node_errors")
    if isinstance(node_errors, dict):
        for node_id, info in node_errors.items():
            if not isinstance(info, dict):
                continue
            class_type = str(info.get("class_type") or "").strip()
            label = class_type or f"node {node_id}"
            for err in info.get("errors") or []:
                if not isinstance(err, dict):
                    continue
                msg = str(err.get("message") or "").strip()
                if not msg:
                    continue
                messages.append(f"{label}: {msg}")

    if messages:
        seen: set[str] = set()
        unique: list[str] = []
        for m in messages:
            if m in seen:
                continue
            seen.add(m)
            unique.append(m)
        if len(unique) == 1:
            return unique[0]
        return "; ".join(unique[:3])

    top = body.get("error")
    if isinstance(top, dict):
        parts = [
            str(top.get("message") or "").strip(),
            str(top.get("details") or "").strip(),
        ]
        text = ": ".join(p for p in parts if p)
        if text:
            return text
    if isinstance(top, str) and top.strip():
        return top.strip()
    return "ComfyUI rejected the workflow (validation failed)."


def _fetch_json(
    url: str, *, timeout: float = 3.0, method: str = "GET", body: Any = None
) -> Any:
    headers = {"User-Agent": "ComfySprites/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw or not raw.strip():
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        err_body = _read_http_error_body(exc)
        message = format_comfyui_error_message(err_body)
        if exc.code != 400:
            message = f"ComfyUI HTTP {exc.code}: {message}"
        raise ComfyUIRequestError(exc.code, message, body=err_body, url=url) from exc


def _comfyui_root(base_url: str | None = None) -> str:
    return normalize_comfyui_base_url(base_url or load_comfyui_base_url())


def _fetch_comfyui(
    base_url: str | None,
    path: str,
    *,
    timeout: float = 3.0,
    method: str = "GET",
    body: Any = None,
) -> Any:
    root = _comfyui_root(base_url)
    return _fetch_json(f"{root}{path}", timeout=timeout, method=method, body=body)


def system_stats(
    base_url: str | None = None, *, timeout: float = 3.0
) -> dict[str, Any]:
    """``GET /system_stats`` — raises on network or HTTP errors."""
    return _fetch_comfyui(base_url, "/system_stats", timeout=timeout)


def list_upscale_models(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/upscale_models`` — filenames under ComfyUI upscale folder."""
    data = _fetch_comfyui(base_url, "/models/upscale_models", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_checkpoints(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/checkpoints`` — filenames under ComfyUI checkpoints folder."""
    data = _fetch_comfyui(base_url, "/models/checkpoints", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_loras(base_url: str | None = None, *, timeout: float = 10.0) -> list[str]:
    """``GET /models/loras`` — filenames under ComfyUI loras folder."""
    data = _fetch_comfyui(base_url, "/models/loras", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_controlnets(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/controlnet`` — filenames under ComfyUI controlnet folder."""
    data = _fetch_comfyui(base_url, "/models/controlnet", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_ultralytics_models(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/ultralytics`` — detector paths (e.g. ``bbox/face_yolov9c.pt``)."""
    data = _fetch_comfyui(base_url, "/models/ultralytics", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_sams_models(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/sams`` — SAM weight filenames."""
    data = _fetch_comfyui(base_url, "/models/sams", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_diffusion_models(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/diffusion_models`` — UNET / diffusion model filenames."""
    data = _fetch_comfyui(base_url, "/models/diffusion_models", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_text_encoders(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/text_encoders`` — CLIP / text encoder filenames."""
    data = _fetch_comfyui(base_url, "/models/text_encoders", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def list_vae_models(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[str]:
    """``GET /models/vae`` — VAE filenames."""
    data = _fetch_comfyui(base_url, "/models/vae", timeout=timeout)
    if not isinstance(data, list):
        return []
    return sorted(str(name) for name in data if name)


def get_queue(base_url: str | None = None, *, timeout: float = 3.0) -> dict[str, Any]:
    """``GET /queue`` — running and pending workflow items."""
    return _fetch_comfyui(base_url, "/queue", timeout=timeout)


def free_comfyui_memory(
    base_url: str | None = None,
    *,
    unload_models: bool = True,
    free_cache: bool = True,
    timeout: float = 30.0,
) -> None:
    """``POST /free`` — ``unload_models`` frees VRAM; ``free_cache`` runs GC + CUDA cache."""
    body: dict[str, bool] = {}
    if unload_models:
        body["unload_models"] = True
    if free_cache:
        body["free_memory"] = True
    if not body:
        return
    _fetch_comfyui(base_url, "/free", timeout=timeout, method="POST", body=body)


def interrupt_prompt(
    prompt_id: str, base_url: str | None = None, *, timeout: float = 10.0
) -> None:
    """``POST /interrupt`` — stop execution when ``prompt_id`` is currently running."""
    _fetch_comfyui(
        base_url,
        "/interrupt",
        timeout=timeout,
        method="POST",
        body={"prompt_id": prompt_id},
    )


def delete_queue_prompts(
    prompt_ids: list[str], base_url: str | None = None, *, timeout: float = 10.0
) -> None:
    """``POST /queue`` with ``delete`` — remove pending items by prompt id."""
    if not prompt_ids:
        return
    _fetch_comfyui(
        base_url,
        "/queue",
        timeout=timeout,
        method="POST",
        body={"delete": list(prompt_ids)},
    )


def prompt_in_queue(queue_body: dict[str, Any], prompt_id: str) -> bool:
    """True if ``prompt_id`` is running or pending on ComfyUI."""
    for key in ("queue_running", "queue_pending"):
        for item in queue_body.get(key) or []:
            if len(item) >= 2 and str(item[1]) == prompt_id:
                return True
    return False


def queue_prompt(
    workflow: dict[str, Any],
    base_url: str | None = None,
    *,
    client_id: str | None = None,
    timeout: float = 60.0,
) -> tuple[str, str]:
    """``POST /prompt`` — return ``(prompt_id, client_id)``."""
    cid = client_id or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "prompt": workflow,
        # Unique metadata so ComfyUI does not skip back-to-back identical graphs.
        "extra_data": {"create_time": int(time.time() * 1000)},
        "client_id": cid,
    }
    data = _fetch_comfyui(
        base_url, "/prompt", timeout=timeout, method="POST", body=payload
    )
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI /prompt did not return prompt_id")
    return str(prompt_id), cid


def get_history_item(
    prompt_id: str, base_url: str | None = None, *, timeout: float = 10.0
) -> dict[str, Any] | None:
    """``GET /history/{prompt_id}`` — ``None`` until the run is recorded."""
    data = _fetch_comfyui(base_url, f"/history/{prompt_id}", timeout=timeout)
    if not isinstance(data, dict):
        return None
    item = data.get(prompt_id)
    return item if isinstance(item, dict) else None


def _history_execution_done(item: dict[str, Any]) -> bool:
    status = item.get("status")
    if not isinstance(status, dict):
        return bool(item)
    if status.get("completed"):
        return True
    status_str = str(status.get("status_str") or "").strip().lower()
    return status_str in ("success", "error")


def _history_execution_error(item: dict[str, Any]) -> str | None:
    status = item.get("status")
    if not isinstance(status, dict):
        return None
    status_str = str(status.get("status_str") or "").strip().lower()
    if status_str != "error":
        return None
    messages = status.get("messages") or []
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, (list, tuple)) and len(msg) >= 2:
            parts.append(str(msg[1]))
        elif isinstance(msg, str):
            parts.append(msg)
    text = "; ".join(p.strip() for p in parts if p and str(p).strip())
    return text or "ComfyUI execution failed"


def wait_for_execution(
    prompt_id: str,
    base_url: str | None = None,
    *,
    timeout: float = 3600.0,
    poll_interval: float = 0.5,
    cancel_event: threading.Event | None = None,
    on_wait_poll: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Wait until ``prompt_id`` completes (no image outputs required)."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    saw_in_queue = False
    started = time.monotonic()

    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        try:
            in_queue = prompt_in_queue(get_queue(base_url), prompt_id)
            if in_queue:
                saw_in_queue = True

            item = get_history_item(prompt_id, base_url)
            if item and _history_execution_done(item):
                err = _history_execution_error(item)
                if err:
                    raise RuntimeError(err)
                if on_wait_poll is not None:
                    on_wait_poll(1.0)
                return item

            if not in_queue and saw_in_queue:
                for retry in range(15):
                    if on_wait_poll is not None:
                        on_wait_poll(min(1.0, (retry + 1) / 15.0))
                    time.sleep(0.2)
                    item = get_history_item(prompt_id, base_url)
                    if item and _history_execution_done(item):
                        err = _history_execution_error(item)
                        if err:
                            raise RuntimeError(err)
                        if on_wait_poll is not None:
                            on_wait_poll(1.0)
                        return item
                break
        except JobCancelled:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = exc
        if on_wait_poll is not None:
            elapsed = time.monotonic() - started
            on_wait_poll(min(0.95, elapsed / max(timeout * 0.5, 1.0)))
        time.sleep(poll_interval)

    msg = f"ComfyUI prompt {prompt_id} did not complete"
    if last_error:
        msg += f" ({last_error})"
    raise TimeoutError(msg)


def wait_for_prompt(
    prompt_id: str,
    base_url: str | None = None,
    *,
    timeout: float = 600.0,
    poll_interval: float = 0.5,
    cancel_event: threading.Event | None = None,
    on_wait_poll: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Wait until ``prompt_id`` leaves the queue and history has image outputs."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    saw_in_queue = False
    started = time.monotonic()

    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        try:
            in_queue = prompt_in_queue(get_queue(base_url), prompt_id)
            if in_queue:
                saw_in_queue = True

            item = get_history_item(prompt_id, base_url)
            if item and item.get("outputs"):
                if on_wait_poll is not None:
                    on_wait_poll(1.0)
                return item

            if not in_queue:
                if saw_in_queue:
                    for retry in range(15):
                        if on_wait_poll is not None:
                            on_wait_poll(min(1.0, (retry + 1) / 15.0))
                        time.sleep(0.2)
                        item = get_history_item(prompt_id, base_url)
                        if item and item.get("outputs"):
                            if on_wait_poll is not None:
                                on_wait_poll(1.0)
                            return item
                    break
                if time.monotonic() - started > 5.0:
                    break
        except Exception as exc:
            last_error = exc
        if on_wait_poll is not None:
            elapsed = time.monotonic() - started
            on_wait_poll(min(0.95, elapsed / max(timeout * 0.5, 1.0)))
        time.sleep(poll_interval)

    msg = f"ComfyUI prompt {prompt_id} finished without outputs"
    if last_error:
        msg += f" ({last_error})"
    raise TimeoutError(msg)


def _comfyui_http_connection(
    base_url: str | None, *, timeout: float
) -> tuple[http.client.HTTPConnection, str]:
    root = _comfyui_root(base_url)
    parsed = urllib.parse.urlparse(root)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = (parsed.path or "").rstrip("/")
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, port, timeout=timeout, context=ctx
        )
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    return conn, path


def upload_image_bytes(
    data: bytes,
    filename: str,
    base_url: str | None = None,
    *,
    timeout: float = 120.0,
    on_progress: Callable[[float], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """``POST /upload/image`` — return ComfyUI upload filename for Load Image."""
    boundary = f"ComfySpritesBoundary{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + data + footer

    conn, path_prefix = _comfyui_http_connection(base_url, timeout=timeout)
    upload_path = f"{path_prefix}/upload/image"
    headers = {
        "User-Agent": "ComfySprites/1.0",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    if on_progress is not None:
        on_progress(0.0)

    try:
        conn.connect()
        conn.putrequest("POST", upload_path)
        for key, value in headers.items():
            conn.putheader(key, value)
        conn.endheaders()

        total = len(body)
        sent = 0
        chunk_size = 64 * 1024
        while sent < total:
            if cancel_event is not None and cancel_event.is_set():
                conn.close()
                raise JobCancelled()
            chunk = body[sent : sent + chunk_size]
            conn.send(chunk)
            sent += len(chunk)
            if on_progress is not None and total > 0:
                on_progress(sent / total)

        response = conn.getresponse()
        raw = response.read()
        status = response.status
        conn.close()
    except JobCancelled:
        raise
    except OSError as exc:
        raise OSError(f"ComfyUI unreachable: {exc}") from exc

    if status < 200 or status >= 300:
        err_body = None
        if raw:
            try:
                parsed_body = json.loads(raw)
                if isinstance(parsed_body, dict):
                    err_body = parsed_body
            except json.JSONDecodeError:
                pass
        message = format_comfyui_error_message(err_body)
        if status != 400:
            message = f"ComfyUI HTTP {status}: {message}"
        raise ComfyUIRequestError(status, message, body=err_body, url=upload_path)

    if not raw:
        raise RuntimeError("ComfyUI /upload/image returned empty body")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ComfyUI /upload/image returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ComfyUI /upload/image returned unexpected payload")
    name = payload.get("name") or payload.get("filename")
    if not name:
        raise RuntimeError("ComfyUI /upload/image did not return a filename")
    if on_progress is not None:
        on_progress(1.0)
    return str(name)


def _collect_output_media(
    history_item: dict[str, Any],
    *,
    node_ids: list[str] | None,
    keys: tuple[str, ...],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    outputs = history_item.get("outputs") or {}
    if node_ids is not None:
        node_keys = [str(nid) for nid in node_ids]
    else:
        node_keys = list(outputs.keys())
    for node_key in node_keys:
        node_out = outputs.get(node_key)
        if not isinstance(node_out, dict):
            continue
        for key in keys:
            for item in node_out.get(key) or []:
                if isinstance(item, dict) and item.get("filename"):
                    refs.append(
                        {
                            "filename": str(item["filename"]),
                            "subfolder": str(item.get("subfolder") or ""),
                            "type": str(item.get("type") or "output"),
                        }
                    )
    return refs


def collect_output_images(
    history_item: dict[str, Any],
    *,
    node_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    """Flatten ``images`` entries from ComfyUI history output nodes.

    When ``node_ids`` is set, only those node keys are included (stable order).
    """
    return _collect_output_media(history_item, node_ids=node_ids, keys=("images",))


def collect_output_videos(
    history_item: dict[str, Any],
    *,
    node_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    """Flatten ``gifs`` / ``videos`` entries from VHS Video Combine outputs."""
    refs = _collect_output_media(
        history_item, node_ids=node_ids, keys=("gifs", "videos")
    )
    if refs:
        return refs
    return _collect_output_media(history_item, node_ids=node_ids, keys=("images",))


def view_image_request(
    filename: str,
    *,
    subfolder: str = "",
    type_: str = "output",
    base_url: str | None = None,
    timeout: float = 60.0,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> tuple[bytes, str]:
    """``GET /view`` — raw image bytes and content-type."""
    root = _comfyui_root(base_url)
    query = urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": type_}
    )
    url = f"{root}/view?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "ComfySprites/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type") or "image/png"
        total_raw = resp.headers.get("Content-Length")
        total: int | None = None
        if total_raw:
            try:
                total = int(total_raw)
            except ValueError:
                total = None
        if on_progress is not None:
            on_progress(0, total)
        if total is None or total <= 0:
            data = resp.read()
            if on_progress is not None:
                on_progress(len(data), len(data) if data else None)
            return data, content_type
        chunks: list[bytes] = []
        read = 0
        while True:
            block = resp.read(65536)
            if not block:
                break
            chunks.append(block)
            read += len(block)
            if on_progress is not None:
                on_progress(read, total)
        return b"".join(chunks), content_type


def queue_counts(queue_body: dict[str, Any]) -> tuple[int, int]:
    running = queue_body.get("queue_running") or []
    pending = queue_body.get("queue_pending") or []
    return len(running), len(pending)


def comfyui_activity_state(running: int, pending: int) -> ComfyuiActivityState:
    if running > 0:
        return "generating"
    if pending > 0:
        return "queued"
    return "idle"


def _status_payload(
    *,
    connected: bool,
    root: str,
    state: ComfyuiActivityState,
    error: str | None = None,
    running_count: int = 0,
    pending_count: int = 0,
    resources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .crystools_monitor import empty_resources

    return {
        "connected": connected,
        "base_url": root,
        "error": error,
        "state": state,
        "running_count": running_count,
        "pending_count": pending_count,
        "resources": resources if resources is not None else empty_resources(),
    }


def check_comfyui_status(
    base_url: str | None = None, *, timeout: float = 3.0
) -> dict[str, Any]:
    """Reachability, queue snapshot, and resource usage for Photo/Video Lab."""
    from .crystools_monitor import empty_resources, fetch_comfyui_resources

    root = normalize_comfyui_base_url(base_url or load_comfyui_base_url())
    stats_body: dict[str, Any] | None = None
    try:
        stats_body = system_stats(root, timeout=timeout)
    except (urllib.error.HTTPError, ComfyUIRequestError) as exc:
        code = exc.status_code if isinstance(exc, ComfyUIRequestError) else exc.code
        return _status_payload(
            connected=False, root=root, state="offline", error=f"HTTP {code}"
        )
    except Exception as exc:
        return _status_payload(
            connected=False, root=root, state="offline", error=str(exc)
        )

    running_count = 0
    pending_count = 0
    queue_error: str | None = None
    try:
        running_count, pending_count = queue_counts(get_queue(root, timeout=timeout))
    except Exception as exc:
        queue_error = str(exc)

    resources = empty_resources()
    try:
        resources = fetch_comfyui_resources(
            root, stats=stats_body, monitor_timeout=max(timeout, 4.0)
        )
    except Exception:
        pass

    return _status_payload(
        connected=True,
        root=root,
        state=comfyui_activity_state(running_count, pending_count),
        error=queue_error,
        running_count=running_count,
        pending_count=pending_count,
        resources=resources,
    )
