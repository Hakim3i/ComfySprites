"""ComfyUI memory cleanup before Make generation."""

from __future__ import annotations

import logging
from typing import Any

from .client import free_comfyui_memory, system_stats

_log = logging.getLogger(__name__)

BYTES_PER_GB = 1024**3
MAKE_LAB_MIN_FREE_RAM_GB = 10
MAKE_LAB_MIN_FREE_VRAM_GB = 10
def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return n


def memory_free_bytes_from_stats(stats: dict[str, Any]) -> dict[str, int | None]:
    """Read ``ram_free`` / ``vram_free`` byte counts from ComfyUI ``system_stats``."""
    sys_info = stats.get("system") if isinstance(stats.get("system"), dict) else {}
    ram_free = _as_int(sys_info.get("ram_free"))
    ram_total = _as_int(sys_info.get("ram_total"))
    vram_free = vram_total = None
    devices = stats.get("devices")
    if isinstance(devices, list) and devices:
        dev = devices[0] if isinstance(devices[0], dict) else {}
        vram_free = _as_int(dev.get("vram_free"))
        vram_total = _as_int(dev.get("vram_total"))
    return {
        "ram_free": ram_free,
        "ram_total": ram_total,
        "vram_free": vram_free,
        "vram_total": vram_total,
    }


def needs_memory_cleanup(
    stats: dict[str, Any],
    *,
    min_free_ram_gb: float = MAKE_LAB_MIN_FREE_RAM_GB,
    min_free_vram_gb: float = MAKE_LAB_MIN_FREE_VRAM_GB,
) -> tuple[bool, bool]:
    """Return ``(low_ram, low_vram)`` when free bytes are under the thresholds."""
    free = memory_free_bytes_from_stats(stats)
    ram_threshold = int(min_free_ram_gb * BYTES_PER_GB)
    vram_threshold = int(min_free_vram_gb * BYTES_PER_GB)
    low_ram = free["ram_free"] is not None and free["ram_free"] < ram_threshold
    low_vram = free["vram_free"] is not None and free["vram_free"] < vram_threshold
    return low_ram, low_vram


def maybe_free_memory_before_make(
    base_url: str | None = None,
    *,
    stats: dict[str, Any] | None = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Call ComfyUI ``/free`` when free RAM or VRAM is below 10 GB."""
    fetched = stats
    if fetched is None:
        try:
            fetched = system_stats(base_url, timeout=timeout)
        except Exception as exc:
            _log.warning("Make memory check skipped: %s", exc)
            return {
                "cleaned": False,
                "low_ram": False,
                "low_vram": False,
                "error": str(exc),
            }

    low_ram, low_vram = needs_memory_cleanup(fetched)
    snapshot = memory_free_bytes_from_stats(fetched)
    if not low_ram and not low_vram:
        return {"cleaned": False, "low_ram": False, "low_vram": False, **snapshot}

    try:
        free_comfyui_memory(
            base_url,
            unload_models=True,
            free_cache=True,
            timeout=max(timeout, 30.0),
        )
        _log.info(
            "Make freed ComfyUI memory (low_ram=%s low_vram=%s)",
            low_ram,
            low_vram,
        )
        return {"cleaned": True, "low_ram": low_ram, "low_vram": low_vram, **snapshot}
    except Exception as exc:
        _log.warning("Make ComfyUI /free failed: %s", exc)
        return {
            "cleaned": False,
            "low_ram": low_ram,
            "low_vram": low_vram,
            "error": str(exc),
            **snapshot,
        }

