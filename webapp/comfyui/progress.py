"""Parse ComfyUI WebSocket progress payloads (see ComfyUI ``progress_state``)."""

from __future__ import annotations

from typing import Any

from .prompt_match import matches_prompt_id


def summarize_progress_state(
    nodes: dict[str, Any], prompt_id: str
) -> dict[str, Any]:
    """Derive sampler step counts + finished node tally from ``progress_state``."""
    finished = 0
    best_value = 0
    best_max = 0
    best_node: str | None = None

    for node_key, state in nodes.items():
        if not isinstance(state, dict) or not matches_prompt_id(state, prompt_id):
            continue
        node_state = str(state.get("state") or "").lower()
        if node_state == "finished":
            finished += 1
            continue
        if node_state not in ("running", "executing"):
            continue
        value = int(round(float(state.get("value") or 0)))
        max_val = int(round(float(state.get("max") or 0)))
        if max_val > best_max or (max_val == best_max and value > best_value):
            best_value = value
            best_max = max_val
            best_node = str(state.get("node_id") or state.get("display_node_id") or node_key)

    return {
        "value": best_value,
        "max": best_max,
        "nodes_finished": finished,
        "active_node": best_node,
    }
