"""Read CPU/GPU utilization from Crystools via ComfyUI ``/ws``."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import quote

from .client import _comfyui_root, system_stats

_log = logging.getLogger(__name__)

_RESOURCES_KEYS = ("cpu_pct", "ram_pct", "gpu_pct", "vram_pct")


def _http_to_ws_url(base_url: str, client_id: str) -> str:
    root = base_url.rstrip("/")
    if root.startswith("https://"):
        ws_root = "wss://" + root[len("https://") :]
    elif root.startswith("http://"):
        ws_root = "ws://" + root[len("http://") :]
    else:
        ws_root = "ws://" + root
    return f"{ws_root}/ws?clientId={quote(client_id)}"


def _norm_pct(value: Any) -> int | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return max(0, min(100, round(n)))


def _resources_from_crystools(data: dict[str, Any]) -> dict[str, int | None]:
    gpus = data.get("gpus") or []
    gpu0 = gpus[0] if gpus else {}
    return {
        "cpu_pct": _norm_pct(data.get("cpu_utilization")),
        "ram_pct": _norm_pct(data.get("ram_used_percent")),
        "gpu_pct": _norm_pct(gpu0.get("gpu_utilization")),
        "vram_pct": _norm_pct(gpu0.get("vram_used_percent")),
    }


def _resources_from_system_stats(stats: dict[str, Any]) -> dict[str, int | None]:
    ram_pct: int | None = None
    vram_pct: int | None = None
    sys_info = stats.get("system") or {}
    ram_total = sys_info.get("ram_total")
    ram_free = sys_info.get("ram_free")
    if ram_total and ram_free is not None and ram_total > 0:
        ram_pct = _norm_pct((ram_total - ram_free) / ram_total * 100)

    devices = stats.get("devices") or []
    if devices:
        dev = devices[0]
        vram_total = dev.get("vram_total")
        vram_free = dev.get("vram_free")
        if vram_total and vram_free is not None and vram_total > 0:
            vram_pct = _norm_pct((vram_total - vram_free) / vram_total * 100)

    return {
        "cpu_pct": None,
        "ram_pct": ram_pct,
        "gpu_pct": None,
        "vram_pct": vram_pct,
    }


def _merge_resources(
    primary: dict[str, int | None], fallback: dict[str, int | None]
) -> dict[str, int | None]:
    out = dict(fallback)
    for key in _RESOURCES_KEYS:
        if primary.get(key) is not None:
            out[key] = primary[key]
    return out


def empty_resources() -> dict[str, int | None]:
    return {key: None for key in _RESOURCES_KEYS}


def fetch_crystools_monitor(
    base_url: str | None = None, *, timeout: float = 4.0
) -> dict[str, int | None] | None:
    """Return Crystools ``crystools.monitor`` payload as pct fields, or ``None``."""
    try:
        import websocket
    except ImportError:
        _log.debug("websocket-client not installed; skipping Crystools monitor")
        return None

    root = _comfyui_root(base_url)
    client_id = str(uuid.uuid4())
    url = _http_to_ws_url(root, client_id)
    deadline = time.monotonic() + timeout
    ws = websocket.WebSocket()
    try:
        ws.connect(url, timeout=min(timeout, 8.0))
        ws.settimeout(0.5)
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except Exception:
                continue
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "crystools.monitor":
                data = msg.get("data")
                if isinstance(data, dict):
                    return _resources_from_crystools(data)
    except Exception as exc:
        _log.debug("Crystools monitor WebSocket failed: %s", exc)
        return None
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return None


def fetch_comfyui_resources(
    base_url: str | None = None,
    *,
    stats: dict[str, Any] | None = None,
    monitor_timeout: float = 4.0,
) -> dict[str, int | None]:
    """CPU/GPU from Crystools when available; RAM/VRAM fall back to ``system_stats``."""
    fallback = empty_resources()
    if stats is None:
        try:
            stats = system_stats(base_url, timeout=3.0)
        except Exception:
            stats = None
    if stats:
        fallback = _resources_from_system_stats(stats)

    crystools = fetch_crystools_monitor(base_url, timeout=monitor_timeout)
    if crystools is None:
        return fallback
    return _merge_resources(crystools, fallback)
