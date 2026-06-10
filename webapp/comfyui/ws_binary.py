"""Parse ComfyUI WebSocket binary preview frames (KSampler latent previews)."""

from __future__ import annotations

import json
import struct

PREVIEW_IMAGE = 1
UNENCODED_PREVIEW_IMAGE = 2
PREVIEW_IMAGE_WITH_METADATA = 4

_MIME_BY_FORMAT = {
    1: "image/jpeg",
    2: "image/png",
    3: "image/webp",
    4: "image/gif",
}


def _mime_from_format(event_id: int, fmt: int) -> str:
    if event_id == 10:
        return "image/bmp" if fmt == 1 else "image/jpeg"
    if event_id == UNENCODED_PREVIEW_IMAGE:
        return "image/png"
    return _MIME_BY_FORMAT.get(fmt & 7, "image/jpeg")


def parse_preview_frame(raw: bytes) -> tuple[str, bytes] | None:
    """Return ``(mime_type, image_bytes)`` for a ComfyUI binary WS frame, else None."""
    if len(raw) < 8:
        return None

    event_id = struct.unpack(">I", raw[0:4])[0]

    if event_id == PREVIEW_IMAGE_WITH_METADATA:
        if len(raw) < 12:
            return None
        meta_length = struct.unpack(">I", raw[4:8])[0]
        end = 8 + meta_length
        if len(raw) <= end:
            return None
        mime = "image/jpeg"
        try:
            meta = json.loads(raw[8:end].decode("utf-8"))
            for key in ("mime_type", "image_type"):
                if key in meta:
                    mime = str(meta[key])
                    break
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return mime, raw[end:]

    if event_id not in (PREVIEW_IMAGE, UNENCODED_PREVIEW_IMAGE, 10):
        return None

    fmt = struct.unpack(">I", raw[4:8])[0]
    mime = _mime_from_format(event_id, fmt)
    return mime, raw[8:]
