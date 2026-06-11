"""Build ComfyUI API-format workflows from modular node files and pipeline recipes."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
NODES_DIR = WORKFLOWS_DIR / "nodes"
RECIPES_DIR = WORKFLOWS_DIR / "recipes"

_REF_PREFIX = "@"


@dataclass(frozen=True)
class BuiltWorkflow:
    workflow: dict[str, Any]
    pipeline: str
    roles: dict[str, str] = field(default_factory=dict)
    patch_roles: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    phases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def node(self, role: str) -> str:
        resolved = self.roles.get(role, role)
        if resolved not in self.workflow:
            raise KeyError(f"workflow missing node role {role!r} ({resolved!r})")
        return resolved

    def patch_role(self, key: str) -> str:
        role = self.patch_roles.get(key)
        if not role:
            raise KeyError(f"pipeline {self.pipeline!r} has no patch_roles[{key!r}]")
        return self.node(role)

    def output(self, key: str) -> str:
        role = self.outputs.get(key)
        if not role:
            raise KeyError(f"pipeline {self.pipeline!r} has no outputs[{key!r}]")
        return self.node(role)


def _load_pipeline_blueprint(name: str) -> dict[str, Any]:
    path = RECIPES_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"pipeline blueprint not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"pipeline blueprint must be a JSON object: {path}")
    return data


def load_node(pipeline: str, role: str) -> dict[str, Any]:
    path = NODES_DIR / pipeline / f"{role}.json"
    if not path.is_file():
        raise FileNotFoundError(f"node definition not found: {path}")
    return copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))


def resolve_refs(
    inputs: dict[str, Any],
    role_to_id: dict[str, str],
    external: dict[str, str] | None = None,
) -> dict[str, Any]:
    ext = external or {}
    out: dict[str, Any] = {}
    for key, val in inputs.items():
        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
            ref = val[0]
            if ref.startswith(_REF_PREFIX):
                role = ref[len(_REF_PREFIX) :]
                if role in role_to_id:
                    out[key] = [role_to_id[role], val[1]]
                elif ref in ext:
                    out[key] = [ext[ref], val[1]]
                else:
                    raise ValueError(f"unresolved ref {ref!r} in input {key!r}")
            elif ref in role_to_id:
                out[key] = [role_to_id[ref], val[1]]
            elif ref in ext:
                out[key] = [ext[ref], val[1]]
            else:
                out[key] = val
        else:
            out[key] = val
    return out


def _instantiate_node(
    pipeline: str,
    role: str,
    role_to_id: dict[str, str],
    external: dict[str, str] | None = None,
) -> dict[str, Any]:
    node = load_node(pipeline, role)
    node["inputs"] = resolve_refs(node.get("inputs") or {}, role_to_id, external)
    return node


def build_pipeline(
    name: str,
    *,
    external: dict[str, str] | None = None,
) -> BuiltWorkflow:
    blueprint = _load_pipeline_blueprint(name)
    pipeline_key = str(blueprint.get("pipeline") or name)
    node_roles = [str(r) for r in (blueprint.get("nodes") or [])]
    if not node_roles:
        raise ValueError(f"pipeline {name!r} has empty nodes list")

    workflow: dict[str, Any] = {}
    role_to_id: dict[str, str] = {}

    for role in node_roles:
        node = _instantiate_node(pipeline_key, role, role_to_id, external)
        workflow[role] = node
        role_to_id[role] = role

    roles = {role: role for role in node_roles}
    patch_roles = {
        str(k): str(v) for k, v in (blueprint.get("patch_roles") or {}).items()
    }
    outputs = {str(k): str(v) for k, v in (blueprint.get("outputs") or {}).items()}
    phases_raw = blueprint.get("phases") or {}
    phases = {
        str(phase): tuple(str(r) for r in roles_list)
        for phase, roles_list in phases_raw.items()
    }

    built = BuiltWorkflow(
        workflow=workflow,
        pipeline=name,
        roles=roles,
        patch_roles=patch_roles,
        outputs=outputs,
        phases=phases,
    )
    validate_built_workflow(built, blueprint)
    return built


def validate_built_workflow(
    built: BuiltWorkflow,
    blueprint: dict[str, Any] | None = None,
) -> None:
    bp = blueprint or _load_pipeline_blueprint(built.pipeline)
    wf = built.workflow

    for role in bp.get("nodes") or []:
        role = str(role)
        if role not in wf:
            raise ValueError(
                f"pipeline {built.pipeline!r} missing built node {role!r}"
            )

    expected_titles = bp.get("expected_titles") or {}
    for role, expected in expected_titles.items():
        role = str(role)
        node = wf.get(role)
        if not isinstance(node, dict):
            continue
        meta = node.get("_meta") or {}
        title = meta.get("title") if isinstance(meta, dict) else None
        if title and str(title) != str(expected):
            raise ValueError(
                f"node {role!r} title mismatch: expected {expected!r}, got {title!r}"
            )

    for patch_key, role in (bp.get("patch_roles") or {}).items():
        role = str(role)
        if role not in wf:
            raise ValueError(
                f"pipeline {built.pipeline!r} patch_roles[{patch_key!r}] "
                f"→ missing node {role!r}"
            )

    output_types = bp.get("output_types") or {}
    for out_key, class_type in output_types.items():
        role = str((bp.get("outputs") or {}).get(out_key) or out_key)
        node = wf.get(role)
        if not isinstance(node, dict) or node.get("class_type") != class_type:
            raise ValueError(
                f"pipeline {built.pipeline!r} output {out_key!r} ({role!r}) "
                f"must be {class_type!r}"
            )
