"""SQLAlchemy models — clean v1 schema (no legacy migrations)."""

from __future__ import annotations

# Bump when mapped columns change; init_schema drops and rebuilds dataset.db.
SCHEMA_VERSION = 16

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Design entity types
ENTITY_CHARACTER = "character"
ENTITY_MONSTER = "monster"
ENTITY_OBJECT = "object"
ENTITY_BACKGROUND = "background"
ENTITY_TYPES = (ENTITY_CHARACTER, ENTITY_MONSTER, ENTITY_OBJECT, ENTITY_BACKGROUND)
SUBJECT_TYPES = (ENTITY_CHARACTER, ENTITY_MONSTER, ENTITY_OBJECT)

ROLE_MAIN = "main"

# View kinds
VIEW_KIND_SHOT = "shot"
VIEW_KIND_ANGLE = "angle"
VIEW_KIND_POV = "pov"
VIEW_KIND_FOCUS = "focus"
VIEW_KINDS = (VIEW_KIND_SHOT, VIEW_KIND_ANGLE, VIEW_KIND_POV, VIEW_KIND_FOCUS)

LORA_KIND_ENTITY = "entity"
LORA_KIND_CHARACTER = "character"
LORA_KIND_ANIMATION = "animation"
LORA_KIND_ANIMATION_SDXL = "animation_sdxl"
LORA_KIND_ANIMATION_LTX = "animation_ltx"
LORA_KIND_ANIMATION_WAN_HIGH = "animation_wan_high"
LORA_KIND_ANIMATION_WAN_LOW = "animation_wan_low"
LORA_KIND_ANIMATION_QWEN_EDIT = "animation_qwen_edit"
LORA_KIND_STYLE = "style"
LORA_KIND_STYLE_LTX = "style_ltx"
LORA_KIND_STYLE_WAN_HIGH = "style_wan_high"
LORA_KIND_STYLE_WAN_LOW = "style_wan_low"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Lora(Base):
    __tablename__ = "loras"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(512))
    download_url: Mapped[str | None] = mapped_column(String(512))
    download_fallback_url: Mapped[str | None] = mapped_column(String(512))
    model_id: Mapped[int | None] = mapped_column(Integer)
    version_id: Mapped[int | None] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255), unique=True)
    trigger: Mapped[str | None] = mapped_column(Text)
    caption_trigger: Mapped[str | None] = mapped_column(Text)
    strength: Mapped[float] = mapped_column(default=1.0)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class DesignEntity(Base):
    """Unified design row: character, monster, object, or background."""

    __tablename__ = "design_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(16), default=ENTITY_CHARACTER)
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MAIN)
    comment: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(512))

    name_tag: Mapped[str] = mapped_column(String(128), default="")
    identity_core: Mapped[list] = mapped_column(JSON, default=list)
    outfit_head: Mapped[list] = mapped_column(JSON, default=list)
    outfit_upper: Mapped[list] = mapped_column(JSON, default=list)
    outfit_lower: Mapped[list] = mapped_column(JSON, default=list)
    outfit_extra: Mapped[list] = mapped_column(JSON, default=list)

    eye_color: Mapped[str | None] = mapped_column(String(64))
    eye_shape: Mapped[str | None] = mapped_column(String(64))
    facial_marks: Mapped[list] = mapped_column(JSON, default=list)
    hair_color: Mapped[str | None] = mapped_column(String(64))
    hair_length: Mapped[str | None] = mapped_column(String(64))
    hair_style: Mapped[str | None] = mapped_column(String(64))
    age_band: Mapped[str | None] = mapped_column(String(64))
    ethnicity: Mapped[str | None] = mapped_column(String(64))
    skin_tone: Mapped[str | None] = mapped_column(String(64))
    height: Mapped[str | None] = mapped_column(String(64))
    breast_size: Mapped[str | None] = mapped_column(String(64))
    body_type: Mapped[str | None] = mapped_column(String(64))
    muscle: Mapped[str | None] = mapped_column(String(64))
    hip_size: Mapped[str | None] = mapped_column(String(64))
    butt_size: Mapped[str | None] = mapped_column(String(64))
    thigh_type: Mapped[str | None] = mapped_column(String(64))
    glasses: Mapped[str | None] = mapped_column(String(64))
    makeup: Mapped[str | None] = mapped_column(String(64))
    piercings: Mapped[list] = mapped_column(JSON, default=list)
    tattoos: Mapped[list] = mapped_column(JSON, default=list)

    # Background-only
    scene_tags: Mapped[list] = mapped_column(JSON, default=list)
    video_prompt: Mapped[str | None] = mapped_column(Text)
    negative: Mapped[str] = mapped_column(Text, default="")

    lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    lora: Mapped[Lora | None] = relationship(foreign_keys=[lora_id])

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    @property
    def key(self) -> str:
        return self.slug

    @property
    def tags(self) -> list:
        return (
            self.scene_tags
            if self.entity_type == ENTITY_BACKGROUND
            else self.identity_core
        )

    @property
    def character_lora(self) -> Lora | None:
        return self.lora


