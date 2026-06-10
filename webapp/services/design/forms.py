"""Form-parsing helpers shared by all route modules.

Includes:

- tag-list / int / float / bool / dialogue parsing
- ``save_uploaded_image()`` for the optional reference image on
  characters, animations, styles (multipart upload, saved
  under ``dataset/uploads/<entity>/<slug>.<ext>``)
- ``apply_inline_lora()`` for the inline LoRA fields on character / act /
  style forms. The LoRA row is created/updated/cleared in lockstep with
  the parent entity — there is no top-level LoRA UI.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from ...config import UPLOADS_DIR, UPLOADS_URL_PREFIX, UPLOADS_URL_PREFIX
from ...db.models import Lora


# ---------------------------------------------------------------------------
# Scalar parsers
# ---------------------------------------------------------------------------


def parse_taglist(raw: str | None) -> list[str]:
    """Split a comma-and-or-newline separated string into a clean ordered list."""
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in raw.replace(",", "\n").splitlines():
        tag = line.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def joined(values: Iterable[str] | None) -> str:
    """Render a tag list back into the textarea-friendly form ("one per line")."""
    if not values:
        return ""
    return "\n".join(values)


def parse_bool(value: str | None) -> bool:
    return str(value or "").lower() in ("1", "true", "on", "yes", "y")


def parse_int(value: str | None, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_dialogue_block(raw: str | None) -> list[tuple[str | None, str]]:
    """Parse a dialogue textarea.

    Each non-empty line is one line. Optional ``delivery:`` prefix splits
    on the first colon. Returns ``(delivery_or_None, line_text)`` pairs.
    """
    if not raw:
        return []
    out: list[tuple[str | None, str]] = []
    for raw_line in raw.splitlines():
        s = raw_line.strip()
        if not s:
            continue
        if ":" in s:
            head, body = s.split(":", 1)
            head_s = head.strip()
            body_s = body.strip()
            if head_s and body_s and len(head_s) <= 48:
                out.append((head_s, body_s))
                continue
        out.append((None, s))
    return out


def render_dialogue_block(rows: Iterable[tuple[str | None, str]]) -> str:
    """Render dialogue rows back into one-line-per-row text."""
    out: list[str] = []
    for delivery, line in rows:
        if delivery:
            out.append(f"{delivery}: {line}")
        else:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
_SLUG_SAFE = re.compile(r"[^a-z0-9_\-]+")


def _slugify(s: str) -> str:
    return _SLUG_SAFE.sub("-", (s or "").strip().lower()) or uuid.uuid4().hex[:8]


def save_uploaded_image(
    upload: Any | None,
    *,
    entity: str,
    slug: str,
    existing: str | None = None,
) -> str | None:
    """Persist a multipart ``UploadFile`` under ``dataset/uploads/<entity>/``.

    Returns the relative URL path that the templates can drop into an
    ``<img src=...>`` tag (e.g. ``/uploads/characters/alma.png``).

    - Returns ``existing`` unchanged if no new file was provided.
    - Returns ``None`` if the upload field was empty AND the form asked
      to clear the image (``clear_image=1``).
    - On a successful new upload, the previous image file (if any and
      different) is removed.
    """
    if upload is None:
        return existing
    filename = getattr(upload, "filename", None) or ""
    if not filename:
        return existing
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        return existing
    entity_dir = UPLOADS_DIR / entity
    entity_dir.mkdir(parents=True, exist_ok=True)
    base = _slugify(slug) or _slugify(Path(filename).stem)
    target = entity_dir / f"{base}{ext}"
    # avoid filename collisions across slugs by suffixing
    if target.exists() and existing != _public_url(target):
        i = 1
        while True:
            cand = entity_dir / f"{base}-{i}{ext}"
            if not cand.exists():
                target = cand
                break
            i += 1
    data = _read_upload(upload)
    if not data:
        return existing
    target.write_bytes(data)
    new_url = _public_url(target)
    # purge previous file if it lived under our managed uploads dir
    if existing and existing != new_url:
        _purge_image(existing)
    return new_url


def clear_uploaded_image(existing: str | None) -> None:
    """Delete an image file from disk if it lives under our uploads tree."""
    if existing:
        _purge_image(existing)


def _read_upload(upload: Any) -> bytes:
    """Read all bytes from a Starlette ``UploadFile`` or duck-typed object."""
    try:
        f = upload.file  # Starlette UploadFile exposes .file (SpooledTemporaryFile)
    except AttributeError:
        f = upload
    try:
        f.seek(0)
    except Exception:
        pass
    return f.read()


def _public_url(path: Path) -> str:
    """Convert a filesystem path under UPLOADS_DIR back to a public URL."""
    try:
        rel = path.relative_to(UPLOADS_DIR)
    except ValueError:
        return ""
    return UPLOADS_URL_PREFIX + "/" + rel.as_posix()


def _purge_image(public_url: str) -> None:
    """Delete the on-disk file for an uploads URL (current or legacy)."""
    rel: Path | None = None
    if public_url.startswith(UPLOADS_URL_PREFIX + "/"):
        rel = Path(public_url[len(UPLOADS_URL_PREFIX) + 1 :])
    elif public_url.startswith("/static/uploads/"):
        rel = Path(public_url[len("/static/uploads/") :])
    if rel is None:
        return
    target = UPLOADS_DIR / rel
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Inline LoRA editor
# ---------------------------------------------------------------------------


def apply_inline_lora(
    session,
    *,
    kind: str,
    filename: str,
    name: str,
    trigger: str | None,
    caption_trigger: str | None,
    strength: float | None,
    url: str | None,
    download_url: str | None,
    download_fallback_url: str | None,
    model_id: int | None,
    version_id: int | None,
    comment: str | None,
    existing_id: int | None = None,
) -> int | None:
    """Create / update / clear a LoRA row from inline parent-form fields.

    Returns the LoRA id to point the parent FK at (or ``None`` to unlink).

    - If ``filename`` is empty AND there's no existing row -> returns None
      (no LoRA wired up).
    - If ``filename`` is empty AND ``existing_id`` is set -> deletes that
      LoRA row (cascade unlink from parent) and returns None.
    - If ``filename`` matches an existing LoRA row's filename, that row is
      reused/updated (so two parents pointing at the same file share).
    - Otherwise the existing row (if any) is updated in place; if there
      was no existing row, a new one is inserted.
    """
    from sqlalchemy import select

    filename = (filename or "").strip()
    if not filename:
        if existing_id is not None:
            row = session.get(Lora, existing_id)
            if row is not None:
                session.delete(row)
        return None

    # Reuse-by-filename takes precedence over the previously-linked row.
    found = session.scalar(select(Lora).where(Lora.filename == filename))
    row = found or (session.get(Lora, existing_id) if existing_id is not None else None)
    if row is None:
        row = Lora(filename=filename, kind=kind, name=name or filename, strength=1.0)
        session.add(row)
        session.flush()

    row.kind = kind
    row.name = (name or filename).strip()
    row.filename = filename
    row.trigger = (trigger or "").strip() or None
    row.caption_trigger = (caption_trigger or "").strip() or None
    if strength is None:
        if row.strength is None:
            row.strength = 1.0
    else:
        row.strength = strength
    row.url = (url or "").strip() or None
    row.download_url = (download_url or "").strip() or None
    row.download_fallback_url = (download_fallback_url or "").strip() or None
    row.model_id = model_id
    row.version_id = version_id
    row.comment = (comment or "").strip() or None
    return row.id


def lora_form_fields(lora: Lora | None, *, pool_key: str = "") -> dict[str, str]:
    """Template context for inline LoRA editor fields."""
    if lora is None:
        out = {
            "filename": "",
            "name": "",
            "url": "",
            "download_url": "",
            "download_fallback_url": "",
            "model_id": "",
            "version_id": "",
            "trigger": "",
            "caption_trigger": "",
            "strength": "1.0",
            "comment": "",
        }
    else:
        out = {
            "filename": lora.filename or "",
            "name": lora.name or "",
            "url": lora.url or "",
            "download_url": lora.download_url or "",
            "download_fallback_url": lora.download_fallback_url or "",
            "model_id": str(lora.model_id) if lora.model_id is not None else "",
            "version_id": str(lora.version_id) if lora.version_id is not None else "",
            "trigger": lora.trigger or "",
            "caption_trigger": lora.caption_trigger or "",
            "strength": str(lora.strength if lora.strength is not None else 1.0),
            "comment": lora.comment or "",
        }
    if pool_key:
        out["pool_key"] = pool_key
    return out


def parse_inline_lora_form(form, prefix: str) -> dict[str, Any]:
    """Pull the inline LoRA fields out of a form using a given prefix.

    Returns the dict shape :func:`apply_inline_lora` expects (minus
    ``kind`` / ``existing_id`` which the caller supplies).
    """
    return {
        "filename": (form.get(f"{prefix}filename") or "").strip(),
        "name": (form.get(f"{prefix}name") or "").strip(),
        "trigger": (form.get(f"{prefix}trigger") or "").strip(),
        "caption_trigger": (form.get(f"{prefix}caption_trigger") or "").strip(),
        "strength": parse_optional_float(form.get(f"{prefix}strength")),
        "url": (form.get(f"{prefix}url") or "").strip(),
        "download_url": (form.get(f"{prefix}download_url") or "").strip(),
        "download_fallback_url": (form.get(f"{prefix}download_fallback_url") or "").strip(),
        "model_id": parse_optional_int(form.get(f"{prefix}model_id")),
        "version_id": parse_optional_int(form.get(f"{prefix}version_id")),
        "comment": (form.get(f"{prefix}comment") or "").strip(),
    }
