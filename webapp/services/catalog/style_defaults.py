"""Style form hints and new-style defaults from dataset/style_defaults.json."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from ...config import DATASET_DIR, PROJECT_ROOT
from .dataset_json import require_json_object

DEFAULTS_PATH = DATASET_DIR / "style_defaults.json"
_SHIPPED_DEFAULTS_PATH = PROJECT_ROOT / "dataset" / "style_defaults.json"

_REQUIRED_LIST_KEYS = (
    "base_model_options",
    "sampler_hints",
    "scheduler_hints",
    "dimension_hints",
)
_REQUIRED_NEW_STYLE_KEYS = (
    "base_model",
    "sampler",
    "scheduler",
    "steps",
    "cfg_scale",
    "clip_skip",
    "width",
    "height",
)


@dataclass(frozen=True)
class NewStyleDefaults:
    base_model: str
    sampler: str
    scheduler: str
    steps: int
    cfg_scale: float
    clip_skip: int
    width: int
    height: int


@dataclass(frozen=True)
class StyleDefaultsConfig:
    base_model_options: tuple[str, ...]
    sampler_hints: tuple[str, ...]
    scheduler_hints: tuple[str, ...]
    dimension_hints: tuple[str, ...]
    new_style: NewStyleDefaults

    def to_dict(self) -> dict[str, Any]:
        ns = self.new_style
        return {
            "base_model_options": list(self.base_model_options),
            "sampler_hints": list(self.sampler_hints),
            "scheduler_hints": list(self.scheduler_hints),
            "dimension_hints": list(self.dimension_hints),
            "new_style": {
                "base_model": ns.base_model,
                "sampler": ns.sampler,
                "scheduler": ns.scheduler,
                "steps": ns.steps,
                "cfg_scale": ns.cfg_scale,
                "clip_skip": ns.clip_skip,
                "width": ns.width,
                "height": ns.height,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StyleDefaultsConfig:
        def _lines(key: str) -> tuple[str, ...]:
            val = raw.get(key)
            if not isinstance(val, list) or not val:
                raise ValueError(f"style_defaults.json: {key!r} must be a non-empty list")
            out = [str(v).strip() for v in val if str(v).strip()]
            if not out:
                raise ValueError(f"style_defaults.json: {key!r} must contain at least one value")
            return tuple(out)

        ns_raw = raw.get("new_style")
        if not isinstance(ns_raw, dict):
            raise ValueError("style_defaults.json: missing or invalid 'new_style' object")
        for key in _REQUIRED_NEW_STYLE_KEYS:
            if key not in ns_raw:
                raise ValueError(f"style_defaults.json: new_style missing required key {key!r}")

        return cls(
            base_model_options=_lines("base_model_options"),
            sampler_hints=_lines("sampler_hints"),
            scheduler_hints=_lines("scheduler_hints"),
            dimension_hints=_lines("dimension_hints"),
            new_style=NewStyleDefaults(
                base_model=str(ns_raw["base_model"]).strip(),
                sampler=str(ns_raw["sampler"]).strip(),
                scheduler=str(ns_raw["scheduler"]).strip(),
                steps=int(ns_raw["steps"]),
                cfg_scale=float(ns_raw["cfg_scale"]),
                clip_skip=int(ns_raw["clip_skip"]),
                width=int(ns_raw["width"]),
                height=int(ns_raw["height"]),
            ),
        )


def _load_raw() -> dict[str, Any]:
    return require_json_object("Style defaults", DEFAULTS_PATH, _SHIPPED_DEFAULTS_PATH)


def load_style_defaults() -> StyleDefaultsConfig:
    return StyleDefaultsConfig.from_dict(_load_raw())


def save_style_defaults(config: StyleDefaultsConfig) -> None:
    DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULTS_PATH.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ensure_style_defaults_file() -> StyleDefaultsConfig:
    if not DEFAULTS_PATH.is_file():
        if not _SHIPPED_DEFAULTS_PATH.is_file():
            raise FileNotFoundError(
                f"Style defaults not found at {DEFAULTS_PATH} or {_SHIPPED_DEFAULTS_PATH}"
            )
        DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SHIPPED_DEFAULTS_PATH, DEFAULTS_PATH)
    return load_style_defaults()


def base_model_options() -> tuple[str, ...]:
    return load_style_defaults().base_model_options


def sampler_hints() -> tuple[str, ...]:
    return load_style_defaults().sampler_hints


def scheduler_hints() -> tuple[str, ...]:
    return load_style_defaults().scheduler_hints


def _match_hint(value: str, hints: tuple[str, ...]) -> str | None:
    needle = " ".join((value or "").split()).lower()
    if not needle:
        return None
    for hint in hints:
        if hint.lower() == needle:
            return hint
    return None


def normalize_sampler(value: str) -> str:
    matched = _match_hint(value, sampler_hints())
    if matched:
        return matched
    hints = ", ".join(sampler_hints())
    raise ValueError(f"Unknown sampler {value!r}. Choose one of: {hints}")


def normalize_scheduler(value: str | None) -> str:
    matched = _match_hint(value or "", scheduler_hints())
    if matched:
        return matched
    hints = ", ".join(scheduler_hints())
    raise ValueError(f"Unknown scheduler {value!r}. Choose one of: {hints}")


def dimension_hints() -> tuple[str, ...]:
    return load_style_defaults().dimension_hints


def new_style_defaults() -> NewStyleDefaults:
    return load_style_defaults().new_style
