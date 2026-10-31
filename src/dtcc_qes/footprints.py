"""Settings for canonical footprint preparation."""

from dataclasses import dataclass
from typing import Literal

from ._city import number


@dataclass(frozen=True)
class Footprints:
    """Geometry cleaning policy, independent of the simulation resolution.

    Pass to ``wind.run`` or ``wind.preview_grid`` to clean footprints and use
    canonical height-preserving solids. ``None`` keeps the strict input contract.
    """

    min_detail: float = 0.5
    exposed_faces: bool = True
    fallback: Literal["error", "tallest"] = "error"

    def __post_init__(self):
        object.__setattr__(self, "min_detail", number(self.min_detail, "min_detail", positive=True))
        if type(self.exposed_faces) is not bool:
            raise ValueError("exposed_faces must be a bool")
        if not isinstance(self.fallback, str) or self.fallback not in ("error", "tallest"):
            raise ValueError("fallback must be 'error' or 'tallest'")
