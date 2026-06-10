"""Embed mode for entity editors loaded inside the gallery iframe."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse

_EMBED_VALUES = frozenset({"1", "true", "yes"})


def is_embed(request: Request, form=None) -> bool:
    if request.query_params.get("embed") in _EMBED_VALUES:
        return True
    if form is not None and form.get("embed") in _EMBED_VALUES:
        return True
    return False


def embed_context(request: Request, form=None) -> dict:
    embed = is_embed(request, form)
    tab = embed_tab_from_form(form) if form is not None else ""
    if not tab:
        tab = (request.query_params.get("tab") or "").strip()
    return {"embed": embed, "initial_tab": tab}


def embed_tab_from_form(form) -> str:
    return (form.get("tab") or "").strip()


def embed_redirect(
    request: Request,
    path: str,
    *,
    tab: str = "",
    form=None,
) -> RedirectResponse:
    if not is_embed(request, form):
        return RedirectResponse(path, status_code=303)
    params = ["embed=1"]
    active_tab = tab or (embed_tab_from_form(form) if form is not None else "")
    if active_tab:
        params.append(f"tab={quote(active_tab, safe='')}")
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}{'&'.join(params)}", status_code=303)
