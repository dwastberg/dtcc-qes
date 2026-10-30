"""Immutable horizontal background profiles above flat ground (metres, m/s).

Measured vectors interpolate component by component in log height by default;
linear physical height is an explicit option.
Opposing directions can therefore give a calm interpolated vector. These are
background fields, not constraints at interior observations. New families are
experimental mean-wind inputs; they do not add atmospheric stability physics.
"""
from dataclasses import dataclass, fields, replace
import json
import math
from types import MappingProxyType
from collections.abc import Mapping

import numpy as np

__all__ = ["LogProfile", "MeasuredProfile", "PowerLawProfile", "UniformProfile",
           "evaluate", "profile_from_dict"]


def _number(value, name, *, positive=False, native=False):
    if isinstance(value, (bool, str, complex)) or np.ndim(value) != 0:
        raise ValueError(f"{name} must be a finite real scalar")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite real scalar") from error
    with np.errstate(over="ignore", under="ignore"):
        narrowed = np.float32(value)
    if (not math.isfinite(value) or (positive and value <= 0) or
            (native and (not np.isfinite(narrowed) or (positive and narrowed <= 0)))):
        raise ValueError(f"{name} must be {'positive and ' if positive else ''}finite" + (" in float32" if native else ""))
    return value


def _array(values, name):
    if np.iscomplexobj(values):
        raise ValueError(f"{name} must be real")
    try:
        array = np.asarray(values)
        if array.ndim != 1 or array.dtype.kind not in "fiu":
            raise ValueError()
        return tuple(_number(v, name) for v in array)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a one-dimensional finite real array") from error


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def _metadata(value):
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a JSON-compatible mapping")
    try:
        return _freeze(json.loads(json.dumps(_thaw(value), allow_nan=False)))
    except (TypeError, ValueError) as error:
        raise ValueError("metadata must be a JSON-compatible mapping") from error


def _vector(speed, direction):
    angle = np.deg2rad(direction)
    return np.stack((-np.asarray(speed) * np.sin(angle), -np.asarray(speed) * np.cos(angle)), axis=-1)


def _reference(vector, height):
    u, v = map(float, vector)
    speed = math.hypot(u, v)
    direction = float(math.degrees(math.atan2(-u, -v)) % 360) if speed else None
    return dict(height=height, u=u, v=v, speed=speed, direction=direction)


class _Profile:
    @property
    def kind(self):
        return {LogProfile: "log", MeasuredProfile: "measured", PowerLawProfile: "power_law",
                UniformProfile: "uniform"}[type(self)]

    @property
    def reference(self):
        return self.reference_at()

    def reference_at(self, roughness_length=0.1):
        return _reference(self.evaluate(self.reference_height, roughness_length), self.reference_height)

    @property
    def turning(self):
        return False

    def to_dict(self):
        return dict(schema_version=1, kind=self.kind,
                    **{f.name: _thaw(getattr(self, f.name)) for f in fields(self)})

    def record(self, heights=None, roughness_length=0.1):
        reference = self.reference_at(roughness_length)
        record = dict(schema_version=1, type=self.kind, requested=self.to_dict(),
                      reference=reference, height_datum="metres above flat ground", horizontal_only=True,
                      interpolation=getattr(self, "interpolation", "analytic"),
                      experimental=self.kind != "log", turning=self.turning)
        if heights is not None:
            z = np.asarray(heights, dtype=np.float64)
            uv = self.evaluate(z, roughness_length)
            with np.errstate(over="ignore"):
                effective = uv.astype(np.float32)
            if not np.isfinite(effective).all():
                raise ValueError("Profile velocities must remain finite in float32")
            directions = np.arctan2(uv[:, 1], uv[:, 0])[np.hypot(uv[:, 0], uv[:, 1]) > 0]
            turning = float(np.ptp(np.rad2deg(np.unwrap(directions)))) if len(directions) > 1 else 0.0
            if turning < 1e-10:
                turning = 0.0
            record.update(max_turning_deg=turning,
                layer_table=dict(heights=z.tolist(), u=uv[:, 0].tolist(), v=uv[:, 1].tolist(),
                                 effective_u=effective[:, 0].astype(float).tolist(), effective_v=effective[:, 1].astype(float).tolist()),
                tail_layers=dict(below=int(np.count_nonzero(z < self.heights[0])) if self.kind == "measured" else 0,
                                 above=int(np.count_nonzero(z > self.heights[-1])) if self.kind == "measured" else 0))
        if self.kind != "log":
            record["turbulence_caveat"] = (
                "QES-Turb derives friction velocity from solved speed with a morphometric log-law conversion; "
                "strong shear or jets can be inconsistent with that conversion. No independent physical validation.")
        return record

    def scaled(self, factor):
        """Multiply all vectors by a positive amplitude; preserve shape and turning."""
        factor = _number(factor, "factor", positive=True)
        if isinstance(self, MeasuredProfile):
            return replace(self, u=tuple(v * factor for v in self.u), v=tuple(v * factor for v in self.v))
        return replace(self, speed=self.speed * factor)

    def _heights(self, heights):
        if np.iscomplexobj(heights):
            raise ValueError("Evaluation heights must be real")
        z = np.asarray(heights, dtype=np.float64)
        if not np.isfinite(z).all() or np.any(z < 0):
            raise ValueError("Evaluation heights must be finite and nonnegative")
        return z

    def check_coverage(self, heights, roughness_length=0.1):
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            vectors = self.evaluate(heights, roughness_length)
            narrowed = np.asarray(vectors, dtype=np.float32)
        if (not np.isfinite(narrowed).all() or
                np.any(np.linalg.norm(vectors, axis=-1) > float(np.finfo(np.float32).max) / 1.2)):
            raise ValueError("Profile velocities must remain finite in float32 at all grid supports")


