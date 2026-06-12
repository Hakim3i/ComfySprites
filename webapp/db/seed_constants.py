"""Canonical shipped default slugs and legacy test-fixture cleanup."""

from __future__ import annotations

from .views_defaults import SIDE_VIEW_KEY

DEFAULT_CHARACTER_SLUG = "asuna"
DEFAULT_OBJECT_SLUG = "book"
DEFAULT_BACKGROUND_SLUG = "grey_background"
DEFAULT_STYLE_SLUG = "wai_illustrious"
DEFAULT_QWEN_STYLE_SLUG = "qwen_image_2512"
DEFAULT_ANIMATION_SLUG = "standing_idle"
DEFAULT_SIDE_VIEW_KEY = SIDE_VIEW_KEY

LEGACY_TEST_ENTITY_SLUGS = (
    "test_character",
    "test_monster",
    "test_object",
    "test_background",
)
LEGACY_TEST_STYLE_SLUG = "test_style"
LEGACY_TEST_ANIMATION_SLUG = "test_act"


def remove_legacy_test_content(session) -> None:
    """Drop old test_* fixture rows from databases created before defaults-only seeding."""
    from sqlalchemy import delete

    from ..revision import bump_revision
    from .models import Animation, DesignEntity, Style

    session.execute(
        delete(DesignEntity).where(DesignEntity.slug.in_(LEGACY_TEST_ENTITY_SLUGS))
    )
    session.execute(delete(Style).where(Style.slug == LEGACY_TEST_STYLE_SLUG))
    session.execute(
        delete(Animation).where(Animation.slug == LEGACY_TEST_ANIMATION_SLUG)
    )
    session.flush()
    bump_revision()


__all__ = [
    "DEFAULT_ANIMATION_SLUG",
    "DEFAULT_BACKGROUND_SLUG",
    "DEFAULT_CHARACTER_SLUG",
    "DEFAULT_OBJECT_SLUG",
    "DEFAULT_QWEN_STYLE_SLUG",
    "DEFAULT_SIDE_VIEW_KEY",
    "DEFAULT_STYLE_SLUG",
    "LEGACY_TEST_ANIMATION_SLUG",
    "LEGACY_TEST_ENTITY_SLUGS",
    "LEGACY_TEST_STYLE_SLUG",
    "remove_legacy_test_content",
]
