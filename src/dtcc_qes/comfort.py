"""Pedestrian wind comfort from an hourly wind climate and per-direction speed fields.

Independent of any wind solver: ``fields`` holds pedestrian-level mean wind
speed for each simulated direction, computed with a known ``reference_speed``.
The hourly climate must be expressed at that same reference (height and
upstream roughness); ``log_law_transfer`` converts station winds.

Pedestrian speed in hour t is K_d(t) * V_t, where V_t is the hourly speed,
K_d = field_d / reference_speed_d and d(t) is the field direction nearest to
the hourly direction. This assumes normalised fields do not depend on wind
speed: QES satisfies it; Reynolds-independent RANS and wind-tunnel data do
approximately. Exceedance is the fraction of valid hours above a speed, summed
over all directions, as in the City of London guideline (Annex A).

Directions are meteorological (where the wind comes FROM), in degrees
clockwise from north, for both the hourly climate and the fields.
"""

from dataclasses import dataclass
from collections.abc import Mapping
from copy import deepcopy
from typing import NamedTuple

import numpy as np
from ._log import shifted_log
from ._validation import real as _number

__all__ = ["Rule", "Rating", "Criterion", "ComfortResult", "NEN8100", "CITY_OF_LONDON",
           "assess", "assess_results", "exceedance", "speed_at_exceedance", "log_law_transfer", "gust_equivalent_mean"]

SEASONS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11)}


class Rule(NamedTuple):
    """Speed (m/s) exceeded for at most ``fraction`` of hours; equality passes if inclusive."""
    speed: float
    fraction: float
    inclusive: bool = True


@dataclass(frozen=True)
class Rating:
    """Ordered classes from best to worst; the first satisfied rule wins.

    The final label applies where no rule is satisfied. Speeds and fractions
    may not decrease, so a cell satisfying one rule satisfies all later rules.
    """
    labels: tuple[str, ...]
    rules: tuple[Rule, ...]

    def __post_init__(self):
        rules = tuple(Rule(*rule) for rule in self.rules)
        if not rules or len(self.labels) != len(rules) + 1:
            raise ValueError("A rating needs at least one rule and one more label than rules")
        for rule in rules:
            if not (np.isfinite(rule.speed) and rule.speed > 0 and 0 < rule.fraction < 1):
                raise ValueError("Rule speeds must be positive and fractions within (0, 1)")
        if any(b.speed < a.speed or b.fraction < a.fraction for a, b in zip(rules, rules[1:])):
            raise ValueError("Rule speeds and fractions must not decrease")
        object.__setattr__(self, "labels", tuple(self.labels))
        object.__setattr__(self, "rules", rules)


@dataclass(frozen=True)
class Criterion:
    """A comfort and a safety rating with the speed measure they are defined on.

    ``height`` is the criterion's evaluation height in metres; fields are taken
    as given and it is only compared with the caller's stated height.
    ``gust_equivalent`` criteria use the worse of mean and gust equivalent
    mean (GEM) speeds. ``seasonal_comfort`` criteria report comfort for the
    worst season; safety is always assessed on all hours. ``activities`` maps
    an activity to a rating index (into ``activity_labels``) per comfort class.
    """
    name: str
    height: float
    comfort: Rating
    safety: Rating
    gust_equivalent: bool = False
    seasonal_comfort: bool = False
    activity_labels: tuple[str, ...] = ()
    activities: tuple[tuple[str, tuple[int, ...]], ...] = ()


