"""Diffusion model catalog API for the Animate tab."""

from __future__ import annotations

from typing import Any

from ..services.catalog.diffusion_models import (
    all_diffusion_model_specs,
    default_diffusion_model_id,
    diffusion_model_to_dict,
)
from .router import router


@router.get("/diffusion-models")
def api_diffusion_models() -> dict[str, Any]:
    specs = all_diffusion_model_specs()
    return {
        "default_id": default_diffusion_model_id(),
        "models": [diffusion_model_to_dict(s) for s in specs],
    }
