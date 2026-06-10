"""Shared FastAPI router for ``/api/*``."""

from __future__ import annotations

from fastapi import APIRouter

from ..db.models import VIEW_KINDS

router = APIRouter(prefix="/api", tags=["api"])

__all__ = ["router", "VIEW_KINDS"]