# NEN 8100:2006: hourly mean at 1.75 m. Comfort classes are half-open bins of
# hours above 5 m/s (A < 2.5 % ... E >= 20 %); danger is p <= 0.05 % no risk,
# 0.05 % < p < 0.30 % limited risk (traversing only), p >= 0.30 % dangerous.
NEN8100 = Criterion(
    name="NEN 8100", height=1.75,
    comfort=Rating(("A", "B", "C", "D", "E"),
                   tuple(Rule(5.0, p, inclusive=False) for p in (0.025, 0.05, 0.10, 0.20))),
    safety=Rating(("no risk", "limited risk", "dangerous"),
                  (Rule(15.0, 0.0005), Rule(15.0, 0.003, inclusive=False))),
    activity_labels=("good", "moderate", "poor"),
    activities=(("traversing", (0, 0, 0, 1, 2)), ("strolling", (0, 0, 1, 2, 2)),
                ("sitting", (0, 1, 2, 2, 2))),
)

# City of London Wind Microclimate Guidelines (2019): mean and GEM speed
# exceeded 5 % of the time (worst season; summer reported separately), and a
# 15 m/s pedestrian safety limit exceeded 0.022 % of the year.
CITY_OF_LONDON = Criterion(
    name="City of London Lawson (2019)", height=1.5,
    comfort=Rating(("frequent sitting", "occasional sitting", "standing", "walking", "uncomfortable"),
                   tuple(Rule(speed, 0.05) for speed in (2.5, 4.0, 6.0, 8.0))),
    safety=Rating(("safe", "unsafe"), (Rule(15.0, 0.00022),)),
    gust_equivalent=True, seasonal_comfort=True,
)


@dataclass(frozen=True)
class ComfortResult:
    """Class maps on the field grid; -1 marks cells with any NaN field value.

    ``comfort`` and ``safety`` index ``criterion.comfort.labels`` and
    ``criterion.safety.labels``, from best to worst. ``exceedance`` maps each
    criterion speed (m/s) to the fraction of all valid hours above it.
    ``seasonal`` maps season names to comfort classes when assessed per season.
    """
    criterion: Criterion
    comfort: np.ndarray
    safety: np.ndarray
    exceedance: dict
    seasonal: dict
    warnings: tuple[str, ...]
    metadata: dict

    def activity(self, name):
        """Rating index per cell for one activity, into ``criterion.activity_labels``."""
        table = dict(self.criterion.activities)
        if name not in table:
            raise ValueError(f"{self.criterion.name} defines no activity {name!r}")
        ratings = np.asarray(table[name], dtype=np.int8)
        return np.where(self.comfort >= 0, ratings[np.maximum(self.comfort, 0)], np.int8(-1))


