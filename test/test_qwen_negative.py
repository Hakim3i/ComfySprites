"""Qwen edit negative composition."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db.models import Animation, DesignEntity
from webapp.services.qwen.build import _apply_qwen_edit


def test_apply_qwen_edit_composes_negative_from_entities():
    build = {"scene": {"character": "c1", "location": "loc1", "animation": "a1"}}
    character = DesignEntity(slug="c1", display_name="C1", negative="bad hands")
    location = DesignEntity(slug="loc1", display_name="Loc", negative="crowd")
    animation = Animation(
        slug="a1",
        menu_name="Edit",
        qwen_edit_prompt="Make her smile",
        negative="blur",
    )
    out = _apply_qwen_edit(
        build,
        character=character,
        location=location,
        animation=animation,
    )
    qwen = out["qwen_edit"]
    assert qwen["prompt"] == "Make her smile"
    assert qwen["negative"] == "bad hands, crowd, blur"
