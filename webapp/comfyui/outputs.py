"""Download ComfyUI render output into ``outputs/make/`` and ``outputs/videos/``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import (
    EDIT_OUTPUT_DIR,
    EDIT_OUTPUT_URL_PREFIX,
    MAKE_OUTPUT_DIR,
    MAKE_OUTPUT_URL_PREFIX,
    VIDEOS_OUTPUT_DIR,
    VIDEOS_OUTPUT_URL_PREFIX,
)
from .client import view_image_request

# Download phase: first 30% while waiting for history, 70% while fetching files.
_DOWNLOAD_WAIT_BAND = 0.30


def _extension(filename: str, content_type: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"}:
        return ext
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct:
        return ".mp4"
    if "webm" in ct:
        return ".webm"
    return ".png"


def output_video_name(prompt_id: str, *, ext: str) -> str:
    """Public filename under ``outputs/videos/``."""
    suffix = ext if ext.startswith(".") else f".{ext}"
    return f"{prompt_id}{suffix}"


def output_make_name(prompt_id: str, *, ext: str) -> str:
    """Public filename under ``outputs/make/`` (ComfyUI source name not included)."""
    suffix = ext if ext.startswith(".") else f".{ext}"
    return f"{prompt_id}{suffix}"


def output_edit_name(prompt_id: str, *, ext: str) -> str:
    """Public filename under ``outputs/edit/``."""
    suffix = ext if ext.startswith(".") else f".{ext}"
    return f"{prompt_id}{suffix}"


def download_fraction_from_parts(
    *,
    wait_part: float = 0.0,
    file_index: int = 0,
    file_count: int = 1,
    file_part: float = 0.0,
) -> float:
    """Map wait + per-file download progress into 0–1 for the download phase."""
    wait_part = max(0.0, min(1.0, wait_part))
    file_part = max(0.0, min(1.0, file_part))
    count = max(1, file_count)
    file_band = 1.0 - _DOWNLOAD_WAIT_BAND
    per_file = file_band / count
    return (
        _DOWNLOAD_WAIT_BAND * wait_part + per_file * file_index + per_file * file_part
    )


def save_output_image(
    image_ref: dict[str, str],
    prompt_id: str,
    *,
    base_url: str | None = None,
    on_download_progress: Callable[[float], None] | None = None,
    output_dir: Path | None = None,
    url_prefix: str | None = None,
) -> tuple[Path, str]:
    """Fetch from ComfyUI ``/view`` and write ``outputs/<lab>/<file>``."""
    filename = image_ref["filename"]

    def _bytes_progress(read: int, total: int | None) -> None:
        if on_download_progress is None:
            return
        if total and total > 0:
            on_download_progress(read / total)
        elif read > 0:
            on_download_progress(1.0)

    data, content_type = view_image_request(
        filename,
        subfolder=image_ref.get("subfolder") or "",
        type_=image_ref.get("type") or "output",
        base_url=base_url,
        on_progress=_bytes_progress if on_download_progress else None,
    )
    ext = _extension(filename, content_type)
    dest_dir = output_dir or MAKE_OUTPUT_DIR
    prefix = url_prefix or MAKE_OUTPUT_URL_PREFIX
    name_fn = output_edit_name if dest_dir == EDIT_OUTPUT_DIR else output_make_name
    out_name = name_fn(prompt_id, ext=ext)
    dest = dest_dir / out_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    public_url = f"{prefix}/{out_name}"
    return dest, public_url


def save_output_video(
    video_ref: dict[str, str],
    prompt_id: str,
    *,
    base_url: str | None = None,
    on_download_progress: Callable[[float], None] | None = None,
) -> tuple[Path, str]:
    """Fetch from ComfyUI ``/view`` and write ``outputs/videos/<file>``."""
    filename = video_ref["filename"]

    def _bytes_progress(read: int, total: int | None) -> None:
        if on_download_progress is None:
            return
        if total and total > 0:
            on_download_progress(read / total)
        elif read > 0:
            on_download_progress(1.0)

    data, content_type = view_image_request(
        filename,
        subfolder=video_ref.get("subfolder") or "",
        type_=video_ref.get("type") or "output",
        base_url=base_url,
        on_progress=_bytes_progress if on_download_progress else None,
    )
    ext = _extension(filename, content_type)
    if ext not in {".mp4", ".webm", ".mov", ".gif"}:
        ext = ".mp4"
    out_name = output_video_name(prompt_id, ext=ext)
    dest = VIDEOS_OUTPUT_DIR / out_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    public_url = f"{VIDEOS_OUTPUT_URL_PREFIX}/{out_name}"
    return dest, public_url


def remove_live_preview_files(prompt_id: str) -> None:
    """Remove legacy on-disk ``{prompt_id}_live.*`` (pre–in-memory live previews)."""
    if not MAKE_OUTPUT_DIR.is_dir():
        return
    for path in MAKE_OUTPUT_DIR.glob(f"{prompt_id}_live.*"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def batch_storage_id(comfy_prompt_id: str, index: int, *, batch_count: int) -> str:
    """DB / filename key for one image in a ComfyUI batch run."""
    if batch_count <= 1:
        return comfy_prompt_id
    return f"{comfy_prompt_id}_{index}"


def save_all_output_images(
    history_item: dict[str, Any],
    comfy_prompt_id: str,
    *,
    base_url: str | None = None,
    images: list[dict[str, str]] | None = None,
    on_download_progress: Callable[[float], None] | None = None,
    output_dir: Path | None = None,
    url_prefix: str | None = None,
) -> list[tuple[Path, str, str]]:
    """Persist every image ref; returns ``(path, public_url, storage_id)`` per image."""
    from .client import collect_output_images

    refs = images if images is not None else collect_output_images(history_item)
    if not refs:
        raise RuntimeError(f"ComfyUI prompt {comfy_prompt_id} finished with no images")
    batch_count = len(refs)
    saved: list[tuple[Path, str, str]] = []
    for i, ref in enumerate(refs):
        storage_id = batch_storage_id(comfy_prompt_id, i, batch_count=batch_count)

        def _file_progress(file_part: float, *, index: int = i) -> None:
            if on_download_progress is None:
                return
            on_download_progress(
                download_fraction_from_parts(
                    wait_part=1.0,
                    file_index=index,
                    file_count=batch_count,
                    file_part=file_part,
                )
            )

        path, url = save_output_image(
            ref,
            storage_id,
            base_url=base_url,
            on_download_progress=_file_progress if on_download_progress else None,
            output_dir=output_dir,
            url_prefix=url_prefix,
        )
        saved.append((path, url, storage_id))
    return saved


def save_all_output_videos(
    history_item: dict[str, Any],
    comfy_prompt_id: str,
    *,
    base_url: str | None = None,
    videos: list[dict[str, str]] | None = None,
    on_download_progress: Callable[[float], None] | None = None,
) -> list[tuple[Path, str, str]]:
    """Persist every video ref; returns ``(path, public_url, storage_id)``."""
    from .client import collect_output_videos

    refs = videos if videos is not None else collect_output_videos(history_item)
    if not refs:
        raise RuntimeError(f"ComfyUI prompt {comfy_prompt_id} finished with no videos")
    saved: list[tuple[Path, str, str]] = []
    batch_count = len(refs)
    for i, ref in enumerate(refs):
        storage_id = batch_storage_id(comfy_prompt_id, i, batch_count=batch_count)

        def _file_progress(file_part: float, *, index: int = i) -> None:
            if on_download_progress is None:
                return
            on_download_progress(
                download_fraction_from_parts(
                    wait_part=1.0,
                    file_index=index,
                    file_count=batch_count,
                    file_part=file_part,
                )
            )

        path, url = save_output_video(
            ref,
            storage_id,
            base_url=base_url,
            on_download_progress=_file_progress if on_download_progress else None,
        )
        saved.append((path, url, storage_id))
    return saved