def gust_equivalent_mean(speed, streamwise_std, *, peak_factor: float,
                         gust_ratio: float = 1.85) -> np.ndarray:
    """Estimate GEM as ``(speed + peak_factor * streamwise_std) / gust_ratio``.

    Inputs are equal-shape nonnegative speeds/deviations in m/s; NaN propagates.
    The result is float64. Infinities, negative values, unequal shapes, invalid
    factors and overflowing estimates raise ValueError. Factors must be finite
    positive scalars. ``peak_factor`` is required and has no calibrated default.

    The City of London Wind Microclimate Guidelines (2019), printed p. 11,
    defines gust speed / 1.85. It does not establish a QES-Turb peak factor or
    gust averaging duration. A peak estimate from QES's algebraic stresses is
    unvalidated screening; record factors and averaging-time assumptions in
    ``assess(..., gem_metadata=...)``. Unknown durations remain unspecified.
    See https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf
    """
    factors = []
    for name, value in (("peak_factor", peak_factor), ("gust_ratio", gust_ratio)):
        if np.ndim(value) != 0 or np.asarray(value).dtype.kind in ("b", "c"):
            raise ValueError(f"{name} must be a positive finite scalar")
        value = _number(value, name, nonnegative=True)
        if value <= 0:
            raise ValueError(f"{name} must be a positive finite scalar")
        factors.append(value)
    peak_factor, gust_ratio = factors
    try:
        if np.iscomplexobj(speed) or np.iscomplexobj(streamwise_std):
            raise ValueError("GEM inputs must be real")
        speed = np.asarray(speed, dtype=np.float64)
        std = np.asarray(streamwise_std, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("speed and streamwise_std must be numeric real arrays") from error
    if speed.shape != std.shape:
        raise ValueError("speed and streamwise_std must have the same shape")
    if np.isinf(speed).any() or np.isinf(std).any() or np.any(speed < 0) or np.any(std < 0):
        raise ValueError("speed and streamwise_std must be nonnegative, finite or NaN")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        estimate = np.asarray((speed + peak_factor * std) / gust_ratio, dtype=np.float64)
    if np.isinf(estimate).any():
        raise ValueError("GEM estimate overflows float64")
    return estimate


def assess(speeds, directions, fields, field_directions, reference_speed, criterion=NEN8100, *,
           gem_fields=None, gem_metadata=None, run_metadata=None, times=None, height=None) -> ComfortResult:
    """Classify comfort and safety for every field cell.

    ``speeds`` and ``directions`` are hourly (T,) arrays; ``fields`` is a
    (D, N, M) stack (any trailing shape works, e.g. probe points) of mean
    pedestrian speeds for ``field_directions`` (D,), simulated with
    ``reference_speed`` (scalar or (D,)). NaN field values mark cells without
    a result, such as buildings.

    Hours with a non-finite speed, or a non-finite direction and nonzero speed,
    are excluded and counted; calm hours (speed 0) remain in the statistics.
    ``gem_fields`` (same shape as ``fields``) is required for a full
    gust-equivalent criterion; each speed's exceedance is then the larger of
    the mean and GEM values, matching "the worse category of the two". Without
    it, a warning states that results are mean-only. ``times`` (T,
    datetime64) enables per-season comfort for seasonal criteria. ``height``
    records the fields' height in metres and warns when it differs from the
    criterion's.

    Optional ``gem_metadata`` is a mapping of source/model, factors, averaging
    times and limitations, deep-copied into ``metadata['gem']``. It requires
    ``gem_fields``. QES provenance in source/model/numerics_version preserves
    an unvalidated-gust screening warning. Missing source/model provenance is
    warned about; supplying GEM does not establish validation or compliance.
    """
    if not isinstance(criterion, Criterion):
        raise ValueError("criterion must be a comfort.Criterion such as NEN8100 or CITY_OF_LONDON")
    if gem_metadata is not None and gem_fields is None:
        raise ValueError("gem_metadata requires gem_fields")
    if gem_metadata is not None and not isinstance(gem_metadata, Mapping):
        raise ValueError("gem_metadata must be a mapping")
    provenance = deepcopy(dict(gem_metadata)) if gem_metadata is not None else {}
    if run_metadata is not None and not isinstance(run_metadata, Mapping):
        raise ValueError("run_metadata must be a mapping")
    if gem_fields is not None and not criterion.gust_equivalent:
        raise ValueError(f"{criterion.name} is defined on mean speeds; gem_fields is not used")
    hourly = _Hourly(speeds, directions, field_directions, times)
    ratios = [_ratios(fields, hourly.field_directions, reference_speed)]
    if gem_fields is not None:
        ratios.append(_ratios(gem_fields, hourly.field_directions, reference_speed))
        if ratios[1].shape != ratios[0].shape:
            raise ValueError("gem_fields must have the same shape as fields")
    invalid = np.any([np.isnan(k).any(axis=0) for k in ratios], axis=0)
    annual = _Climate(hourly.speeds, hourly.sectors, len(hourly.field_directions))
    speeds_used = sorted({rule.speed for rule in criterion.comfort.rules + criterion.safety.rules})
    fractions = {speed: _governing(annual, ratios, speed, invalid) for speed in speeds_used}
    safety = _classify(criterion.safety, fractions, invalid)

    warnings, seasonal = [], {}
    if criterion.gust_equivalent and gem_fields is None:
        warnings.append(f"Mean speeds only: {criterion.name} also applies gust equivalent mean (GEM) "
                        "speeds; results are non-conservative where gusts govern.")
    if gem_fields is not None:
        identifiers = (provenance.get(key) for key in ("source", "model", "numerics_version"))
        if any(isinstance(value, str) and "qes" in value.casefold() for value in identifiers):
            warnings.append("QES-Turb GEM is an algebraic screening estimate, not validated for pedestrian gusts; "
                            "peak factors and averaging times are modelling assumptions.")
        elif not any(isinstance(provenance.get(key), str) and
                     provenance[key].strip().casefold() not in ("", "unspecified") for key in ("source", "model")):
            warnings.append("GEM source/model provenance is unspecified; supplying GEM fields does not establish "
                            "gust validation or guideline compliance.")
    if criterion.seasonal_comfort and hourly.months is not None:
        for season, months in SEASONS.items():
            selected = np.isin(hourly.months, months)
            if not selected.any():
                raise ValueError(f"times contain no valid {season} hours; seasonal comfort needs all seasons")
            climate = _Climate(hourly.speeds[selected], hourly.sectors[selected], len(hourly.field_directions))
            seasonal[season] = _classify(criterion.comfort, {
                rule.speed: _governing(climate, ratios, rule.speed, invalid) for rule in criterion.comfort.rules
            }, invalid)
        comfort = np.maximum.reduce(list(seasonal.values()))
        period = "worst season"
    else:
        comfort = _classify(criterion.comfort, fractions, invalid)
        period = "all hours"
        if criterion.seasonal_comfort:
            warnings.append(f"Comfort uses all hours; {criterion.name} reports the worst season "
                            "and summer separately. Pass times for seasonal comfort.")
    if height is not None and not np.isclose(height, criterion.height):
        warnings.append(f"Fields are at {height:g} m; {criterion.name} is evaluated at {criterion.height:g} m.")

    metadata = dict(
        criterion=criterion.name, evaluation_height=criterion.height, field_height=height,
        speed_measure=("mean and GEM" if gem_fields is not None else "mean"), comfort_period=period,
        safety_period="all hours", hours=annual.hours, missing_hours=hourly.missing, calm_hours=hourly.calm,
        hours_per_direction=annual.counts, field_directions=hourly.field_directions.tolist(),
        direction_assignment="nearest field direction; ties to the earlier field",
    )
    if gem_metadata is not None:
        metadata["gem"] = provenance
    if run_metadata is not None:
        metadata["runs"] = deepcopy(dict(run_metadata))
    return ComfortResult(criterion, comfort, safety, fractions, seasonal, tuple(warnings), metadata)


def assess_results(results, speeds, directions, criterion=NEN8100, *, height=None,
                   method="linear", peak_factor=None, gust_ratio=1.85, times=None):
    """Assess matching wind results using declared references and owned samples.

    No exposure transfer is implicit. Mean-only criteria retain run provenance
    independently of GEM. Supplying a peak factor for a gust criterion enables
    algebraic screening GEM, preserving invalid stress-contributor masks.
    """
    if not isinstance(criterion, Criterion):
        raise ValueError("criterion must be a comfort.Criterion")
    height = criterion.height if height is None else _number(height, "height", nonnegative=True)
    fields, gems, angles, references, runs, actual = _prepare_results(
        results, height, method, criterion.gust_equivalent and peak_factor is not None,
        peak_factor, gust_ratio)
    gem_metadata = None if gems is None else dict(source="dtcc_qes / QES-Turb",
        model="algebraic mixing-length screening", peak_factor=peak_factor, gust_ratio=gust_ratio,
        peak_factor_basis="user-selected screening assumption; no QES calibration",
        mean_averaging_time="unspecified", gust_averaging_time="unspecified",
        limitations=["No independent validation for pedestrian gusts; factors are user assumptions"])
    return assess(speeds,directions,fields,angles,references,criterion,gem_fields=gems,
        gem_metadata=gem_metadata,run_metadata=runs,times=times,height=actual)


def _prepare_results(results, height, method, use_gem, peak_factor, gust_ratio):
    results = tuple(results)
    if not results:
        raise ValueError("results must be nonempty")
    if method not in ("linear", "nearest"):
        raise ValueError("method must be linear or nearest")
    fields, gems, angles, references, records = [], [], [], [], []
    common = None
    actual = height
    for result in results:
        reference = (result.metadata.get("profile") or {}).get("reference")
        if reference is None or result.reference_speed is None or result.reference_speed <= 0 or result.reference_direction is None:
            raise ValueError("Comfort requires a non-calm declared profile reference")
        direction = result.reference_direction % 360.
        if any(np.isclose((direction-d+180.) % 360.-180.,0.,rtol=0,atol=1e-10) for d in angles):
            raise ValueError("Result directions must be distinct modulo 360")
        profile = result.metadata["profile"]
        roughness = profile["requested"]["roughness_length"]
        sample = result.sample(height,method=method)
        if sample.method != method or sample.requested_height != height:
            raise ValueError("Sample method and requested height must match the request")
        for axis in ("x", "y"):
            if not np.array_equal(getattr(sample,axis),getattr(result,axis)):
                raise ValueError("Sample coordinates must match result coordinates")
        if sample.origin != result.origin or sample.crs != result.crs:
            raise ValueError("Sample frame must match result origin and crs")
        if method == "linear" and sample.sampled_height is not None and sample.sampled_height != height:
            raise ValueError("Linear sample must use the requested height")
        if sample.sampled_height is None and (np.any(sample.valid) or np.any(np.isfinite(sample.velocity))):
            raise ValueError("Unavailable sample support must retain NaN fields and invalid masks")
        if method == "nearest" and sample.sampled_height is None:
            raise ValueError("Nearest samples require an actual sampled height")
        signature = (tuple(result.origin), result.crs, reference["height"], roughness)
        if common is None:
            common = (signature,np.array(sample.x,copy=True),np.array(sample.y,copy=True),sample.speed.shape)
            if method == "nearest":
                actual = sample.sampled_height
        elif signature != common[0] or not np.array_equal(sample.x,common[1]) or not np.array_equal(sample.y,common[2]) or sample.speed.shape != common[3]:
            raise ValueError("Results must share coordinates, origin, crs, reference height and roughness")
        if method == "nearest" and sample.sampled_height != actual:
            raise ValueError("Nearest samples must share the same actual sampled height")
        fields.append(np.array(sample.speed,dtype=np.float64,copy=True))
        if use_gem:
            if result.turbulence is None:
                raise ValueError("GEM requires turbulence in every result")
            gems.append(gust_equivalent_mean(fields[-1],sample.streamwise_std,
                peak_factor=peak_factor,gust_ratio=gust_ratio))
        angles.append(direction)
        references.append(result.reference_speed)
        contributors = getattr(sample,"_stress_contributors_valid",None)
        records.append(dict(direction=direction,reference=deepcopy(reference),roughness_length=roughness,
            qualification=result.qualification,caveats=deepcopy(profile.get("caveats",[])),
            turbulence=deepcopy(result.metadata.get("turbulence")),
            sampling=dict(method=method,requested_height=height,sampled_height=sample.sampled_height,
                cells=int(sample.valid.size),valid_cells=int(sample.valid.sum()),
                valid_stress_contributors=None if contributors is None else int(contributors.sum()))))
    runs = dict(directions=records,sampling=dict(method=method,requested_height=height,field_height=actual))
    return np.stack(fields),np.stack(gems) if use_gem else None,angles,references,runs,actual


def exceedance(speeds, directions, fields, field_directions, reference_speed, threshold):
    """Fraction of valid hours with pedestrian speed above ``threshold`` m/s; NaN where invalid."""
    threshold = _number(threshold, "threshold", nonnegative=True)
    hourly = _Hourly(speeds, directions, field_directions)
    ratios = _ratios(fields, hourly.field_directions, reference_speed)
    climate = _Climate(hourly.speeds, hourly.sectors, len(hourly.field_directions))
    return _governing(climate, [ratios], threshold, np.isnan(ratios).any(axis=0))


def speed_at_exceedance(speeds, directions, fields, field_directions, reference_speed, fraction, *,
                        tolerance=0.01):
    """Smallest pedestrian speed exceeded for at most ``fraction`` of valid hours.

    Uses bisection over the total exceedance of all directions; results lie
    within ``tolerance`` m/s above the exact value. NaN where invalid.
    """
    fraction, tolerance = _number(fraction, "fraction", nonnegative=True), _number(tolerance, "tolerance", positive=True)
    if not 0 < fraction < 1 or tolerance <= 0:
        raise ValueError("fraction must be within (0, 1) and tolerance positive")
    hourly = _Hourly(speeds, directions, field_directions)
    ratios = _ratios(fields, hourly.field_directions, reference_speed)
    climate = _Climate(hourly.speeds, hourly.sectors, len(hourly.field_directions))
    invalid = np.isnan(ratios).any(axis=0)
    top = np.zeros(ratios.shape[1:])
    for k, table in zip(ratios, climate.tables):
        if len(table[0]):
            top = np.fmax(top, k * table[0][-1])
    low, high = np.zeros_like(top), top
    steps = int(np.ceil(np.log2(max(float(top.max(initial=0)), tolerance) / tolerance)))
    for _ in range(min(200, max(1, steps))):
        middle = 0.5 * (low + high)
        within = climate.fraction(ratios, middle) <= fraction
        low, high = np.where(within, low, middle), np.where(within, middle, high)
    return np.where(invalid, np.nan, high)


def log_law_transfer(speeds, from_height, from_roughness, to_height, to_roughness, blending_height=60.0,
                     *, from_law="standard", to_law="shifted"):
    """Transfer hourly speeds between heights and roughness lengths (metres).

    Neutral logarithmic profiles without displacement height, matched at a
    blending height where speed is taken as independent of surface roughness.
    """
    values = {name: _number(value, name, nonnegative=True) for name, value in dict(
        from_height=from_height, from_roughness=from_roughness, to_height=to_height,
        to_roughness=to_roughness, blending_height=blending_height).items()}
    if any(value <= 0 for value in values.values()):
        raise ValueError("Heights and roughness lengths must be positive")
    terms=[]
    for side, law in (("from",from_law),("to",to_law)):
        if law not in ("standard","shifted"):
            raise ValueError("from_law and to_law must be standard or shifted")
        z,z0,hb=values[side+"_height"],values[side+"_roughness"],values["blending_height"]
        if law=="standard":
            if min(z,hb)<=z0:
                raise ValueError("Heights must exceed the corresponding roughness lengths for standard laws")
            terms.append((np.log(z)-np.log(z0),np.log(hb)-np.log(z0)))
        else:
            terms.append((shifted_log(z,z0),shifted_log(hb,z0)))
    factor = terms[0][1]/terms[0][0]*terms[1][0]/terms[1][1]
    return np.asarray(speeds, dtype=np.float64) * factor


class _Hourly:
    """Validated hours with finite speeds, assigned to the nearest field direction."""

    def __init__(self, speeds, directions, field_directions, times=None):
        speeds = np.asarray(speeds, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        if speeds.ndim != 1 or directions.shape != speeds.shape or len(speeds) == 0:
            raise ValueError("speeds and directions must be one-dimensional arrays of equal, nonzero length")
        if np.any(speeds < 0):
            raise ValueError("Hourly speeds must be nonnegative")
        field_directions = np.asarray(field_directions, dtype=np.float64)
        if field_directions.ndim != 1 or len(field_directions) == 0 or not np.isfinite(field_directions).all():
            raise ValueError("field_directions must be a nonempty one-dimensional array of finite degrees")
        self.field_directions = np.mod(field_directions, 360.0)
        if len(np.unique(self.field_directions)) != len(self.field_directions):
            raise ValueError("field_directions must be distinct modulo 360 degrees")
        calm = speeds == 0
        valid = np.isfinite(speeds) & (np.isfinite(directions) | calm)
        self.missing, self.calm = int((~valid).sum()), int((valid & calm).sum())
        if not valid.any():
            raise ValueError("No valid hours: every hour lacks a finite speed or direction")
        self.speeds = speeds[valid]
        self.sectors = _nearest_direction(np.where(np.isfinite(directions), directions, 0.0)[valid],
                                          self.field_directions)
        self.months = None
        if times is not None:
            times = np.asarray(times)
            if times.shape != speeds.shape or times.dtype.kind != "M" or np.isnat(times).any():
                raise ValueError("times must be a datetime64 array without NaT, matching speeds")
            self.months = (times.astype("datetime64[M]").astype(np.int64) % 12 + 1)[valid]


class _Climate:
    """Per-direction distinct speeds with the number of hours at or above each."""

    def __init__(self, speeds, sectors, count):
        self.hours = len(speeds)
        self.counts, self.tables = [], []
        for d in range(count):
            values, repeats = np.unique(speeds[sectors == d], return_counts=True)
            self.counts.append(int(repeats.sum()))
            self.tables.append((values, np.r_[np.cumsum(repeats[::-1])[::-1], 0]))

    def fraction(self, ratios, threshold):
        """Fraction of hours above ``threshold`` (scalar or per cell); invalid cells are arbitrary."""
        above = np.zeros(np.broadcast_shapes(ratios.shape[1:], np.shape(threshold)), dtype=np.int64)
        with np.errstate(divide="ignore", invalid="ignore"):
            for k, (values, tail) in zip(ratios, self.tables):
                if len(values):
                    # K = 0 gives inf (or NaN at zero threshold); both sort past every speed.
                    above += tail[np.searchsorted(values, threshold / k, side="right")]
        return above / self.hours


def _governing(climate, ratios, threshold, invalid):
    fraction = np.max([climate.fraction(k, threshold) for k in ratios], axis=0)
    return np.where(invalid, np.nan, fraction)


def _classify(rating, fractions, invalid):
    shape = invalid.shape
    classes = np.full(shape, len(rating.rules), dtype=np.int8)
    for index in reversed(range(len(rating.rules))):
        rule = rating.rules[index]
        fraction = fractions[rule.speed]
        classes[(fraction <= rule.fraction) if rule.inclusive else (fraction < rule.fraction)] = index
    classes[invalid] = -1
    return classes


def _ratios(fields, field_directions, reference_speed):
    try:
        fields = np.asarray(fields, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("fields must be a numeric (D, N, M) array or a sequence of equal-shape arrays") from error
    if fields.ndim < 2 or len(fields) != len(field_directions):
        raise ValueError("fields must be (D, ...) with one field per field direction")
    if np.isinf(fields).any() or np.any(fields < 0):
        raise ValueError("Field speeds must be nonnegative, finite or NaN")
    reference = np.asarray(reference_speed, dtype=np.float64)
    if reference.ndim > 1 or reference.size not in (1, len(fields)):
        raise ValueError("reference_speed must be a scalar or one value per field direction")
    if not np.isfinite(reference).all() or np.any(reference <= 0):
        raise ValueError("reference_speed must be positive and finite")
    return fields / reference.reshape((-1,) + (1,) * (fields.ndim - 1))


def _nearest_direction(directions, field_directions):
    best = np.full(len(directions), np.inf)
    sectors = np.zeros(len(directions), dtype=np.intp)
    for index, direction in enumerate(field_directions):
        distance = np.abs(np.mod(directions - direction + 180.0, 360.0) - 180.0)
        closer = distance < best
        best[closer], sectors[closer] = distance[closer], index
    return sectors