@dataclass(frozen=True)
class LogProfile(_Profile):
    speed: float
    direction: float
    reference_height: float = 10.0
    roughness_length: float = 0.1
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)
        object.__setattr__(self, "roughness_length", _number(self.roughness_length, "roughness_length", positive=True))
        z, z0 = np.float32(self.reference_height), np.float32(self.roughness_length)
        with np.errstate(over="ignore", divide="ignore"):
            ratio = (z + z0) / z0
        if not np.isfinite(ratio) or ratio <= 1:
            raise ValueError("Reference height and roughness must form a finite float32 log profile")

    def evaluate(self, heights, roughness_length=0.1):
        z = self._heights(heights)
        return (np.log1p(z / self.roughness_length) / math.log1p(self.reference_height / self.roughness_length))[..., None] * _vector(self.speed, self.direction)


@dataclass(frozen=True)
class UniformProfile(_Profile):
    speed: float
    direction: float
    reference_height: float = 10.0
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)

    def evaluate(self, heights, roughness_length=0.1):
        z = self._heights(heights)
        return np.broadcast_to(_vector(self.speed, self.direction), z.shape + (2,)).copy()


@dataclass(frozen=True)
class PowerLawProfile(_Profile):
    speed: float
    direction: float
    reference_height: float
    exponent: float
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)
        object.__setattr__(self, "exponent", _number(self.exponent, "exponent", positive=True))

    def evaluate(self, heights, roughness_length=0.1):
        z = self._heights(heights)
        return ((z / self.reference_height) ** self.exponent)[..., None] * _vector(self.speed, self.direction)


def _analytic(profile):
    for name in ("speed", "direction", "reference_height"):
        object.__setattr__(profile, name, _number(getattr(profile, name), name, positive=name == "reference_height", native=True))
    if profile.speed < 0 or not 0 <= profile.direction < 360:
        raise ValueError("speed must be nonnegative and direction must be in [0, 360)")
    object.__setattr__(profile, "metadata", _metadata(profile.metadata))


