"""Immutable horizontal background profiles (flat-ground metres and m/s).

All new families evaluate in Python float64. Measured vectors interpolate in
log height by default, or physical height explicitly. Native code receives
only the final physical-layer table. These experimental inputs add no new
atmospheric stability or independent physical validation.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
import json
import math
from types import MappingProxyType

import numpy as np
from ._log import shifted_log as _shifted_log

__all__ = ["LogProfile", "MeasuredProfile", "PowerLawProfile", "UniformProfile",
           "evaluate", "profile_from_dict"]


def _number(value, name, *, positive=False, native=False):
    if isinstance(value, (bool, np.bool_, str, complex)) or np.ndim(value) != 0:
        raise ValueError(f"{name} must be a finite real scalar")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite real scalar") from error
    valid = math.isfinite(value) and (not positive or value > 0)
    if native:
        with np.errstate(over="ignore", under="ignore"):
            narrowed = np.float32(value)
        valid = valid and np.isfinite(narrowed) and (not positive or narrowed > 0)
    if not valid:
        raise ValueError(f"{name} must be {'positive and ' if positive else ''}finite" +
                         (" in float32" if native else ""))
    return value


def _array(values, name):
    try:
        array = np.asarray(values)
        if array.ndim != 1 or array.dtype.kind not in "fiu":
            raise ValueError()
        array = array.astype(np.float64)
        if not np.isfinite(array).all():
            raise ValueError()
        return tuple(array.tolist())
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


class _Profile:
    @property
    def kind(self):
        return _PROFILE_CLASSES[type(self)]

    @property
    def reference(self):
        """Declared reference, using this profile's ground roughness."""
        u, v = map(float, self.evaluate(self.reference_height))
        speed = math.hypot(u, v)
        if not math.isfinite(speed):
            raise ValueError("Reference vector speed must be finite")
        direction = math.degrees(math.atan2(-u, -v)) % 360 if speed else None
        if not isinstance(self, MeasuredProfile):
            # Analytic families define their reference amplitude and direction
            # exactly; do not change normalization through trigonometric rounding.
            speed, direction = self.speed, self.direction if self.speed else None
        return dict(height=self.reference_height, u=u, v=v, speed=speed, direction=direction)

    def evaluate(self, heights):
        array = np.asarray(heights)
        if array.dtype.kind not in "fiu":
            raise ValueError("Evaluation heights must be finite nonnegative real numbers")
        z = array.astype(np.float64)
        if not np.isfinite(z).all() or np.any(z < 0):
            raise ValueError("Evaluation heights must be finite and nonnegative")
        with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
            vectors = self._evaluate(z, self.roughness_length)
        if not np.isfinite(vectors).all():
            raise ValueError("Evaluated profile velocities must remain finite")
        # A calm roof must have the documented atan2(+0,+0)=0 orientation,
        # independent of signed zeros introduced by speed/direction conversion.
        return np.where(vectors == 0, 0.0, vectors)

    def to_dict(self):
        payload = dict(schema_version=2, kind=self.kind,
                       **{f.name: _thaw(getattr(self, f.name)) for f in fields(self)
                          if not f.name.startswith("_")})
        if isinstance(self, MeasuredProfile) and self._measurements is not None:
            payload.pop("u")
            payload.pop("v")
            payload.update(_thaw(self._measurements))
        return payload

    def scaled(self, factor):
        """Multiply every vector by a positive amplitude; preserve shape/turning."""
        factor = _number(factor, "factor", positive=True)
        payload = self.to_dict()
        for name in ("speed", "speeds", "u", "v"):
            if name in payload:
                values = payload[name]
                payload[name] = ([v * factor for v in values] if isinstance(values, list)
                                 else values * factor)
        return profile_from_dict(payload)

    def with_direction(self, direction):
        """Rigidly rotate the reference to direction modulo 360; reject calm."""
        direction = _number(direction, "direction") % 360.
        reference = self.reference
        if not reference["speed"]:
            raise ValueError("Cannot rotate a calm reference")
        payload = self.to_dict()
        delta = direction-reference["direction"]
        if "direction" in payload:
            payload["direction"] = (payload["direction"]+delta) % 360.
        elif "directions" in payload:
            payload["directions"] = [(d+delta) % 360. for d in payload["directions"]]
        else:
            angle = np.deg2rad(delta)
            u, v = np.asarray(payload["u"]), np.asarray(payload["v"])
            payload["u"] = (u*np.cos(angle)+v*np.sin(angle)).tolist()
            payload["v"] = (v*np.cos(angle)-u*np.sin(angle)).tolist()
        return profile_from_dict(payload)


