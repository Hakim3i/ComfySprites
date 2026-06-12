"""Export tab — sprite sheet / picture export from saved Animate videos."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/export", response_class=HTMLResponse, name="export")
def export_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "export/index.html",
        {"active": "export"},
    )
