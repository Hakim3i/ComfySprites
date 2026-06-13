"""Chain ComfyUI ``LoraLoader`` nodes (replaces rgthree Power Lora Loader)."""

from __future__ import annotations

from typing import Any

LORA_LOADER_CLASS = "LoraLoader"
LORA_LOADER_MODEL_ONLY_CLASS = "LoraLoaderModelOnly"


def _active_loras(loras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lora in loras:
        if not isinstance(lora, dict):
            continue
        filename = (lora.get("filename") or "").strip()
        if not filename:
            continue
        strength = lora.get("strength")
        if strength is not None and float(strength) == 0.0:
            continue
        out.append(lora)
    return out


def _lora_strength(lora: dict[str, Any]) -> float:
    raw = lora.get("strength")
    if raw is None:
        return 1.0
    return float(raw)


def _purge_stack_nodes(
    workflow: dict[str, Any],
    *,
    tail_id: str,
    stack_prefix: str,
) -> None:
    for key in list(workflow.keys()):
        if key == tail_id:
            continue
        if key.startswith(f"{stack_prefix}:"):
            del workflow[key]
    if tail_id in workflow:
        node = workflow[tail_id]
        if isinstance(node, dict) and node.get("class_type") == LORA_LOADER_CLASS:
            del workflow[tail_id]


def apply_lora_loader_chain(
    workflow: dict[str, Any],
    *,
    tail_id: str,
    loras: list[dict[str, Any]],
    model_source: list[Any],
    clip_source: list[Any],
    stack_prefix: str,
    title_prefix: str = "LoRA",
    resolve_lora_name: Any | None = None,
) -> tuple[list[Any], list[Any]]:
    """Insert chained ``LoraLoader`` nodes; return (model_out, clip_out) link refs."""
    _purge_stack_nodes(workflow, tail_id=tail_id, stack_prefix=stack_prefix)
    active = _active_loras(loras)
    if not active:
        return model_source, clip_source

    model_in = model_source
    clip_in = clip_source
    last = len(active) - 1
    for index, lora in enumerate(active):
        node_id = tail_id if index == last else f"{stack_prefix}:{index}"
        strength = _lora_strength(lora)
        lora_name = (lora.get("filename") or "").strip()
        if resolve_lora_name is not None:
            lora_name = str(resolve_lora_name(lora_name) or lora_name).strip()
        workflow[node_id] = {
            "class_type": LORA_LOADER_CLASS,
            "_meta": {"title": f"{title_prefix} {index + 1}"},
            "inputs": {
                "model": model_in,
                "clip": clip_in,
                "lora_name": lora_name,
                "strength_model": strength,
                "strength_clip": strength,
            },
        }
        model_in = [node_id, 0]
        clip_in = [node_id, 1]
    return model_in, clip_in


def _purge_model_only_stack_nodes(
    workflow: dict[str, Any],
    *,
    tail_id: str,
    stack_prefix: str,
) -> None:
    for key in list(workflow.keys()):
        if key == tail_id:
            node = workflow[key]
            if (
                isinstance(node, dict)
                and node.get("class_type") == LORA_LOADER_MODEL_ONLY_CLASS
            ):
                del workflow[key]
            continue
        if key.startswith(f"{stack_prefix}:"):
            del workflow[key]


def apply_lora_loader_model_only_chain(
    workflow: dict[str, Any],
    *,
    tail_id: str,
    loras: list[dict[str, Any]],
    model_source: list[Any],
    stack_prefix: str,
    title_prefix: str = "LoRA",
    resolve_lora_name: Any | None = None,
) -> list[Any]:
    """Insert chained ``LoraLoaderModelOnly`` nodes; return model_out link ref."""
    _purge_model_only_stack_nodes(workflow, tail_id=tail_id, stack_prefix=stack_prefix)
    active = _active_loras(loras)
    if not active:
        return model_source

    model_in = model_source
    last = len(active) - 1
    for index, lora in enumerate(active):
        node_id = tail_id if index == last else f"{stack_prefix}:{index}"
        lora_name = (lora.get("filename") or "").strip()
        if resolve_lora_name is not None:
            lora_name = str(resolve_lora_name(lora_name) or lora_name).strip()
        workflow[node_id] = {
            "class_type": LORA_LOADER_MODEL_ONLY_CLASS,
            "_meta": {"title": f"{title_prefix} {index + 1}"},
            "inputs": {
                "model": model_in,
                "lora_name": lora_name,
                "strength_model": _lora_strength(lora),
            },
        }
        model_in = [node_id, 0]
    return model_in


def first_lora_loader_id(
    workflow: dict[str, Any],
    *,
    tail_id: str,
    stack_prefix: str,
) -> str | None:
    """First node in a stack (for ensure-node model/clip injection)."""
    candidates = [
        key
        for key in workflow
        if key == tail_id
        or (
            str(key).startswith(f"{stack_prefix}:")
            and workflow[key].get("class_type") == LORA_LOADER_CLASS
        )
    ]
    if not candidates:
        return None

    def _sort_key(node_id: str) -> tuple[int, str]:
        if node_id == tail_id:
            return (10_000, node_id)
        suffix = str(node_id).split(":", 1)[-1]
        try:
            return (int(suffix), node_id)
        except ValueError:
            return (9_999, node_id)

    return sorted(candidates, key=_sort_key)[0]


def rewire_lora_model_consumers(
    workflow: dict[str, Any],
    *,
    model_ref: list[Any],
    previous_model_nodes: str | list[str],
) -> None:
    """Point nodes that read model from any *previous_model_nodes* at *model_ref*."""
    if isinstance(previous_model_nodes, str):
        previous_model_nodes = [previous_model_nodes]
    wants = [[node_id, 0] for node_id in previous_model_nodes]
    tail_id = model_ref[0] if isinstance(model_ref, list) and model_ref else None
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == LORA_LOADER_CLASS:
            continue
        if node_id == tail_id:
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if inputs.get("model") in wants:
            inputs["model"] = model_ref