@dataclass(frozen=True)
class LogProfile(_Profile):
    speed: float
    direction: float
    reference_height: float = 10.0
    roughness_length: float = 0.1
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)
        # Match the old public-run gate before any geometry is extracted.
        # Native Log arithmetic uses the narrowed height/roughness and a
        # float32 sum/division; reject overflow and ratios rounding to one.
        height, roughness = float(np.float32(self.reference_height)), float(np.float32(self.roughness_length))
        limit = float(np.finfo(np.float32).max)
        if height + roughness > limit:
            raise ValueError("Reference height and roughness must form a finite float32 log profile")
        ratio = float(np.float32(height + roughness)) / roughness
        if not 1 < ratio <= limit or np.float32(ratio) <= 1:
            raise ValueError("Reference height and roughness must form a finite float32 log profile")

    def _evaluate(self, z, roughness_length):
        ratio = _shifted_log(z, self.roughness_length) / _shifted_log(self.reference_height, self.roughness_length)
        return ratio[..., None] * _vector(self.speed, self.direction)


@dataclass(frozen=True)
class UniformProfile(_Profile):
    speed: float
    direction: float
    reference_height: float = 10.0
    roughness_length: float = 0.1
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)

    def _evaluate(self, z, roughness_length):
        return np.broadcast_to(_vector(self.speed, self.direction), z.shape + (2,)).copy()


@dataclass(frozen=True)
class PowerLawProfile(_Profile):
    speed: float
    direction: float
    reference_height: float
    exponent: float
    roughness_length: float = 0.1
    metadata: Mapping | None = None

    def __post_init__(self):
        _analytic(self)
        object.__setattr__(self, "exponent", _number(self.exponent, "exponent", positive=True))

    def _evaluate(self, z, roughness_length):
        if self.speed == 0:
            return np.zeros(z.shape + (2,), dtype=np.float64)
        return ((z / self.reference_height) ** self.exponent)[..., None] * _vector(self.speed, self.direction)


def _analytic(profile):
    for name in ("speed", "direction", "reference_height"):
        value = _number(getattr(profile, name), name, positive=name == "reference_height", native=True)
        object.__setattr__(profile, name, value)
    if profile.speed < 0 or not 0 <= profile.direction < 360:
        raise ValueError("speed must be nonnegative and direction must be in [0, 360)")
    object.__setattr__(profile, "roughness_length",
                       _number(profile.roughness_length, "roughness_length", positive=True, native=True))
    object.__setattr__(profile, "metadata", _metadata(profile.metadata))


