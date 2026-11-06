"""Explicit layers and a provisional automatic vertical-grid policy.

Configuration owns immutable requested faces or automatic settings. Native
coordinates use sequential float32 layer accumulation. Automatic settings are
prototype candidates, pending accuracy/cost validation.
"""

from dataclasses import asdict, dataclass

import numpy as np
from ._validation import real, versioned_mapping

GENERATOR_VERSION = "explicit-v1"
AUTO_GENERATOR_VERSION = "auto-v1-prototype"


@dataclass(frozen=True)
class _AutoSettings:
    pedestrian_height: float = 1.5
    growth_rate: float = 1.15
    min_layer_thickness: float | None = None
    max_aspect_ratio: float = 8.0
    first_layer_thickness: float | None = None
    fine_region_height: float | None = None
    upper_layer_cap: float | None = None

    def __post_init__(self):
        for name, value in asdict(self).items():
            if value is None:
                continue
            value = real(value,name,positive=True)
            object.__setattr__(self, name, value)
        if self.pedestrian_height is None or self.growth_rate is None or self.max_aspect_ratio is None:
            raise ValueError("pedestrian_height, growth_rate and max_aspect_ratio cannot be None")
        if not 1 < self.growth_rate <= 1.20:
            raise ValueError("Automatic growth_rate must be greater than 1 and at most 1.20")
        if self.max_aspect_ratio < 1:
            raise ValueError("max_aspect_ratio must be at least 1")
        if self.fine_region_height is not None and self.fine_region_height < self.pedestrian_height:
            raise ValueError("fine_region_height must be at least pedestrian_height")


@dataclass(frozen=True)
class GridPreview:
    """Owned grid coordinates and diagnostics without allocated wind fields.

    Axes and faces are effective float32 local coordinates. ``dz`` measures
    face separations; ``solver_dz`` holds solver thicknesses before accumulation
    roundoff. Growth/aspect ratios use solver thicknesses, matching metadata.
    ``domain`` records requested/local/global effective bounds and roof errors.
    Arrays and metadata remain editable; a preview is not a prepared solver.
    """
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    z_faces: np.ndarray
    solver_dz: np.ndarray
    origin: tuple[float, float, float]
    crs: str | None
    resolution: float
    domain: dict
    terrain: dict
    eligibility: dict | None = None

    @property
    def shape(self):
        return (len(self.z), len(self.y), len(self.x))

    @property
    def cell_count(self):
        nz, ny, nx = self.shape
        return nz * ny * nx

    @property
    def dz(self):
        return np.diff(self.z_faces)

    @property
    def growth_ratios(self):
        return self.solver_dz[1:] / self.solver_dz[:-1]

    @property
    def thin_cell_aspect_ratios(self):
        return np.float32(self.resolution) / self.solver_dz

    @property
    def tall_cell_aspect_ratios(self):
        return self.solver_dz / np.float32(self.resolution)


def effective_faces(layers):
    """Validate layer arithmetic and return QES's effective physical faces."""
    values = np.asarray(layers, dtype=np.float64)
    if values.ndim != 1 or not 2 <= len(values) <= 10000:
        raise ValueError("Vertical grid requires 2..10000 layers")
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        narrowed = values.astype(np.float32)
        faces = np.r_[np.float32(0), np.cumsum(narrowed, dtype=np.float32)]
        centres = np.float32(0.5) * (faces[:-1] + faces[1:])
        ghosted = np.r_[narrowed[0], narrowed]
        previous = ghosted[:-1]
        following = np.r_[narrowed[1:], narrowed[-1]]
        scales = [narrowed * (np.float32(0.5) * (narrowed + neighbour))
                  for neighbour in (previous, following)]
        coefficients = [np.float32(1) / scale for scale in scales]
    if (not np.isfinite(values).all() or np.any(values <= 0)
            or not np.isfinite(narrowed).all() or np.any(narrowed <= 0)):
        raise ValueError("Vertical layers must be positive and finite in float32")
    if (not np.isfinite(faces).all() or not np.isfinite(centres).all()
            or np.any(np.diff(faces) <= 0) or np.any(np.diff(centres) <= 0)):
        raise ValueError("Vertical coordinates collapse or overflow in float32")
    if any(not np.isfinite(c).all() or np.any(c <= 0) for c in (*scales, *coefficients)):
        raise ValueError("Vertical layers cannot form positive finite float32 solver coefficients")
    return faces