@dataclass(frozen=True, init=False)
class MeasuredProfile(_Profile):
    heights: tuple
    u: tuple
    v: tuple
    reference_height: float
    below: str = "error"
    above: str = "constant"
    interpolation: str = "log_height"
    metadata: Mapping | None = None

    def __init__(self, heights, speeds=None, *, direction=None, directions=None, reference_height,
                 below="error", above="constant", interpolation="log_height", metadata=None, u=None, v=None):
        heights = _array(heights, "heights")
        if len(heights) < 2 or heights[0] <= 0 or np.any(np.diff(heights) <= 0):
            raise ValueError("Measured heights need at least two positive, strictly increasing values")
        if speeds is not None:
            if u is not None or v is not None or (direction is None) == (directions is None):
                raise ValueError("Supply speeds and either direction or directions; never conflicting components")
            speeds = _array(speeds, "speeds")
            if len(speeds) != len(heights) or any(s < 0 for s in speeds):
                raise ValueError("speeds must match heights and be nonnegative")
            angles = _array(directions, "directions") if directions is not None else (_number(direction, "direction"),) * len(heights)
            if len(angles) != len(heights) or any(not 0 <= d < 360 for d in angles):
                raise ValueError("directions must match heights and be in [0, 360)")
            components = _vector(speeds, angles)
            u, v = components[:, 0], components[:, 1]
            # Retain the submitted measurements, including scalar/vector-mean provenance.
            provenance = dict(metadata or {})
            provenance["measurements"] = dict(speeds=list(speeds), directions=list(angles))
            metadata = provenance
        elif direction is not None or directions is not None or u is None or v is None:
            raise ValueError("Supply speeds/direction or both u and v")
        u, v = _array(u, "u"), _array(v, "v")
        if len(u) != len(heights) or len(v) != len(heights):
            raise ValueError("u and v must match heights")
        if np.any(np.hypot(u, v) > float(np.finfo(np.float32).max)):
            raise ValueError("Measured vector speeds must remain finite in float32")
        if below not in ("error", "log") or above not in ("error", "constant"):
            raise ValueError("Unsupported measured profile extrapolation policy")
        if interpolation not in ("log_height", "linear"):
            raise ValueError("interpolation must be log_height or linear")
        for name, value in dict(heights=heights, u=u, v=v, reference_height=_number(reference_height, "reference_height", positive=True, native=True),
                                below=below, above=above, interpolation=interpolation, metadata=_metadata(metadata)).items():
            object.__setattr__(self, name, value)
        self.evaluate(self.reference_height)  # Reference coverage is mandatory.
        ref = self.reference
        if not math.isfinite(ref["speed"]) or ref["speed"] > np.finfo(np.float32).max:
            raise ValueError("Reference vector speed must be finite in float32")

    @classmethod
    def from_directions(cls, heights, speeds, directions, **kwargs):
        return cls(heights, speeds, directions=directions, **kwargs)

    @classmethod
    def from_components(cls, heights, u, v, **kwargs):
        return cls(heights, u=u, v=v, **kwargs)

    @property
    def turning(self):
        vectors = np.column_stack((self.u, self.v))
        speeds = np.linalg.norm(vectors, axis=1)
        unit = vectors[speeds > 0] / speeds[speeds > 0, None]
        return len(unit) > 1 and bool(np.any(np.linalg.norm(unit - unit[0], axis=1) > 1e-6))

    def evaluate(self, heights, roughness_length=0.1):
        z = self._heights(heights)
        if self.below == "error" and np.any(z < self.heights[0]):
            raise ValueError("Profile coverage: evaluation below first measurement; select an explicit below policy")
        if self.above == "error" and np.any(z > self.heights[-1]):
            raise ValueError("Profile coverage: evaluation above last measurement; select an explicit above policy")
        coordinates = np.log(self.heights) if self.interpolation == "log_height" else self.heights
        # Evaluate only positive log coordinates; lower tails handle ground.
        query = np.log(np.maximum(z, self.heights[0])) if self.interpolation == "log_height" else z
        out = np.stack((np.interp(query, coordinates, self.u), np.interp(query, coordinates, self.v)), axis=-1)
        if self.below != "error":
            roughness_length = _number(roughness_length, "roughness_length", positive=True, native=True)
            ratio = np.log1p(z / roughness_length) / math.log1p(self.heights[0] / roughness_length)
            out = np.where((z < self.heights[0])[..., None], ratio[..., None] * np.array((self.u[0], self.v[0])), out)
        return out


PROFILE_TYPES = (LogProfile, MeasuredProfile, PowerLawProfile, UniformProfile)


def profile_from_dict(payload):
    if not isinstance(payload, Mapping):
        raise ValueError("profile must be a JSON-compatible mapping")
    args = dict(payload)
    version = args.pop("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported profile schema_version")
    kind = args.pop("kind", None)
    classes = {"log": LogProfile, "measured": MeasuredProfile, "power_law": PowerLawProfile, "uniform": UniformProfile}
    if kind not in classes:
        raise ValueError("profile kind must be log, measured, power_law or uniform")
    try:
        return classes[kind](**args)
    except TypeError as error:
        raise ValueError(f"Invalid {kind} profile fields: {error}") from error


def evaluate(profile, heights, roughness_length=0.1):
    """Evaluate an immutable profile in float64; return horizontal ``(u, v)``.

    Heights are physical metres above flat ground. Measured lower-log tails use
    the run's roughness; native code receives only the final per-layer table.
    """
    if not isinstance(profile, PROFILE_TYPES):
        raise TypeError("Expected an immutable wind profile")
    vectors = profile.evaluate(heights, roughness_length)
    return vectors[..., 0], vectors[..., 1]
