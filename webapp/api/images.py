"""Reference image upload helpers."""

from __future__ import annotations

from typing import Any

from fastapi import UploadFile

from ..services.design.forms import save_uploaded_image


def attach_upload_image(
    entity: Any,
    *,
    file: UploadFile,
    entity_dir: str,
    slug: str,
) -> str:
    entity.image_path = save_uploaded_image(
        file, entity=entity_dir, slug=slug, existing=entity.image_path
    )
    return entity.image_path
