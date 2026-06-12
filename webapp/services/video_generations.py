"""Persist Animate Lab video outputs."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT, VIDEOS_OUTPUT_URL_PREFIX
from ..db.models import Generation, VideoGeneration
from .generations import _image_file_exists, _public_image_url


def save_video_generation(
    session: Session,
    *,
    prompt_id: str,
    video_path: str,
    source_prompt_id: str,
    model_id: str,
    request: dict[str, Any],
    build: dict[str, Any],
) -> VideoGeneration:
    row = VideoGeneration(
        prompt_id=prompt_id,
        video_path=video_path,
        source_prompt_id=source_prompt_id,
        model_id=model_id,
        request_json=request,
        build_json=build,
    )
    session.add(row)
    return row


def _public_video_url(video_path: str) -> str:
    return f"{VIDEOS_OUTPUT_URL_PREFIX}/{Path(video_path).name}"


def _video_file_exists(video_path: str) -> bool:
    path = Path(video_path)
    if path.is_absolute():
        return path.is_file()
    return (PROJECT_ROOT / path).is_file()


def _source_still_url(session: Session, source_prompt_id: str | None) -> str | None:
    if not source_prompt_id:
        return None
    source = session.get(Generation, source_prompt_id)
    if source is None or not _image_file_exists(source.image_path):
        return None
    return _public_image_url(source.image_path)


def _row_to_history_item(row: VideoGeneration, session: Session) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    build = dict(row.build_json or {})
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    request = dict(row.request_json or {})
    animation_slug = request.get("animation_slug") or scene.get("animation")
    source_image_url = _source_still_url(session, row.source_prompt_id)
    source_kind = str(request.get("source_kind") or "make")
    return {
        "prompt_id": row.prompt_id,
        "video_url": _public_video_url(row.video_path),
        "image_url": source_image_url,
        "source_image_url": source_image_url,
        "source_prompt_id": row.source_prompt_id,
        "source_kind": source_kind,
        "model_id": row.model_id,
        "animation_slug": animation_slug,
        "character_slug": scene.get("character"),
        "background_slug": scene.get("location"),
        "style_slug": scene.get("style"),
        "created_at": created.isoformat(),
        "request": dict(row.request_json or {}),
        "build": build,
    }


def list_recent_video_generations(
    session: Session, *, limit: int = 25
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(VideoGeneration)
        .order_by(VideoGeneration.created_at.desc())
        .limit(limit)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not _video_file_exists(row.video_path):
            continue
        items.append(_row_to_history_item(row, session))
    return items
