"""Pytest configuration for ComfySprites."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = Path(__file__).resolve().parent
for p in (str(ROOT), str(TEST_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

_DEFAULT_RELOAD_MODULES = (
    "webapp.db",
    "webapp.db.session",
    "webapp.db.init",
    "webapp.revision",
    "webapp.env_settings",
    "webapp.api",
    "webapp.main",
)


def boot_webapp_client(
    tmp_path_factory,
    *,
    mktemp_name: str = "webapp",
    extra_modules: tuple[str, ...] = (),
    seed: Callable[[], None] | None = None,
) -> Iterator:
    tmp = tmp_path_factory.mktemp(mktemp_name)
    dataset_dir = tmp / "dataset"
    dataset_dir.mkdir()

    import webapp.config as cfg

    cfg.DATASET_DIR = dataset_dir
    cfg.DB_PATH = dataset_dir / "dataset.db"
    cfg.UPLOADS_DIR = dataset_dir / "uploads"
    cfg.UPLOADS_DIR.mkdir()

    for name in (*_DEFAULT_RELOAD_MODULES, *extra_modules):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    if extra_modules and "webapp.main" in sys.modules:
        importlib.reload(sys.modules["webapp.main"])

    from webapp.db import session as db_session
    from webapp.db import init_db

    db_session._engine = None
    db_session._Session = None
    init_db(cfg.DB_PATH)
    if seed is not None:
        seed()

    from webapp.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    yield from boot_webapp_client(tmp_path_factory)


@pytest.fixture(autouse=True)
def comfyui_make_base_url(monkeypatch):
    monkeypatch.setenv("COMFYUI_MAKE_BASE_URL", "http://localhost:8188")