@dataclass(frozen=True, init=False)
class MeasuredProfile(_Profile):
    heights: tuple
    u: tuple
    v: tuple
    reference_height: float
    roughness_length: float = 0.1
    below: str = "error"
    above: str = "constant"
    interpolation: str = "log_height"
    metadata: Mapping | None = None
    _measurements: Mapping | None = field(default=None, repr=False, compare=False)

    def __init__(self, heights, speeds=None, *, direction=None, directions=None, reference_height,
                 roughness_length=0.1, below="error", above="constant", interpolation="log_height", metadata=None, u=None, v=None):
        heights = _array(heights, "heights")
        if len(heights) < 2 or heights[0] <= 0 or np.any(np.diff(heights) <= 0):
            raise ValueError("Measured heights need at least two positive, strictly increasing values")
        metadata = _metadata(metadata)
        measurements = None
        if speeds is not None:
            if u is not None or v is not None or (direction is None) == (directions is None):
                raise ValueError("Supply speeds and either direction or directions; never conflicting components")
            speeds = _array(speeds, "speeds")
            if len(speeds) != len(heights) or any(s < 0 for s in speeds):
                raise ValueError("speeds must match heights and be nonnegative")
            angles = (_array(directions, "directions") if directions is not None else
                      (_number(direction, "direction"),) * len(heights))
            if len(angles) != len(heights) or any(not 0 <= d < 360 for d in angles):
                raise ValueError("directions must match heights and be in [0, 360)")
            components = _vector(speeds, angles)
            u, v = components[:, 0], components[:, 1]
            measurements = dict(speeds=speeds)
            if directions is not None:
                measurements["directions"] = angles
            else:
                measurements["direction"] = angles[0]
            measurements = _freeze(measurements)
        elif direction is not None or directions is not None or u is None or v is None:
            raise ValueError("Supply speeds/direction or both u and v")
        u, v = _array(u, "u"), _array(v, "v")
        if len(u) != len(heights) or len(v) != len(heights):
            raise ValueError("u and v must match heights")
        if below not in ("error", "log") or above not in ("error", "constant"):
            raise ValueError("Unsupported measured profile extrapolation policy")
        if interpolation not in ("log_height", "linear"):
            raise ValueError("interpolation must be log_height or linear")
        height = _number(reference_height, "reference_height", positive=True, native=True)
        roughness = _number(roughness_length, "roughness_length", positive=True, native=True)
        if (height < heights[0] and below == "error") or (height > heights[-1] and above == "error"):
            raise ValueError("Profile coverage does not include the reference height")
        for name, value in dict(heights=heights, u=u, v=v, reference_height=height, roughness_length=roughness, below=below,
                                above=above, interpolation=interpolation, metadata=metadata,
                                _measurements=measurements).items():
            object.__setattr__(self, name, value)

    @classmethod
    def from_directions(cls, heights, speeds, directions, **kwargs):
        return cls(heights, speeds, directions=directions, **kwargs)

    @classmethod
    def from_components(cls, heights, u, v, **kwargs):
        return cls(heights, u=u, v=v, **kwargs)

    def _evaluate(self, z, roughness_length):
        if self.below == "error" and np.any(z < self.heights[0]):
            raise ValueError("Profile coverage: evaluation below first measurement; select an explicit below policy")
        if self.above == "error" and np.any(z > self.heights[-1]):
            raise ValueError("Profile coverage: evaluation above last measurement; select an explicit above policy")
        heights = np.asarray(self.heights)
        query = np.clip(z, heights[0], heights[-1])
        upper = np.clip(np.searchsorted(heights, query), 1, len(heights) - 1)
        lower = upper - 1
        lo, hi = heights[lower], heights[upper]
        if self.interpolation == "log_height":
            # Search in physical height: taking log of the knots first can
            # collapse distinct neighbouring float64 heights. log1p retains
            # their small relative separation; large ratios use log differences.
            with np.errstate(over="ignore"):
                q_ratio, h_ratio = (query - lo) / lo, (hi - lo) / lo
                numerator = np.where(np.isfinite(q_ratio), np.log1p(q_ratio), np.log(query) - np.log(lo))
                denominator = np.where(np.isfinite(h_ratio), np.log1p(h_ratio), np.log(hi) - np.log(lo))
            fraction = numerator / denominator
        else:
            fraction = (query - lo) / (hi - lo)
        vectors = np.column_stack((self.u, self.v))
        out = (1 - fraction)[..., None] * vectors[lower] + fraction[..., None] * vectors[upper]
        if self.below == "log":
            roughness = _number(roughness_length, "roughness_length", positive=True)
            ratio = _shifted_log(np.minimum(z, heights[0]), roughness) / _shifted_log(heights[0], roughness)
            out = np.where((z < heights[0])[..., None], ratio[..., None] * vectors[0], out)
        return out


