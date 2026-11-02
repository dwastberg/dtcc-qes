"""dtcc-qes inflow profiles built from the AIJ approach-flow tables.

The baseline is a ``MeasuredProfile`` through the tabulated points at full-scale
heights, with a shifted-log tail below the lowest point (``below="log"``), its
roughness fitted to the lowest points. Power-law and log fits are the
sensitivity variants. QES is linear in the inflow speed, so the wind-tunnel
speeds are used unchanged; results are normalised by the profile's own speed at
the reference height (``reference_speed``).

The ground roughness of a profile reaches native code only through the
turbulence wall model (``TURBWallTerrain``) and the measured lower tail, so it
does not change the mean wind above the lowest measured point.

The "canopy" inflow (Phase 5) keeps the measured approach profile above a
blending height z_b and replaces it below with a shifted log law of urban
roughness z0_u, U(z) = U_a(z_b) ln(1 + z/z0_u) / ln(1 + z_b/z0_u). It
represents the slowing inside a district that the building parameterizations
do not reach. Its results are normalised by the *approach* flow
(``approach_profile``), as the tunnel data are.
"""

from typing import NamedTuple

import numpy as np
from dtcc_qes.profiles import LogProfile, MeasuredProfile, PowerLawProfile

from .tables import Inflow

KINDS = ("measured", "power_law", "log", "canopy")
FIT_HEIGHT = {"D": 200.0, "E": 100.0}  # m: power-law and log fits use points up to 2 H (D) and 0.4 Z_R (E)
TAIL_POINTS = 4  # lowest points used for the roughness of the measured profile's log tail
CANOPY_LOWEST = 0.1  # m: lowest tabulated canopy point, below every cell centre down to 0.25 m layers
CANOPY_POINTS = 40  # log-spaced points of the canopy law below the blending height


class LogFit(NamedTuple):
    roughness_length: float  # z0 of U = a ln(1 + z/z0), the law of LogProfile and below="log"
    amplitude: float  # a = u*/kappa
    rms: float  # m/s, over the fitted points
    points: int


class PowerFit(NamedTuple):
    exponent: float
    speed: float  # m/s at the reference height
    reference_height: float
    rms: float  # m/s, over the fitted points
    points: int


def _subset(heights, speeds, max_height=None, count=None):
    heights, speeds = np.asarray(heights, dtype=np.float64), np.asarray(speeds, dtype=np.float64)
    keep = np.ones(heights.shape, dtype=bool) if max_height is None else heights <= max_height
    if count is not None:
        keep &= np.arange(len(heights)) < count
    if keep.sum() < 2:
        raise ValueError("A profile fit needs at least two points")
    return heights[keep], speeds[keep]


def fit_log(heights, speeds, max_height=None, count=None) -> LogFit:
    """Least-squares fit of U = a·ln(1 + z/z0); z0 by a log-spaced search, then golden-section refinement."""
    z, u = _subset(heights, speeds, max_height, count)

    def residual(log_z0):
        x = np.log1p(z / 10.0 ** log_z0)
        a = float(x @ u / (x @ x))
        return float(np.sqrt(np.mean((a * x - u) ** 2))), a

    grid = np.linspace(-8.0, np.log10(z.max()), 401)
    errors = [residual(g)[0] for g in grid]
    i = int(np.argmin(errors))
    lo, hi = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    ratio = (np.sqrt(5.0) - 1) / 2
    for _ in range(80):
        a, b = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
        if residual(a)[0] < residual(b)[0]:
            hi = b
        else:
            lo = a
    best = (lo + hi) / 2
    rms, amplitude = residual(best)
    return LogFit(float(10.0 ** best), amplitude, rms, len(z))


def fit_power_law(heights, speeds, reference_height, max_height=None) -> PowerFit:
    """Least-squares fit of ln U = ln U_ref + α ln(z/z_ref)."""
    z, u = _subset(heights, speeds, max_height)
    x = np.log(z / reference_height)
    exponent, intercept = np.polyfit(x, np.log(u), 1)
    speed = float(np.exp(intercept))
    rms = float(np.sqrt(np.mean((speed * (z / reference_height) ** exponent - u) ** 2)))
    return PowerFit(float(exponent), speed, float(reference_height), rms, len(z))


def _metadata(inflow, kind, **fit):
    return dict(source=f"AIJ Case {inflow.case} Inflow sheet", kind=kind, **fit)


