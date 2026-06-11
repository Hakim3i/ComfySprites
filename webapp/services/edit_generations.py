"""Persist Edit Lab image outputs."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EDIT_OUTPUT_URL_PREFIX, PROJECT_ROOT
from ..db.models import EditGeneration, Generation
from .generations import _image_file_exists, _public_image_url, source_image_path


def edit_image_path(row: EditGeneration) -> Path:
    path = Path(row.image_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def save_edit_generation(
    session: Session,
    *,
    prompt_id: str,
    image_path: str,
    source_prompt_id: str,
    source_kind: str,
    animation_slug: str | None,
    request: dict[str, Any],
    build: dict[str, Any],
) -> EditGeneration:
    row = EditGeneration(
        prompt_id=prompt_id,
        image_path=image_path,
        source_prompt_id=source_prompt_id,
        source_kind=source_kind,
        animation_slug=animation_slug,
        request_json=request,
        build_json=build,
    )
    session.add(row)
    return row


def _public_edit_url(image_path: str) -> str:
    return f"{EDIT_OUTPUT_URL_PREFIX}/{Path(image_path).name}"


def _source_still_url(
    session: Session, source_prompt_id: str | None, source_kind: str | None
) -> str | None:
    if not source_prompt_id:
        return None
    if source_kind == "edit":
        row = session.get(EditGeneration, source_prompt_id)
        if row is None or not _image_file_exists(row.image_path):
            return None
        return _public_edit_url(row.image_path)
    source = session.get(Generation, source_prompt_id)
    if source is None or not _image_file_exists(source.image_path):
        return None
    return _public_image_url(source.image_path)


def _row_to_history_item(row: EditGeneration, session: Session) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    build = dict(row.build_json or {})
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    request = dict(row.request_json or {})
    animation_slug = request.get("animation_slug") or row.animation_slug or scene.get(
        "animation"
    )
    return {
        "prompt_id": row.prompt_id,
        "image_url": _public_edit_url(row.image_path),
        "source_image_url": _source_still_url(
            session, row.source_prompt_id, row.source_kind
        ),
        "source_prompt_id": row.source_prompt_id,
        "source_kind": row.source_kind,
        "animation_slug": animation_slug,
        "character_slug": scene.get("character"),
        "background_slug": scene.get("location"),
        "style_slug": scene.get("style"),
        "created_at": created.isoformat(),
        "request": request,
        "build": build,
    }


def list_recent_edit_generations(
    session: Session, *, limit: int = 25
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(EditGeneration)
        .order_by(EditGeneration.created_at.desc())
        .limit(limit)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not _image_file_exists(row.image_path):
            continue
        items.append(_row_to_history_item(row, session))
    return items


def resolve_source_image_path(
    session: Session, *, source_prompt_id: str, source_kind: str
) -> Path:
    if source_kind == "edit":
        row = session.get(EditGeneration, source_prompt_id)
        if row is None:
            raise ValueError(f"Unknown or missing edit source {source_prompt_id!r}")
        path = edit_image_path(row)
        if not path.is_file():
            raise ValueError(f"Edit source image missing on disk for {source_prompt_id!r}")
        return path
    source = session.get(Generation, source_prompt_id)
    if source is None:
        raise ValueError(f"Unknown or missing source still {source_prompt_id!r}")
    path = source_image_path(source)
    if not path.is_file():
        raise ValueError(f"Source image missing on disk for {source_prompt_id!r}")
    return path