_PROFILE_CLASSES = {LogProfile: "log", MeasuredProfile: "measured",
                    PowerLawProfile: "power_law", UniformProfile: "uniform"}
PROFILE_TYPES = tuple(_PROFILE_CLASSES)


def profile_from_dict(payload):
    if not isinstance(payload, Mapping):
        raise ValueError("profile must be a JSON-compatible mapping")
    args = dict(payload)
    version = args.pop("schema_version", None)
    if type(version) is not int or version != 2:
        raise ValueError("Profile schema_version=2 is required; migrate v1 payloads by moving roughness_length onto the profile payload")
    kind = args.pop("kind", None)
    classes = {name: cls for cls, name in _PROFILE_CLASSES.items()}
    if not isinstance(kind, str) or kind not in classes:
        raise ValueError("profile kind must be log, measured, power_law or uniform")
    try:
        return classes[kind](**args)
    except TypeError as error:
        raise ValueError(f"Invalid {kind} profile fields: {error}") from error


def _profile_record(profile, heights):
    """One owned record for the canonical inflow at final physical supports.

    Log stays analytic in native code and never allocates a Python layer table.
    Non-log families evaluate once in float64 at the final float32 centres.
    """
    reference = profile.reference
    direction = profile.direction if isinstance(profile, LogProfile) else reference["direction"] or 0.
    record = dict(schema_version=2, kind=profile.kind, requested=profile.to_dict(),
        reference=reference, height_datum="metres above flat ground", horizontal_only=True,
        experimental=not isinstance(profile, LogProfile),
        interpolation=getattr(profile, "interpolation", "analytic"),
        native_reference_scalars=dict(speed=float(np.float32(reference["speed"])),
            direction=float(np.float32(direction)), reference_height=float(np.float32(reference["height"]))),
        boundary_layer="neutral logarithmic" if isinstance(profile, LogProfile) else
                       f"experimental {profile.kind} horizontal profile")
    if isinstance(profile, LogProfile):
        return dict(record, max_turning_deg=0., tail_layers=dict(below=0, above=0), caveats=[])
    z = np.asarray(heights, dtype=np.float64)
    vectors = profile.evaluate(z)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        effective = vectors.astype(np.float32)
        speed = np.hypot(effective[:, 0].astype(float), effective[:, 1].astype(float)).astype(np.float32)
        limit = (speed.astype(float) * 1.2).astype(np.float32)
    if not np.isfinite(effective).all() or not np.isfinite(limit).all():
        raise ValueError("Profile velocities and velocity limit must remain finite in float32 at all grid supports")
    nonzero = speed > 0
    directions = np.arctan2(effective[nonzero, 1].astype(float), effective[nonzero, 0].astype(float))
    turning = float(np.ptp(np.rad2deg(np.unwrap(directions)))) if len(directions) > 1 else 0.0
    if turning < 1e-10:
        turning = 0.0
    measured = isinstance(profile, MeasuredProfile)
    return dict(record, max_turning_deg=turning,
        layer_table=dict(heights=z.tolist(), u=vectors[:, 0].tolist(), v=vectors[:, 1].tolist(),
                         effective_u=effective[:, 0].astype(float).tolist(), effective_v=effective[:, 1].astype(float).tolist()),
        tail_layers=dict(below=int(np.count_nonzero(z < profile.heights[0])) if measured else 0,
                         above=int(np.count_nonzero(z > profile.heights[-1])) if measured else 0),
        caveats=["QES-Turb derives friction velocity from solved speed with a morphometric log-law conversion; "
                          "strong shear or jets can be inconsistent with that conversion. No independent physical validation."])


def evaluate(profile, heights):
    """Evaluate in float64 and return horizontal ``(u, v)`` components.

    Measured lower-log tails use the profile's roughness. No profile parameters or
    borrowed Python buffers cross into native computation.
    """
    if type(profile) not in PROFILE_TYPES:
        raise TypeError("Expected an immutable wind profile")
    vectors = profile.evaluate(heights)
    return vectors[..., 0], vectors[..., 1]


