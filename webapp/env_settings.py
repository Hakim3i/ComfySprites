"""Read/write API keys and ComfyUI URL in the workspace ``.env`` file."""

from __future__ import annotations

import os
import re

from .config import PROJECT_ROOT

WORKSPACE_ROOT = PROJECT_ROOT.parent
ENV_PATH = WORKSPACE_ROOT / ".env"

CIVITAI_KEYS = ("CIVITAI_TOKEN", "CIVITAI_API_KEY")
HF_KEYS = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")
COMFYUI_BASE_URL_KEY = "COMFYUI_BASE_URL"
COMFYUI_PHOTO_BASE_URL_KEY = "COMFYUI_PHOTO_BASE_URL"

_ENV_LINE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)

_COMFYUI_SETUP_MSG = (
    "ComfyUI URL is not configured. Set COMFYUI_PHOTO_BASE_URL or COMFYUI_BASE_URL "
    f"in {ENV_PATH} or via the Settings tab."
)


def _strip_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _quote_env_value(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[\s#"\\]', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _first_set(keys: tuple[str, ...], values: dict[str, str]) -> str:
    for key in keys:
        v = (values.get(key) or os.environ.get(key) or "").strip()
        if v:
            return v
    return ""


def load_api_keys() -> dict[str, str]:
    file_values = read_env_file()
    return {
        "civitai_token": _first_set(CIVITAI_KEYS, file_values),
        "hf_token": _first_set(HF_KEYS, file_values),
    }


def read_env_file() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = _ENV_LINE.match(line)
        if m:
            out[m.group(1)] = _strip_env_value(m.group(2))
    return out


def save_api_keys(*, civitai_token: str, hf_token: str) -> None:
    civitai = civitai_token.strip()
    hf = hf_token.strip()

    lines: list[str] = []
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updates: dict[str, str] = {}
    if civitai:
        updates["CIVITAI_TOKEN"] = civitai
    if hf:
        updates["HF_TOKEN"] = hf

    seen: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        m = _ENV_LINE.match(line)
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1)
        if key in updates:
            out_lines.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        elif key in CIVITAI_KEYS + HF_KEYS:
            if key == "CIVITAI_TOKEN" and not civitai:
                continue
            if key == "HF_TOKEN" and not hf:
                continue
            if key in ("CIVITAI_API_KEY", "HUGGINGFACE_HUB_TOKEN"):
                continue
            out_lines.append(line)
        else:
            out_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            if out_lines and out_lines[-1].strip():
                out_lines.append("")
            out_lines.append(f"{key}={_quote_env_value(value)}")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    ENV_PATH.write_text(text, encoding="utf-8")

    if civitai:
        os.environ["CIVITAI_TOKEN"] = civitai
    else:
        os.environ.pop("CIVITAI_TOKEN", None)
    if hf:
        os.environ["HF_TOKEN"] = hf
    else:
        os.environ.pop("HF_TOKEN", None)


def normalize_comfyui_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("ComfyUI URL cannot be empty")
    return raw


def _comfyui_raw_url(file_values: dict[str, str] | None = None) -> str:
    values = file_values if file_values is not None else read_env_file()
    for key in (COMFYUI_PHOTO_BASE_URL_KEY, COMFYUI_BASE_URL_KEY):
        raw = (values.get(key) or os.environ.get(key) or "").strip()
        if raw:
            return raw
    return ""


def load_comfyui_base_url() -> str:
    raw = _comfyui_raw_url()
    if not raw:
        raise RuntimeError(_COMFYUI_SETUP_MSG)
    return normalize_comfyui_base_url(raw)


def load_comfyui_urls() -> dict[str, str]:
    return {"photo": load_comfyui_base_url()}


def save_comfyui_urls(*, photo_url: str) -> None:
    photo = normalize_comfyui_base_url(photo_url)
    updates = {COMFYUI_PHOTO_BASE_URL_KEY: photo}
    lines: list[str] = []
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        m = _ENV_LINE.match(line)
        if m and m.group(1) in updates:
            key = m.group(1)
            out_lines.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        elif m and m.group(1) == COMFYUI_BASE_URL_KEY:
            continue
        else:
            out_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            if out_lines and out_lines[-1].strip():
                out_lines.append("")
            out_lines.append(f"{key}={_quote_env_value(value)}")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    ENV_PATH.write_text(text, encoding="utf-8")
    os.environ[COMFYUI_PHOTO_BASE_URL_KEY] = photo


def save_comfyui_base_url(url: str) -> None:
    save_comfyui_urls(photo_url=url)