@dataclass(frozen=True)
class VerticalGrid:
    """Immutable explicit faces or provisional automatic policy settings."""

    faces: tuple[float, ...] | None = None
    _automatic: _AutoSettings | None = None

    def __post_init__(self):
        if self._automatic is not None:
            if self.faces is not None or not isinstance(self._automatic, _AutoSettings):
                raise ValueError("Use either explicit faces or VerticalGrid.auto(...) settings")
            return
        try:
            values = np.asarray(self.faces)
        except (TypeError, ValueError) as error:
            raise ValueError("z_faces must be a finite one-dimensional numeric sequence") from error
        if (values.ndim != 1 or values.dtype.kind not in "iuf"
                or not 3 <= len(values) <= 10001):
            raise ValueError("z_faces must contain 3..10001 numeric physical faces")
        values = values.astype(np.float64)
        if not np.isfinite(values).all() or values[0] != 0 or np.any(np.diff(values) <= 0):
            raise ValueError("z_faces must start at zero and be finite and strictly increasing")
        effective_faces(np.diff(values))
        object.__setattr__(self, "faces", tuple(float(v) for v in values))

    @classmethod
    def from_faces(cls, z_faces):
        """Copy face heights above flat ground; at least two layers are required."""
        return cls(z_faces)

    @classmethod
    def auto(cls, *, pedestrian_height=1.5, growth_rate=1.15, min_layer_thickness=None,
             max_aspect_ratio=8, first_layer_thickness=None, fine_region_height=None,
             upper_layer_cap=None):
        """Create a provisional geometry-based policy, resolved by preview/run.

        Lengths are metres above flat ground. first_layer_thickness is a target;
        the fine-band count and constraints determine the actual equal layers.
        No automatic preset has yet passed the C2 accuracy/cost study.
        """
        return cls(_automatic=_AutoSettings(pedestrian_height, growth_rate, min_layer_thickness,
            max_aspect_ratio, first_layer_thickness, fine_region_height, upper_layer_cap))

    @property
    def mode(self):
        return "auto" if self._automatic is not None else "explicit"

    @property
    def layers(self):
        if self._automatic is not None:
            raise ValueError("Automatic layers depend on geometry and bounds; use wind.preview_grid or wind.run")
        return np.ascontiguousarray(np.diff(self.faces), dtype=np.float64)

    def to_metadata(self):
        if self._automatic is not None:
            return dict(mode="auto", generator_version=AUTO_GENERATOR_VERSION,
                        policy_status="prototype_unvalidated", requested_settings=asdict(self._automatic))
        layers = self.layers.astype(np.float32)
        return dict(mode="explicit", generator_version=GENERATOR_VERSION,
                    requested_faces=list(self.faces),
                    uniform=bool(np.all(layers == layers[0])))

    def to_dict(self):
        if self.mode == "auto":
            return dict(schema_version=1, mode="auto", settings=asdict(self._automatic))
        return dict(schema_version=1, mode="explicit", faces=list(self.faces))

    @classmethod
    def from_dict(cls, payload):
        from collections.abc import Mapping
        args = versioned_mapping(payload, "vertical_grid", schema_name="vertical-grid")
        mode = args.pop("mode", None)
        if mode == "explicit" and set(args) == {"faces"}:
            return cls.from_faces(args["faces"])
        if mode == "auto" and set(args) == {"settings"} and isinstance(args["settings"], Mapping):
            try:
                return cls.auto(**args["settings"])
            except TypeError as error:
                raise ValueError(f"Invalid automatic-grid settings: {error}") from error
        raise ValueError("Expected explicit faces or automatic settings without unknown fields")
