"""Database bootstrap."""

from __future__ import annotations

from pathlib import Path

from .session import init_schema


def init_db(db_path: Path | None = None):
    init_schema(db_path)
    _seed_json_catalog_files()
    _remove_legacy_test_content(db_path)
    _seed_catalog_if_empty(db_path)


def _seed_catalog_if_empty(db_path: Path | None = None) -> None:
    """Insert shipped catalog rows only when a table has no rows (first run)."""
    from sqlalchemy import func, select

    from .models import (
        ENTITY_BACKGROUND,
        ENTITY_CHARACTER,
        ENTITY_OBJECT,
        ROLE_MAIN,
        Animation,
        DesignEntity,
        Style,
        View,
    )
    from .session import session_scope

    with session_scope(db_path) as session:
        if session.scalar(select(func.count()).select_from(View)) == 0:
            from .views_defaults import ensure_default_views

            ensure_default_views(session)
        if session.scalar(select(func.count()).select_from(Style)) == 0:
            from .styles_defaults import ensure_default_styles

            ensure_default_styles(session)
        if session.scalar(select(func.count()).select_from(Animation)) == 0:
            from .animations_defaults import ensure_default_animations

            ensure_default_animations(session)
        bg_count = session.scalar(
            select(func.count())
            .select_from(DesignEntity)
            .where(DesignEntity.entity_type == ENTITY_BACKGROUND)
        )
        if bg_count == 0:
            from .backgrounds_defaults import ensure_default_backgrounds

            ensure_default_backgrounds(session)
        char_count = session.scalar(
            select(func.count())
            .select_from(DesignEntity)
            .where(
                DesignEntity.entity_type == ENTITY_CHARACTER,
                DesignEntity.role == ROLE_MAIN,
            )
        )
        if char_count == 0:
            from .characters_defaults import ensure_default_characters

            ensure_default_characters(session)
        obj_count = session.scalar(
            select(func.count())
            .select_from(DesignEntity)
            .where(
                DesignEntity.entity_type == ENTITY_OBJECT,
                DesignEntity.role == ROLE_MAIN,
            )
        )
        if obj_count == 0:
            from .objects_defaults import ensure_default_objects

            ensure_default_objects(session)


def _remove_legacy_test_content(db_path: Path | None = None) -> None:
    from .seed_constants import remove_legacy_test_content
    from .session import session_scope

    with session_scope(db_path) as session:
        remove_legacy_test_content(session)


def _seed_json_catalog_files() -> None:
    """Copy shipped dataset JSON into the workspace when missing (catalog metadata only)."""
    from ..services.catalog.character_suggestions import ensure_suggestions_file
    from ..services.catalog.controlnet_types import ensure_controlnet_types_file
    from ..services.catalog.diffusion_models import ensure_diffusion_models_file
    from ..services.catalog.style_defaults import ensure_style_defaults_file
    from .animations_defaults import ensure_animations_defaults_file
    from .backgrounds_defaults import ensure_backgrounds_defaults_file
    from .characters_defaults import ensure_characters_defaults_file
    from .objects_defaults import ensure_objects_defaults_file
    from .views_defaults import ensure_views_defaults_file

    ensure_suggestions_file()
    ensure_style_defaults_file()
    ensure_animations_defaults_file()
    ensure_controlnet_types_file()
    ensure_backgrounds_defaults_file()
    ensure_characters_defaults_file()
    ensure_objects_defaults_file()
    ensure_views_defaults_file()
    ensure_diffusion_models_file()
