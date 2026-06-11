"""FastAPI app entry point for the ComfySprites webapp."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .asyncio_compat import install_client_disconnect_exception_handler
from .config import (
    GITHUB_NODES_REPO_URL,
    GITHUB_REPO_URL,
    MAKE_OUTPUT_DIR,
    MAKE_OUTPUT_URL_PREFIX,
    UPLOADS_DIR,
    UPLOADS_URL_PREFIX,
    VIDEOS_OUTPUT_DIR,
    VIDEOS_OUTPUT_URL_PREFIX,
    EDIT_OUTPUT_DIR,
    EDIT_OUTPUT_URL_PREFIX,
    ensure_edit_outputs,
    ensure_make_outputs,
    ensure_videos_outputs,
)
from .db import init_db
from .revision import asset_revision

HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    install_client_disconnect_exception_handler()
    yield


app = FastAPI(title="ComfySprites", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.globals["asset_revision"] = asset_revision
templates.env.globals["github_repo_url"] = GITHUB_REPO_URL
templates.env.globals["github_nodes_repo_url"] = GITHUB_NODES_REPO_URL
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(UPLOADS_URL_PREFIX, StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
ensure_make_outputs()
ensure_videos_outputs()
ensure_edit_outputs()
app.mount(
    MAKE_OUTPUT_URL_PREFIX,
    StaticFiles(directory=str(MAKE_OUTPUT_DIR)),
    name="make_outputs",
)
app.mount(
    VIDEOS_OUTPUT_URL_PREFIX,
    StaticFiles(directory=str(VIDEOS_OUTPUT_DIR)),
    name="video_outputs",
)
app.mount(
    EDIT_OUTPUT_URL_PREFIX,
    StaticFiles(directory=str(EDIT_OUTPUT_DIR)),
    name="edit_outputs",
)
app.state.templates = templates

from .routes.pages import home as home_routes  # noqa: E402
from .routes.pages import design as design_routes  # noqa: E402
from .routes.pages import animations as animations_routes  # noqa: E402
from .routes.pages import styles as styles_routes  # noqa: E402
from .routes.pages import backgrounds as backgrounds_routes  # noqa: E402
from .routes.pages import views as views_routes  # noqa: E402
from .routes.pages import settings as settings_routes  # noqa: E402
from .routes.pages import make as make_routes  # noqa: E402
from .routes.pages import animate as animate_routes  # noqa: E402
from .routes.pages import edit as edit_routes  # noqa: E402
from .api import router as api_router  # noqa: E402

app.include_router(home_routes.router)
app.include_router(design_routes.hub_router, prefix="/design", tags=["design"])
app.include_router(
    design_routes.monster_router, prefix="/design/monsters", tags=["monsters"]
)
app.include_router(
    design_routes.object_router, prefix="/design/objects", tags=["objects"]
)
app.include_router(design_routes.router, prefix="/characters", tags=["characters"])
app.include_router(animations_routes.router, prefix="/animations", tags=["animations"])
app.include_router(styles_routes.router, prefix="/styles", tags=["styles"])
app.include_router(backgrounds_routes.router, prefix="/backgrounds", tags=["backgrounds"])
app.include_router(views_routes.router, tags=["views"])
app.include_router(settings_routes.router, tags=["settings"])
app.include_router(make_routes.router, tags=["make"])
app.include_router(animate_routes.router, tags=["animate"])
app.include_router(edit_routes.router, tags=["edit"])
app.include_router(api_router)
