"""JSON REST API mounted under ``/api``."""

from .router import router

from . import lora as _lora  # noqa: F401
from . import animations as _animations  # noqa: F401
from . import design_entities as _design_entities  # noqa: F401
from . import backgrounds as _backgrounds  # noqa: F401
from . import core as _core  # noqa: F401
from . import styles as _styles  # noqa: F401
from . import views as _views  # noqa: F401
from . import make as _make  # noqa: F401
from . import gallery as _gallery  # noqa: F401
from . import diffusion_models as _diffusion_models  # noqa: F401
from . import animate as _animate  # noqa: F401

__all__ = ["router"]