class Style(Base):
    __tablename__ = "styles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255), default="")
    base_model: Mapped[str] = mapped_column(String(32), default="illustrious")
    civitai_url: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[int | None] = mapped_column(Integer)
    version_id: Mapped[int | None] = mapped_column(Integer)
    download_url: Mapped[str | None] = mapped_column(Text)
    download_fallback_url: Mapped[str | None] = mapped_column(String(512))
    sampler: Mapped[str] = mapped_column(String(64), default="Euler a")
    scheduler: Mapped[str | None] = mapped_column(String(64))
    steps: Mapped[int] = mapped_column(Integer, default=25)
    cfg_scale: Mapped[float] = mapped_column(Float, default=5.0)
    clip_skip: Mapped[int] = mapped_column(Integer, default=2)
    width: Mapped[int] = mapped_column(Integer, default=832)
    height: Mapped[int] = mapped_column(Integer, default=1216)
    denoise_strength: Mapped[float | None] = mapped_column(Float)
    prefix: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str] = mapped_column(Text, default="")
    video_register: Mapped[str | None] = mapped_column(Text)
    ltx_video_negative: Mapped[str | None] = mapped_column(Text)
    ltx_audio_negative: Mapped[str | None] = mapped_column(Text)
    wan_negative: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(512))
    lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    lora: Mapped[Lora | None] = relationship(foreign_keys=[lora_id])
    ltx_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    ltx_lora: Mapped[Lora | None] = relationship(foreign_keys=[ltx_lora_id])
    wan_high_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    wan_high_lora: Mapped[Lora | None] = relationship(foreign_keys=[wan_high_lora_id])
    wan_low_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    wan_low_lora: Mapped[Lora | None] = relationship(foreign_keys=[wan_low_lora_id])
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    @property
    def name(self) -> str:
        return self.display_name


class Animation(Base):
    __tablename__ = "animations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    menu_name: Mapped[str] = mapped_column(String(128), unique=True)
    subject_type: Mapped[str] = mapped_column(
        String(16), default=ENTITY_CHARACTER, server_default=ENTITY_CHARACTER
    )
    comment: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(512))
    controlnets: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    video_prompt: Mapped[str | None] = mapped_column(Text)
    framings: Mapped[list] = mapped_column(JSON, default=list)
    orientation: Mapped[str | None] = mapped_column(String(16))
    lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    lora: Mapped[Lora | None] = relationship(foreign_keys=[lora_id])
    ltx_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    ltx_lora: Mapped[Lora | None] = relationship(foreign_keys=[ltx_lora_id])
    wan_high_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    wan_high_lora: Mapped[Lora | None] = relationship(foreign_keys=[wan_high_lora_id])
    wan_low_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    wan_low_lora: Mapped[Lora | None] = relationship(foreign_keys=[wan_low_lora_id])
    qwen_edit_prompt: Mapped[str | None] = mapped_column(Text)
    negative: Mapped[str] = mapped_column(Text, default="")
    qwen_edit_lora_id: Mapped[int | None] = mapped_column(ForeignKey("loras.id"))
    qwen_edit_lora: Mapped[Lora | None] = relationship(foreign_keys=[qwen_edit_lora_id])
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class View(Base):
    __tablename__ = "views"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer, default=0)
    comment: Mapped[str | None] = mapped_column(Text)
    framing_clause: Mapped[str | None] = mapped_column(Text)


class Generation(Base):
    __tablename__ = "generations"

    prompt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    image_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    request_json: Mapped[dict] = mapped_column(JSON)
    build_json: Mapped[dict] = mapped_column(JSON)


class VideoGeneration(Base):
    __tablename__ = "video_generations"

    prompt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_path: Mapped[str] = mapped_column(String(512))
    source_prompt_id: Mapped[str] = mapped_column(String(36))
    model_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    request_json: Mapped[dict] = mapped_column(JSON)
    build_json: Mapped[dict] = mapped_column(JSON)


class EditGeneration(Base):
    __tablename__ = "edit_generations"

    prompt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    image_path: Mapped[str] = mapped_column(String(512))
    source_prompt_id: Mapped[str] = mapped_column(String(36))
    source_kind: Mapped[str] = mapped_column(String(16), default="make")
    animation_slug: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    request_json: Mapped[dict] = mapped_column(JSON)
    build_json: Mapped[dict] = mapped_column(JSON)
