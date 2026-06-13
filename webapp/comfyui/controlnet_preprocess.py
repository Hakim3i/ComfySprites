"""Run ControlNet preprocessor nodes on ComfyUI for a source still."""

from __future__ import annotations

import base64
import uuid
from typing import Any

from ..services.catalog.controlnet_types import controlnet_type_spec
from .client import (
    ComfyUIRequestError,
    collect_output_images,
    queue_prompt,
    upload_image_bytes,
    view_image_request,
    wait_for_prompt,
)

_LOAD_NODE = "load_image"
_PREPROCESS_NODE = "preprocess"
_EXPORT_NODE = "export_image"
_TIMEOUT_S = 120.0


def build_controlnet_preprocess_workflow(
    comfy_image_name: str,
    *,
    cn_type: str,
) -> dict[str, Any]:
    spec = controlnet_type_spec(cn_type)
    if spec is None:
        raise ValueError(f"unknown ControlNet type {cn_type!r}")
    prep = spec.preprocessor
    if prep is None:
        raise ValueError(f"ControlNet type {cn_type!r} has no preprocessor configured")
    prep_inputs = dict(prep.inputs)
    prep_inputs["image"] = [_LOAD_NODE, 0]
    return {
        _LOAD_NODE: {
            "class_type": "LoadImage",
            "_meta": {"title": "Source image"},
            "inputs": {"image": comfy_image_name},
        },
        _PREPROCESS_NODE: {
            "class_type": prep.class_type,
            "_meta": {"title": f"{spec.label} preprocessor"},
            "inputs": prep_inputs,
        },
        _EXPORT_NODE: {
            "class_type": "SaveImage",
            "_meta": {"title": "Save preprocessor output"},
            "inputs": {
                "filename_prefix": "ControlNet_Preprocess",
                "images": [_PREPROCESS_NODE, 0],
            },
        },
    }


def run_controlnet_preprocess(
    image_bytes: bytes,
    *,
    cn_type: str,
    base_url: str | None = None,
    filename: str = "source.png",
) -> bytes:
    """Upload *image_bytes*, run the preprocessor workflow, return PNG bytes."""
    if not image_bytes:
        raise ValueError("empty source image")
    comfy_name = upload_image_bytes(image_bytes, filename, base_url=base_url)
    workflow = build_controlnet_preprocess_workflow(comfy_name, cn_type=cn_type)
    client_id = str(uuid.uuid4())
    prompt_id, _ = queue_prompt(workflow, base_url, client_id=client_id)
    history = wait_for_prompt(prompt_id, base_url, timeout=_TIMEOUT_S)
    images = collect_output_images(history, node_ids=[_EXPORT_NODE])
    if not images:
        raise RuntimeError("ControlNet preprocessor produced no output image")
    ref = images[0]
    body, _content_type = view_image_request(
        ref["filename"],
        subfolder=ref.get("subfolder") or "",
        type_=ref.get("type") or "output",
        base_url=base_url,
    )
    if not body:
        raise ComfyUIRequestError(502, "Failed to download ControlNet preprocessor output")
    return body


def controlnet_preprocess_data_url(
    image_bytes: bytes,
    *,
    cn_type: str,
    base_url: str | None = None,
    filename: str = "source.png",
) -> str:
    out = run_controlnet_preprocess(
        image_bytes, cn_type=cn_type, base_url=base_url, filename=filename
    )
    encoded = base64.b64encode(out).decode("ascii")
    return f"data:image/png;base64,{encoded}"
