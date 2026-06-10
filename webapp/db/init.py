"""Database bootstrap and JSON default seeds."""

from __future__ import annotations

from pathlib import Path

from .session import init_schema


def init_db(db_path: Path | None = None):
    init_schema(db_path)
    _seed_json_defaults()
    _seed_test_content(db_path)
    _seed_default_styles(db_path)
    _seed_default_animations(db_path)
    _seed_default_backgrounds(db_path)


def _seed_test_content(db_path: Path | None = None) -> None:
    from .session import session_scope
    from .test_seed import reset_test_content

    with session_scope(db_path) as session:
        reset_test_content(session)


def _seed_default_styles(db_path: Path | None = None) -> None:
    from .session import session_scope
    from .styles_defaults import ensure_default_styles

    with session_scope(db_path) as session:
        ensure_default_styles(session)


def _seed_default_animations(db_path: Path | None = None) -> None:
    from .session import session_scope
    from .animations_defaults import ensure_default_animations

    with session_scope(db_path) as session:
        ensure_default_animations(session)


def _seed_default_backgrounds(db_path: Path | None = None) -> None:
    from .session import session_scope
    from .backgrounds_defaults import ensure_default_backgrounds

    with session_scope(db_path) as session:
        ensure_default_backgrounds(session)


def _seed_json_defaults() -> None:
    from ..services.catalog.controlnet_types import ensure_controlnet_types_file
    from ..services.catalog.character_suggestions import ensure_suggestions_file
    from ..services.catalog.style_defaults import ensure_style_defaults_file
    from .animations_defaults import ensure_animations_defaults_file
    from .backgrounds_defaults import ensure_backgrounds_defaults_file
    from .views_defaults import ensure_views_defaults_file

    ensure_suggestions_file()
    ensure_style_defaults_file()
    ensure_animations_defaults_file()
    ensure_controlnet_types_file()
    ensure_backgrounds_defaults_file()
    ensure_views_defaults_file()
