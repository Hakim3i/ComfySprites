"""Canonical test fixtures — wiped and re-inserted on each pytest run and dev startup."""

from __future__ import annotations

from sqlalchemy import delete, select

from ..revision import bump_revision
from .models import (
    ENTITY_BACKGROUND,
    ENTITY_CHARACTER,
    ENTITY_MONSTER,
    ENTITY_OBJECT,
    LORA_KIND_STYLE,
    ROLE_MAIN,
    Animation,
    DesignEntity,
    Lora,
    Style,
)
from .views_defaults import (
    SIDE_VIEW_KEY,
    ensure_default_views,
    view_tuples,
)

TEST_STYLE_SLUG = "test_style"
TEST_ANIMATION_SLUG = "test_act"
TEST_ACT_SLUG = TEST_ANIMATION_SLUG  # legacy alias
TEST_CHARACTER_SLUG = "test_character"
TEST_MONSTER_SLUG = "test_monster"
TEST_OBJECT_SLUG = "test_object"
TEST_BACKGROUND_SLUG = "test_background"
_LEGACY_TAXONOMY_BACKGROUND_SLUG = "bedroom"

TEST_ENTITY_SLUGS = (
    TEST_CHARACTER_SLUG,
    TEST_MONSTER_SLUG,
    TEST_OBJECT_SLUG,
    TEST_BACKGROUND_SLUG,
)

TEST_SIDE_VIEW_KEY = SIDE_VIEW_KEY
TEST_VIEWS = view_tuples()

# Default sprite act — idle side-view pose for character/object renders.
TEST_ANIMATION_TAGS = ("idle", "standing", "looking_away")
TEST_ANIMATION_FRAMINGS = (TEST_SIDE_VIEW_KEY,)

_FIXTURE_COMMENT = "Test fixture — reset on each test run and dev startup"

# Real generation data (slugs/names stay test_* for isolation).
WAI_V17_FILENAME = "waiIllustriousSDXL_v170.safetensors"
WAI_V17_CIVITAI_URL = (
    "https://civitai.red/models/827184/wai-illustrious-sdxl?modelVersionId=2883731"
)
# Epic Seven Sprites — style LoRA stacked on the WAI checkpoint in test_style.
E7_SPRITES_FILENAME = "e7sprites-000005.safetensors"
E7_SPRITES_CIVITAI_URL = (
    "https://civitai.red/models/1747637/epic-seven-sprites?modelVersionId=1977902"
)
E7_SPRITES_DOWNLOAD_URL = "https://civitai.red/api/download/models/1977902"
E7_SPRITES_DOWNLOAD_FALLBACK_URL = (
    "https://huggingface.co/Hakim3i/epic-seven-sprites-lora/resolve/main/"
    "Epic_Seven_Sprites.safetensors"
)
E7_SPRITES_TRIGGER = "e7sprites"
E7_SPRITES_MODEL_ID = 1747637
E7_SPRITES_VERSION_ID = 1977902

TEST_STYLE_DISPLAY_NAME = "Test Style"
TEST_STYLE_PREFIX = (
    "masterpiece, best quality, amazing quality, ultra-detailed, 4k, sharp"
)
TEST_STYLE_NEGATIVE = "bad quality, worst quality, worst detail, sketch, censor"


def ensure_test_taxonomy(session) -> None:
    """Canonical views; drop removed legacy taxonomy backgrounds."""
    ensure_default_views(session)
    session.execute(
        delete(DesignEntity).where(
            DesignEntity.entity_type == ENTITY_BACKGROUND,
            DesignEntity.slug == _LEGACY_TAXONOMY_BACKGROUND_SLUG,
        )
    )


def _clear_test_rows(session) -> None:
    session.execute(delete(DesignEntity).where(DesignEntity.slug.in_(TEST_ENTITY_SLUGS)))
    session.execute(delete(Style).where(Style.slug == TEST_STYLE_SLUG))
    session.execute(delete(Lora).where(Lora.filename == E7_SPRITES_FILENAME))
    session.execute(delete(Animation).where(Animation.slug == TEST_ANIMATION_SLUG))
    session.flush()


