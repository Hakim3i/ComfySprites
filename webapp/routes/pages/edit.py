"""Edit tab — Qwen Image Edit."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/edit", response_class=HTMLResponse, name="edit")
def edit_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "edit/index.html",
        {"active": "edit"},
    )
