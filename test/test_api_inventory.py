"""FastAPI route registry — guards against accidental endpoint drift."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.main import app

EXPECTED_API_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("DELETE", "/api/animations/{slug}"),
    ("DELETE", "/api/characters/{slug}"),
    ("DELETE", "/api/styles/{slug}"),
    ("DELETE", "/api/views/{key:path}"),
    ("DELETE", "/api/backgrounds/{key:path}"),
    ("GET", "/api/animations"),
    ("GET", "/api/animations/{slug}"),
    ("GET", "/api/characters"),
    ("GET", "/api/characters/{slug}"),
    ("GET", "/api/styles"),
    ("GET", "/api/styles/{slug}"),
    ("GET", "/api/views"),
    ("GET", "/api/views/{key:path}"),
    ("GET", "/api/backgrounds"),
    ("GET", "/api/backgrounds/{key:path}"),
    ("GET", "/api/dropdowns"),
    ("GET", "/api/health"),
    ("GET", "/api/character-attributes"),
    ("GET", "/api/comfyui/status"),
    ("GET", "/api/make/history"),
    ("GET", "/api/make/detailers"),
    ("POST", "/api/animations"),
    ("POST", "/api/build"),
    ("POST", "/api/characters"),
    ("POST", "/api/styles"),
    ("POST", "/api/backgrounds"),
    ("POST", "/api/make/generate"),
    ("PATCH", "/api/loras/{lora_id}"),
})


def _api_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            continue
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            out.add((method, path))
    return out


def test_api_route_inventory_matches_expected():
    actual = _api_routes()
    missing = EXPECTED_API_ROUTES - actual
    assert not missing, f"missing routes: {sorted(missing)}"
