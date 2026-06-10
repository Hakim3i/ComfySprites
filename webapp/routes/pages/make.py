"""Make Lab — sprite generation via ComfyUI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/make", response_class=HTMLResponse, name="make")
def make_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "make/index.html",
        {"active": "make"},
    )