def _pedestrian_sampling(profile, centres, height, record):
    """Component-first background interpolation diagnostics at a planned height.

    Historical Log speed-up arithmetic intentionally uses narrowed native log
    scalars. Other families use their declared profile and reference. No solved
    fields or turbulence arrays are allocated or assessed by these diagnostics.
    """
    upper = int(np.searchsorted(centres, height))
    lower = upper if upper < len(centres) and centres[upper] == height else upper-1
    if lower < 0 or upper >= len(centres):
        raise ValueError("Automatic pedestrian height must have physical cell-centre support")
    a, b = float(centres[lower]), float(centres[upper])
    weight = 0. if lower == upper else (height-a)/(b-a)
    out = dict(height=height, centre_indices=[lower,upper], bracketing_centres=[a,b],
        upper_weight=weight, third_centre=float(centres[2]) if len(centres)>2 else None,
        inflow="unknown" if profile is None else "known",
        profile_kind=None if profile is None else profile.kind,
        reference_height=None, roughness_length=None,
        flat_profile_exact_K=None, flat_profile_interpolated_K=None, flat_profile_bias_K=None,
        exact_velocity_mps=None, interpolated_velocity_mps=None, speed_interpolation_error_mps=None,
        vector_interpolation_error_mps=None, vector_interpolation_error_over_reference=None,
        normalization_unavailable_reason="unknown_inflow" if profile is None else None)
    if profile is None:
        return out
    reference = record["reference"]
    speed = reference["speed"]
    out.update(reference_height=profile.reference_height, roughness_length=profile.roughness_length)
    if isinstance(profile, LogProfile):
        # Keep these operations and their order identical to the old _city
        # diagnostic, including float32 narrowing followed by math.log1p.
        z0, ref = float(np.float32(profile.roughness_length)), float(np.float32(profile.reference_height))
        denominator = math.log1p(ref/z0)
        exact_k = math.log1p(height/z0)/denominator
        interpolated_k = (math.log1p(a/z0)*(1-weight)+math.log1p(b/z0)*weight)/denominator
        vector = np.array([reference["u"],reference["v"]])
        exact, interpolated = vector*exact_k, vector*interpolated_k
        out.update(reference_height=ref, roughness_length=z0, ratio_basis="native_log_scalars")
    else:
        table = record["layer_table"]
        low = np.array([table["u"][lower],table["v"][lower]])
        high = np.array([table["u"][upper],table["v"][upper]])
        interpolated = low+(high-low)*weight
        exact = profile.evaluate(height)
        exact_k = math.hypot(*exact)/speed if speed else None
        interpolated_k = math.hypot(*interpolated)/speed if speed else None
        if isinstance(profile, UniformProfile) and speed:
            exact_k = interpolated_k = 1.
        out["ratio_basis"] = "declared_profile"
    vector_error = math.hypot(*(interpolated-exact))
    out.update(exact_velocity_mps=exact.tolist(), interpolated_velocity_mps=interpolated.tolist(),
        speed_interpolation_error_mps=math.hypot(*interpolated)-math.hypot(*exact),
        vector_interpolation_error_mps=vector_error)
    for key in ("speed_interpolation_error_mps", "vector_interpolation_error_mps"):
        if not math.isfinite(out[key]):
            out[key] = None
    if speed and all(math.isfinite(v) for v in (exact_k, interpolated_k, vector_error/speed)):
        out.update(flat_profile_exact_K=exact_k, flat_profile_interpolated_K=interpolated_k,
                   flat_profile_bias_K=interpolated_k-exact_k,
                   vector_interpolation_error_over_reference=vector_error/speed)
    elif speed:
        out["normalization_unavailable_reason"] = "normalization_not_representable"
    else:
        out["normalization_unavailable_reason"] = "calm_reference"
    return out
