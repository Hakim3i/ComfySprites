"""Shared helpers for Power Lora Loader (rgthree) nodes."""

from __future__ import annotations

from typing import Any


def patch_power_lora_loader(inputs: dict[str, Any], loras: list[dict[str, Any]]) -> None:
    for key in list(inputs.keys()):
        if key.startswith("lora_"):
            del inputs[key]
    slot = 0
    for lora in loras:
        filename = (lora.get("filename") or "").strip()
        if not filename:
            continue
        slot += 1
        strength = float(
            lora.get("strength") if lora.get("strength") is not None else 1.0
        )
        inputs[f"lora_{slot}"] = {
            "on": True,
            "lora": filename,
            "strength": strength,
            "strengthTwo": strength,
        }
    if "PowerLoraLoaderHeaderWidget" not in inputs:
        inputs["PowerLoraLoaderHeaderWidget"] = {"type": "PowerLoraLoaderHeaderWidget"}
    if "➕ Add Lora" not in inputs:
        inputs["➕ Add Lora"] = ""