def reset_test_content(session) -> None:
    """Delete known test slugs and insert a fresh style, act, and design sprites."""
    ensure_test_taxonomy(session)
    _clear_test_rows(session)

    style_lora = Lora(
        kind=LORA_KIND_STYLE,
        name="Epic Seven Sprites",
        url=E7_SPRITES_CIVITAI_URL,
        download_url=E7_SPRITES_DOWNLOAD_URL,
        download_fallback_url=E7_SPRITES_DOWNLOAD_FALLBACK_URL,
        model_id=E7_SPRITES_MODEL_ID,
        version_id=E7_SPRITES_VERSION_ID,
        filename=E7_SPRITES_FILENAME,
        trigger=E7_SPRITES_TRIGGER,
        strength=1.0,
        comment=_FIXTURE_COMMENT,
    )
    session.add(style_lora)
    session.flush()

    session.add(
        Style(
            slug=TEST_STYLE_SLUG,
            display_name=TEST_STYLE_DISPLAY_NAME,
            filename=WAI_V17_FILENAME,
            base_model="illustrious",
            civitai_url=WAI_V17_CIVITAI_URL,
            model_id=827184,
            version_id=2883731,
            download_url="https://civitai.red/api/download/models/2883731",
            sampler="Euler a",
            scheduler="normal",
            steps=25,
            cfg_scale=6.0,
            clip_skip=2,
            width=1024,
            height=1344,
            prefix=TEST_STYLE_PREFIX,
            negative=TEST_STYLE_NEGATIVE,
            image_path=None,
            lora_id=style_lora.id,
            comment=_FIXTURE_COMMENT,
        )
    )
    session.add(
        Animation(
            slug=TEST_ANIMATION_SLUG,
            menu_name="Sprite idle",
            subject_type=ENTITY_CHARACTER,
            tags=list(TEST_ANIMATION_TAGS),
            framings=list(TEST_ANIMATION_FRAMINGS),
            orientation="portrait",
            comment=_FIXTURE_COMMENT,
        )
    )

    session.add(
        DesignEntity(
            slug=TEST_CHARACTER_SLUG,
            display_name="Test Character",
            name_tag="1girl",
            entity_type=ENTITY_CHARACTER,
            role=ROLE_MAIN,
            identity_core=["1girl", "solo"],
            hair_color="brown hair",
            hair_length="very long hair",
            hair_style="high ponytail",
            eye_color="blue eyes",
            age_band="teen",
            ethnicity="asian",
            skin_tone="pale skin",
            height="petite",
            breast_size="medium breasts",
            body_type="plump",
            muscle="soft body",
            hip_size="narrow waist",
            butt_size="big ass",
            thigh_type="thick thighs",
            outfit_upper=["sailor collar"],
            outfit_lower=["pleated skirt"],
            outfit_extra=["stockings"],
            comment=_FIXTURE_COMMENT,
        )
    )

    session.add(
        DesignEntity(
            slug=TEST_MONSTER_SLUG,
            display_name="Test Monster",
            name_tag=TEST_MONSTER_SLUG,
            entity_type=ENTITY_MONSTER,
            role=ROLE_MAIN,
            identity_core=["slime", "monster", "solo", "no humans"],
            comment=_FIXTURE_COMMENT,
        )
    )
    session.add(
        DesignEntity(
            slug=TEST_OBJECT_SLUG,
            display_name="Test Object",
            name_tag=TEST_OBJECT_SLUG,
            entity_type=ENTITY_OBJECT,
            role=ROLE_MAIN,
            identity_core=["sword", "weapon", "no humans", "simple background"],
            comment=_FIXTURE_COMMENT,
        )
    )
    session.add(
        DesignEntity(
            slug=TEST_BACKGROUND_SLUG,
            display_name=TEST_BACKGROUND_DISPLAY_NAME,
            entity_type=ENTITY_BACKGROUND,
            scene_tags=list(TEST_BACKGROUND_SCENE_TAGS),
            comment=_FIXTURE_COMMENT,
        )
    )
    session.flush()
    bump_revision()


# Canonical test character snapshot — tests assert against these defaults.
TEST_CHARACTER_NAME_TAG = "1girl"
TEST_CHARACTER_IDENTITY_CORE = ("1girl", "solo")
TEST_CHARACTER_PHYSICAL = {
    "hair_color": "brown hair",
    "hair_length": "very long hair",
    "hair_style": "high ponytail",
    "eye_color": "blue eyes",
    "age_band": "teen",
    "ethnicity": "asian",
    "skin_tone": "pale skin",
    "height": "petite",
    "breast_size": "medium breasts",
    "body_type": "plump",
    "muscle": "soft body",
    "hip_size": "narrow waist",
    "butt_size": "big ass",
    "thigh_type": "thick thighs",
}
TEST_CHARACTER_OUTFIT = {
    "outfit_head": [],
    "outfit_upper": ["sailor collar"],
    "outfit_lower": ["pleated skirt"],
    "outfit_extra": ["stockings"],
}

# Canonical test background — neutral grey sprite backdrop for Make rolls.
TEST_BACKGROUND_DISPLAY_NAME = "test_background"
TEST_BACKGROUND_SCENE_TAGS = ("simple_background", "grey_background")

__all__ = [
    "E7_SPRITES_DOWNLOAD_FALLBACK_URL",
    "E7_SPRITES_DOWNLOAD_URL",
    "E7_SPRITES_FILENAME",
    "E7_SPRITES_MODEL_ID",
    "E7_SPRITES_TRIGGER",
    "E7_SPRITES_VERSION_ID",
    "TEST_ANIMATION_FRAMINGS",
    "TEST_ANIMATION_SLUG",
    "TEST_ANIMATION_TAGS",
    "TEST_BACKGROUND_DISPLAY_NAME",
    "TEST_BACKGROUND_SCENE_TAGS",
    "TEST_BACKGROUND_SLUG",
    "TEST_CHARACTER_IDENTITY_CORE",
    "TEST_CHARACTER_NAME_TAG",
    "TEST_CHARACTER_OUTFIT",
    "TEST_CHARACTER_PHYSICAL",
    "TEST_CHARACTER_SLUG",
    "TEST_ENTITY_SLUGS",
    "TEST_MONSTER_SLUG",
    "TEST_OBJECT_SLUG",
    "TEST_SIDE_VIEW_KEY",
    "TEST_STYLE_DISPLAY_NAME",
    "TEST_STYLE_NEGATIVE",
    "TEST_STYLE_PREFIX",
    "TEST_STYLE_SLUG",
    "TEST_VIEWS",
    "WAI_V17_FILENAME",
    "ensure_test_taxonomy",
    "reset_test_content",
]
