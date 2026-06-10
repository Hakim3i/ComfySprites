"""ComfySprites path and URL constants."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
DB_PATH = DATASET_DIR / "dataset.db"
STATIC_DIR = PACKAGE_ROOT / "static"
UPLOADS_DIR = DATASET_DIR / "uploads"
UPLOADS_URL_PREFIX = "/uploads"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MAKE_OUTPUT_DIR = OUTPUTS_DIR / "make"
MAKE_OUTPUT_URL_PREFIX = "/outputs/make"
VIDEOS_OUTPUT_DIR = OUTPUTS_DIR / "videos"
VIDEOS_OUTPUT_URL_PREFIX = "/outputs/videos"

GITHUB_REPO_URL = "https://github.com/Hakim3i/ComfySprites"
GITHUB_NODES_REPO_URL = "https://github.com/Hakim3i/ComfyUI-ComfySprites"


def ensure_make_outputs() -> None:
    MAKE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
