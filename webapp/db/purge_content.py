"""Optional generated output cleanup."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select

from ..config import EDIT_OUTPUT_DIR, PROJECT_ROOT
from ..revision import bump_revision
from .models import EditGeneration, Generation


def _unlink_output(path: Path) -> None:
    if path.is_file():
        path.unlink()


def purge_edit_output_files() -> None:
    """Remove Edit Lab PNG files from ``outputs/edit/``."""
    if not EDIT_OUTPUT_DIR.is_dir():
        return
    for path in EDIT_OUTPUT_DIR.glob("*.png"):
        _unlink_output(path)


def purge_all_generated_content(session) -> None:
    """One-shot: clear edit/make history rows and edit output files."""
    purge_edit_output_files()

    for row in session.scalars(select(EditGeneration)).all():
        rel = Path(row.image_path)
        disk = rel if rel.is_absolute() else PROJECT_ROOT / rel
        _unlink_output(disk)
    session.execute(delete(EditGeneration))
    session.execute(delete(Generation))
    session.flush()
    bump_revision()


__all__ = [
    "purge_all_generated_content",
    "purge_edit_output_files",
]
