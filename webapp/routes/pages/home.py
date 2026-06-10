"""Home dashboard at ``/``."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from ...config import PHOTOS_OUTPUT_DIR
from ...db import (
    ENTITY_BACKGROUND,
    ENTITY_CHARACTER,
    ENTITY_MONSTER,
    ENTITY_OBJECT,
    ROLE_MAIN,
    ROLE_PARTNER,
    Animation,
    DesignEntity,
    Generation,
    Style,
    View,
    session_scope,
)
from ...revision import current_revision
from ...services.validate import run_validation

router = APIRouter()

_PHOTO_OUTPUT_EXTS = frozenset({".webp", ".jpg", ".jpeg", ".png"})


def _count_output_files(root, extensions: frozenset[str]) -> int:
    if not root.is_dir():
        return 0
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def dataset_counts() -> dict[str, int]:
    with session_scope() as s:
        counts = {
            "characters": s.scalar(
                select(func.count(DesignEntity.id)).where(
                    DesignEntity.entity_type == ENTITY_CHARACTER,
                    DesignEntity.role == ROLE_MAIN,
                )
            )
            or 0,
            "partners": s.scalar(
                select(func.count(DesignEntity.id)).where(
                    DesignEntity.entity_type == ENTITY_CHARACTER,
                    DesignEntity.role == ROLE_PARTNER,
                )
            )
            or 0,
            "monsters": s.scalar(
                select(func.count(DesignEntity.id)).where(
                    DesignEntity.entity_type == ENTITY_MONSTER
                )
            )
            or 0,
            "objects": s.scalar(
                select(func.count(DesignEntity.id)).where(
                    DesignEntity.entity_type == ENTITY_OBJECT
                )
            )
            or 0,
            "backgrounds": s.scalar(
                select(func.count(DesignEntity.id)).where(
                    DesignEntity.entity_type == ENTITY_BACKGROUND
                )
            )
            or 0,
            "animations": s.scalar(select(func.count(Animation.id))) or 0,
            "styles": s.scalar(select(func.count(Style.id))) or 0,
            "views": s.scalar(select(func.count(View.id))) or 0,
            "generations": s.scalar(select(func.count(Generation.prompt_id))) or 0,
        }
    counts["photos"] = max(counts["generations"], _count_output_files(PHOTOS_OUTPUT_DIR, _PHOTO_OUTPUT_EXTS))
    return counts


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    report = run_validation()
    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "active": "home",
            "counts": dataset_counts(),
            "revision": current_revision(),
            "validation": {
                "ok": report.ok,
                "count": report.count,
                "errors": report.errors,
                "warnings": report.warnings,
            },
        },
    )
