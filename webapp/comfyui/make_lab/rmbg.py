"""Compose Make Lab RMBG stage from nodes/rmbg.json (after detailers/upscale)."""



from __future__ import annotations



import copy

from typing import Any



from ..workflow_builder import load_node_template, registry_nodes



_EXPORT_IMAGE_NODE = registry_nodes()["export_image"]

_RMBG_NODE_ID = "rmbg:0"

_RMBG_INPUT_KEYS = frozenset(

    {

        "model",

        "sensitivity",

        "process_res",

        "mask_blur",

        "mask_offset",

        "invert_output",

        "refine_foreground",

        "background",

        "background_color",

    }

)





def load_rmbg_defaults() -> dict[str, Any]:

    """Default RMBG scalars from ``nodes/rmbg.json``."""

    tpl = load_node_template("rmbg")

    return dict(tpl.get("defaults") or {})





def rmbg_enabled_from_request(request: dict[str, Any] | None) -> bool:

    rmbg = (request or {}).get("rmbg")

    if isinstance(rmbg, dict):

        return bool(rmbg.get("enabled"))

    return False





def rmbg_settings_from_request(request: dict[str, Any] | None) -> dict[str, Any] | None:

    if not rmbg_enabled_from_request(request):

        return None

    out = load_rmbg_defaults()

    rmbg = (request or {}).get("rmbg")

    if isinstance(rmbg, dict):

        for key, val in rmbg.items():

            if key == "enabled" or key not in _RMBG_INPUT_KEYS:

                continue

            out[key] = val

    return out





def _instantiate_rmbg_node(

    image_source: list[Any],

    settings: dict[str, Any],

) -> dict[str, Any]:

    tpl = load_node_template("rmbg")

    inputs = copy.deepcopy(tpl.get("defaults") or {})

    for key, val in settings.items():

        if key in _RMBG_INPUT_KEYS:

            inputs[key] = val

    inputs["image"] = image_source

    return {

        "class_type": tpl["class_type"],

        "_meta": copy.deepcopy(tpl.get("_meta") or {}),

        "inputs": inputs,

    }





def apply_rmbg_stage(workflow: dict[str, Any], request: dict[str, Any] | None) -> str | None:

    """Insert RMBG node before ComfySprites export when enabled (mutates *workflow*)."""

    settings = rmbg_settings_from_request(request)

    if not settings:

        return None



    export = workflow.get(_EXPORT_IMAGE_NODE)

    if not isinstance(export, dict):

        raise ValueError(f"Make Lab export node {_EXPORT_IMAGE_NODE!r} missing")



    source = (export.get("inputs") or {}).get("images")

    if not isinstance(source, list) or len(source) < 2:

        raise ValueError("Make Lab export node has no image source to rewire")



    workflow[_RMBG_NODE_ID] = _instantiate_rmbg_node(source, settings)

    export.setdefault("inputs", {})["images"] = [_RMBG_NODE_ID, 0]

    return _RMBG_NODE_ID