def measured_profile(inflow: Inflow, direction: float, *, tail_points: int = TAIL_POINTS,
                     interpolation: str = "log_height", roughness_length: float | None = None) -> MeasuredProfile:
    """The tabulated profile; below the lowest point a shifted-log tail with fitted z0.

    ``roughness_length`` replaces the fitted tail z0, for the tail and the QES-Turb wall model.
    """
    tail = fit_log(inflow.heights, inflow.speeds, count=tail_points)
    z0 = tail.roughness_length if roughness_length is None else float(roughness_length)
    return MeasuredProfile(inflow.heights, inflow.speeds, direction=float(direction),
                           reference_height=inflow.reference["height"],
                           roughness_length=z0, below="log", above="constant",
                           interpolation=interpolation,
                           metadata=_metadata(inflow, "measured", tail_points=tail_points,
                                              tail_rms=tail.rms, tail_roughness=tail.roughness_length))


def canopy_profile(inflow: Inflow, direction: float, *, canopy_roughness: float, blending_height: float,
                   interpolation: str = "log_height", roughness_length: float | None = None) -> MeasuredProfile:
    """The approach profile above ``blending_height``; below it the in-canopy shifted log law.

    The ground roughness (tail and QES-Turb) stays that of the approach profile unless
    ``roughness_length`` is given, so only the mean inflow changes.
    """
    approach = measured_profile(inflow, direction, interpolation=interpolation, roughness_length=roughness_length)
    speed_b = reference_speed(approach, blending_height)
    low = np.geomspace(CANOPY_LOWEST, blending_height, CANOPY_POINTS, endpoint=False)
    law = speed_b * np.log1p(low / canopy_roughness) / np.log1p(blending_height / canopy_roughness)
    above = inflow.heights > blending_height
    return MeasuredProfile(np.r_[low, blending_height, inflow.heights[above]],
                           np.r_[law, speed_b, inflow.speeds[above]], direction=float(direction),
                           reference_height=inflow.reference["height"],
                           roughness_length=approach.roughness_length, below="log", above="constant",
                           interpolation=interpolation,
                           metadata=_metadata(inflow, "canopy", canopy_roughness=float(canopy_roughness),
                                              blending_height=float(blending_height)))


def approach_profile(inflow: Inflow, kind: str, direction: float, **options):
    """The profile that normalises K: the inflow itself, or the measured approach flow for "canopy"."""
    if kind == "canopy":
        options = {k: v for k, v in options.items() if k in ("interpolation", "roughness_length")}
        return measured_profile(inflow, direction, **options)
    return profile(inflow, kind, direction, **options)


def power_law_profile(inflow: Inflow, direction: float, max_height: float | None = None) -> PowerLawProfile:
    """Power law fitted up to ``max_height`` (default ``FIT_HEIGHT``) through the reference height."""
    max_height = FIT_HEIGHT[inflow.case] if max_height is None else max_height
    fit = fit_power_law(inflow.heights, inflow.speeds, inflow.reference["height"], max_height)
    tail = fit_log(inflow.heights, inflow.speeds, count=TAIL_POINTS)
    return PowerLawProfile(fit.speed, float(direction), fit.reference_height, fit.exponent,
                           roughness_length=tail.roughness_length,
                           metadata=_metadata(inflow, "power_law", max_height=max_height, rms=fit.rms))


def log_profile(inflow: Inflow, direction: float, max_height: float | None = None) -> LogProfile:
    """Shifted log law fitted up to ``max_height`` (default ``FIT_HEIGHT``)."""
    max_height = FIT_HEIGHT[inflow.case] if max_height is None else max_height
    fit = fit_log(inflow.heights, inflow.speeds, max_height)
    height = inflow.reference["height"]
    speed = fit.amplitude * float(np.log1p(height / fit.roughness_length))
    return LogProfile(speed, float(direction), height, fit.roughness_length,
                      metadata=_metadata(inflow, "log", max_height=max_height, rms=fit.rms))


def profile(inflow: Inflow, kind: str, direction: float, **options):
    """The inflow profile of ``kind`` ("measured", "power_law", "log" or "canopy") for one direction."""
    builders = dict(measured=measured_profile, power_law=power_law_profile, log=log_profile, canopy=canopy_profile)
    if kind not in builders:
        raise ValueError(f"kind must be one of {KINDS}")
    return builders[kind](inflow, direction, **options)


def reference_speed(profile, height: float | None = None) -> float:
    """Horizontal speed of ``profile`` at ``height`` (default: its reference height)."""
    height = profile.reference_height if height is None else height
    return float(np.hypot(*profile.evaluate(np.array([height]))[0]))
