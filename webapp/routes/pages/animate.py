"""Animate tab — image-to-video scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/animate", response_class=HTMLResponse, name="animate")
def animate_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "animate/index.html",
        {"active": "animate"},
    )
