"""Workspace settings (API keys, ComfyUI URL, tag suggestions)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...services import attributes as char_attrs
from ...services.catalog.character_suggestions import (
    ensure_suggestions_file,
    load_suggestions,
    parse_suggestions_form,
    save_suggestions,
)
from ...env_settings import (
    ENV_PATH,
    load_api_keys,
    load_comfyui_urls,
    save_api_keys,
    save_comfyui_urls,
)
from ...revision import bump_revision

router = APIRouter()

_SAVE_FLASH: dict[str, str] = {
    "api-keys": f"API keys saved to {ENV_PATH}. Restart Cursor MCP servers if you changed them.",
    "comfyui": f"ComfyUI URL saved to {ENV_PATH}.",
    "suggestions": "Physical tag suggestions saved to dataset/character_suggestions.json.",
}


def _suggestion_form_lines() -> dict[str, str]:
    data = load_suggestions()
    return {key: "\n".join(data.get(key, [])) for key in data}


@router.get("/settings", response_class=HTMLResponse, name="settings")
def settings_page(request: Request, saved: str = ""):
    keys = load_api_keys()
    try:
        comfyui_urls = load_comfyui_urls()
        comfyui_photo_base_url = comfyui_urls["photo"]
    except RuntimeError:
        comfyui_photo_base_url = ""
    ensure_suggestions_file()
    flash = None
    if saved in _SAVE_FLASH:
        flash = {"text": _SAVE_FLASH[saved]}
    suggestion_attrs = [
        a for a in char_attrs.ATTRIBUTES if a.key in _suggestion_form_lines()
    ]
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active": "settings",
            "civitai_token": keys["civitai_token"],
            "hf_token": keys["hf_token"],
            "comfyui_photo_base_url": comfyui_photo_base_url,
            "env_path": str(ENV_PATH),
            "suggestion_lines": _suggestion_form_lines(),
            "suggestion_attrs": suggestion_attrs,
            "flash": flash,
        },
    )


@router.post("/settings/comfyui", name="settings_save_comfyui")
async def settings_save_comfyui(request: Request):
    form = await request.form()
    save_comfyui_urls(
        photo_url=(form.get("comfyui_photo_base_url") or "").strip(),
    )
    return RedirectResponse("/settings?saved=comfyui", status_code=303)


@router.post("/settings/api-keys", name="settings_save_api_keys")
async def settings_save_api_keys(request: Request):
    form = await request.form()
    save_api_keys(
        civitai_token=(form.get("civitai_token") or "").strip(),
        hf_token=(form.get("hf_token") or "").strip(),
    )
    return RedirectResponse("/settings?saved=api-keys", status_code=303)


@router.post("/settings/suggestions", name="settings_save_suggestions")
async def settings_save_suggestions(request: Request):
    form = await request.form()
    save_suggestions(parse_suggestions_form(form))
    bump_revision()
    return RedirectResponse("/settings?saved=suggestions", status_code=303)
