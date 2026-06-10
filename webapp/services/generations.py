"""Persist Make request + build metadata for photo outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import PHOTOS_OUTPUT_URL_PREFIX, PROJECT_ROOT
from .sdxl.composer import BuildPayload
from ..db.models import Generation, _utcnow

_REQUEST_METADATA_EXCLUDE = frozenset({"generation_count", "batch_index"})
_RANDOM_SLOT = frozenset({"random", ""})


def request_from_payload(payload: BuildPayload) -> dict[str, Any]:
    """JSON-serializable echo of Make ``BuildPayload`` (minus UI-only fields)."""
    data = payload.model_dump(mode="json", exclude_none=True)
    for key in _REQUEST_METADATA_EXCLUDE:
        data.pop(key, None)
    return data


def _request_slot_needs_resolution(request: dict[str, Any], key: str) -> bool:
    if key not in request:
        return True
    raw = request.get(key)
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in _RANDOM_SLOT
    return False


def resolve_request_from_build(
    request: dict[str, Any], build: dict[str, Any]
) -> dict[str, Any]:
    out = dict(request)
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    for req_key, scene_key in (
        ("character", "character"),
        ("animation", "animation"),
        ("style", "style"),
        ("location", "location"),
        ("orientation", "orientation"),
    ):
        scene_val = scene.get(scene_key)
        if scene_val is None:
            continue
        if _request_slot_needs_resolution(out, req_key):
            out[req_key] = scene_val
    if _request_slot_needs_resolution(out, "partner"):
        partner = scene.get("partner")
        out["partner"] = partner if partner else "none"
    refine_style = scene.get("refine_style")
    if refine_style is not None and _request_slot_needs_resolution(out, "refine_style"):
        out["refine_style"] = refine_style
    return out


def request_with_resolved_seed(
    request: dict[str, Any], build: dict[str, Any]
) -> dict[str, Any]:
    out = dict(request)
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}
    scene_seed = scene.get("seed")
    if scene_seed is not None:
        out["seed"] = scene_seed
    return out


def enrich_photo_request_from_build(
    request: dict[str, Any], build: dict[str, Any]
) -> dict[str, Any]:
    out = dict(request)
    sdxl = build.get("sdxl") if isinstance(build.get("sdxl"), dict) else {}
    checkpoint = sdxl.get("checkpoint") if isinstance(sdxl.get("checkpoint"), dict) else {}
    scene = build.get("scene") if isinstance(build.get("scene"), dict) else {}

    for key in ("steps", "cfg_scale", "sampler", "scheduler"):
        if key not in out and key in checkpoint:
            out[key] = checkpoint[key]
    if "width" not in out and sdxl.get("width") is not None:
        out["width"] = sdxl["width"]
    if "height" not in out and sdxl.get("height") is not None:
        out["height"] = sdxl["height"]
    refine_style = scene.get("refine_style")
    if refine_style is not None and "refine_style" not in out:
        out["refine_style"] = refine_style
    return out


def request_for_storage(request: dict[str, Any], build: dict[str, Any]) -> dict[str, Any]:
    out = dict(request)
    for key in _REQUEST_METADATA_EXCLUDE:
        out.pop(key, None)
    out = request_with_resolved_seed(out, build)
    out = enrich_photo_request_from_build(out, build)
    return resolve_request_from_build(out, build)


def save_photo_generation(
    session: Session,
    *,
    prompt_id: str,
    image_path: str,
    request: dict[str, Any],
    build: dict[str, Any],
    created_at: datetime | None = None,
) -> bool:
    if session.get(Generation, prompt_id) is not None:
        return False
    stored_build = dict(build)
    stored_build.pop("ltx", None)
    row = Generation(
        prompt_id=prompt_id,
        image_path=image_path,
        created_at=created_at or _utcnow(),
        request_json=request_for_storage(request, build),
        build_json=stored_build,
    )
    session.add(row)
    return True


def clear_all_photo_generations(
    session: Session, *, delete_image_files: bool = True
) -> int:
    rows = session.scalars(select(Generation)).all()
    count = len(rows)
    if delete_image_files:
        seen: set[Path] = set()
        for row in rows:
            path = Path(row.image_path)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path in seen:
                continue
            seen.add(path)
            if path.is_file():
                path.unlink()
    session.execute(delete(Generation))
    return count


def _image_file_exists(image_path: str) -> bool:
    path = Path(image_path)
    if path.is_absolute():
        return path.is_file()
    return (PROJECT_ROOT / path).is_file()


def _public_image_url(image_path: str) -> str:
    return f"{PHOTOS_OUTPUT_URL_PREFIX}/{Path(image_path).name}"


def _scene_dict(build: dict[str, Any]) -> dict[str, Any]:
    scene = build.get("scene")
    return scene if isinstance(scene, dict) else {}


def _scene_partner_slug(scene: dict[str, Any], request: dict[str, Any]) -> str:
    raw = scene.get("partner")
    if raw is None:
        raw = request.get("partner")
    text = str(raw or "").strip()
    lowered = text.lower()
    if not text or lowered in _RANDOM_SLOT or lowered == "none":
        return "none"
    return text


def _scene_outfit_slug(scene: dict[str, Any], request: dict[str, Any]) -> str:
    raw = scene.get("outfit")
    if raw is None:
        raw = request.get("outfit")
    return str(raw or "").strip()


def _generation_to_history_item(row: Generation) -> dict[str, Any]:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    build = dict(row.build_json)
    request = resolve_request_from_build(
        request_with_resolved_seed(dict(row.request_json), build), build
    )
    scene = _scene_dict(build)
    seed = scene.get("seed")
    if seed is None:
        seed = request.get("seed")
    return {
        "prompt_id": row.prompt_id,
        "image_url": _public_image_url(row.image_path),
        "animation_slug": scene.get("animation") or scene.get("act"),
        "character_slug": scene.get("character"),
        "partner_slug": _scene_partner_slug(scene, request),
        "outfit_slug": _scene_outfit_slug(scene, request),
        "location_slug": scene.get("location"),
        "style_slug": scene.get("style"),
        "seed": seed,
        "created_at": created.isoformat(),
        "request": request,
        "build": build,
    }


def source_image_path(row: Generation) -> Path:
    path = Path(row.image_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def get_gallery_item(session: Session, prompt_id: str) -> dict[str, Any] | None:
    """Load one Make Lab output when the on-disk image still exists."""
    row = session.get(Generation, prompt_id)
    if row is None:
        return None
    if not _image_file_exists(row.image_path):
        return None
    return _generation_to_history_item(row)


def delete_gallery_item(session: Session, prompt_id: str) -> bool:
    """Remove one generation row and its output file."""
    row = session.get(Generation, prompt_id)
    if row is None:
        return False
    path = source_image_path(row)
    if path.is_file():
        path.unlink()
    session.delete(row)
    return True


def list_recent_photo_generations(
    session: Session, *, limit: int = 5
) -> list[dict[str, Any]]:
    capped = min(max(1, limit), 200)
    rows = session.scalars(
        select(Generation).order_by(Generation.created_at.desc()).limit(capped * 2)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        if len(items) >= capped:
            break
        if not _image_file_exists(row.image_path):
            continue
        items.append(_generation_to_history_item(row))
    return items
