"""Automatic historical-climate pedestrian wind comfort screening."""

from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Literal

import numpy as np
from pydantic import ConfigDict, Field as Argument, model_validator
from dtcc_core.common import get_python_logger
from dtcc_core.datasets import DatasetBaseArgs, DatasetDescriptor
from dtcc_core.model import Bounds, Field, FieldSlice, Transform

from . import __version__, comfort, wind
from ._comfort_weather import EXPOSURES, fetch_climate, resolve_period
from ._dataset_city import prepare_city
from ._footprints import plan_footprint_domain
from .datasets import QESWindArgs, QESWindDataset, _fetch_city
from .turbulence import NUMERICS_VERSION

POLICY_VERSION = "comfort-screening-v1"
DIRECTIONS = tuple(np.arange(0., 360., 22.5))
REFERENCE_SPEED = 5.0
CRITERIA = {"nen8100": comfort.NEN8100, "city_of_london": comfort.CITY_OF_LONDON}


class QESWindComfortArgs(DatasetBaseArgs):
    """Assessment bounds in EPSG:3006; weather dates are half-open UTC."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    source: Literal["LM", "OSM"] = "LM"
    resolution: float = Argument(2.0, gt=0)
    max_cells: int = Argument(50_000_000, ge=1,
        description="Memory-capacity guard for the full buffered simulation domain; not an accuracy setting.")
    criterion: Literal["nen8100", "city_of_london"] = "nen8100"
    start: str | None = Argument(None, description="Inclusive UTC start; defaults to 12 calendar months before end.")
    end: str | None = Argument(None, description="Exclusive UTC end; defaults to first of the previous month.")
    years: tuple[int, int] | None = Argument(None, description="Alternative inclusive calendar-year pair; conflicts with start/end.")
    weather_source: Literal["smhi", "open_meteo"] = Argument("smhi", description="SMHI observations or explicit ERA5 reanalysis selection; no fallback.")
    exposure: Literal["open", "suburban", "urban"] = "open"
    policy_version: str = POLICY_VERSION

    @model_validator(mode="after")
    def resolve_request(self):
        if not np.isfinite(self.bounds).all():
            raise ValueError("bounds must contain finite coordinates")
        if self.policy_version != POLICY_VERSION:
            raise ValueError("Comfort policy changed; recreate the request")
        self.start, self.end = resolve_period(self.start, self.end, self.years)
        # Store the resolved dates once: context and reproducible requests cannot
        # change identity when the current month changes during execution.
        self.years = None
        wind._validate_grid(self.resolution, None, 20., 20., self.max_cells)
        return self


class QESWindComfortDataset(DatasetDescriptor):
    name = "qes_wind_comfort"
    title = "QES Pedestrian Wind Comfort"
    description = "Historic wind climate and directional QES screening for NEN 8100 or City of London Lawson (2019)."
    ArgsModel = QESWindComfortArgs
    data_category = "simulation"
    result_kind = "field_slice"
    python_return_type = "dtcc_core.model.FieldSlice"
    source_service = "dtcc-qes"
    default_crs = "EPSG:3006"
    generated_by = {"package": "dtcc-qes", "version": __version__, "license": "GPL-3.0-only"}
    source = [{"name": "dtcc_core.datasets.city", "role": "geometry and heights"},
              {"name": "dtcc_core.datasets.weather_history", "role": "historic wind climate"}]
    license = "Input data terms are inherited from the city and historical weather sources."
    processing_steps = ["Validate paired historical wind observations and coverage",
        "Prepare buffered flat-ground geometry and explicit pedestrian layers once",
        "Solve all 16 meteorological directions; retain pedestrian planes",
        "Transfer climate references and assess comfort, safety and seasonal suitability"]
    presentation_limitations = [
        "QES screening; model accuracy and planning compliance remain unqualified.",
        "Exposure and unknown 10 m measurement height are recorded assumptions.",
        "16 sectors, grid and domain buffer are provisional; assess local sensitivity.",
        "QES-Turb gusts use constant peak factor 3.0 and are unvalidated."]

    __call__ = QESWindDataset.__call__
    validate = QESWindDataset.validate

    def describe(self):
        metadata = super().describe()
        metadata["field_names"] = ["comfort", "safety", "valid", "exceedance_*",
                                   "sitting", "strolling", "traversing", "comfort_<season>"]
        metadata["products"] = [dict(name="slice", python_return_type=self.python_return_type,
                                      formats=[], categorical=True)]
        return metadata

    def build(self, args):
        started = time.perf_counter()
        xy = list(args.bounds) if len(args.bounds) == 4 else [args.bounds[i] for i in (0, 1, 3, 4)]
        climate = fetch_climate(args, xy)  # Fail before city fetch / expensive solves.
        weather_seconds = time.perf_counter() - started
        criterion = CRITERIA[args.criterion]
        source, fetch_bounds, buffer = _buffered_city(args, xy)
        preparation_started = time.perf_counter()
        preparation_args = QESWindArgs(bounds=fetch_bounds, source=args.source,
                                      resolution=args.resolution, horizontal_padding=20., max_cells=args.max_cells)
        footprints, bounds, preparation = prepare_city(source, preparation_args)
        maximum_height = max((cell.height for cell in footprints.cells), default=0.)
        ground = bounds[2]
        top = max(40., 3 * maximum_height + 20.)
        if len(args.bounds) == 6:
            top = args.bounds[5] - ground
            if top < max(criterion.height + 2., maximum_height + 2 * args.resolution):
                raise ValueError("3D comfort bounds need clearance above buildings and pedestrian height")
        vertical = _vertical_grid(criterion.height, args.resolution, top)
        profile = wind.LogProfile(REFERENCE_SPEED, 0., roughness_length=EXPOSURES[args.exposure])
        grid = wind._validate_grid(args.resolution, (*bounds[:5], ground + top),
                                   20., 20., args.max_cells, vertical_grid=vertical)
        turbulence = wind.Turbulence() if criterion.gust_equivalent else None
        geometry, domain = plan_footprint_domain(footprints,
            reference_height=profile.reference_height, roughness_length=profile.roughness_length,
            **grid, terrain=ground, turbulence=turbulence is not None)
        wind._prepare_profile(domain, profile)
        solver = wind.Solver()
        city_seconds = time.perf_counter() - preparation_started
        fields, gems, runs = [], [], []
        solver_warnings = []
        points, crop, domain_bounds = None, None, None
        logger = get_python_logger("dtcc-qes")
        with wind._prepared_model(geometry, domain, profile, solver, vertical, turbulence,
                                  "allow_estimated", preparation_started, city_seconds) as model:
            setup_timings = model.preparation_timings
            for index, direction in enumerate(DIRECTIONS):
                logger.info("Wind comfort direction %d/%d: %g degrees", index+1, len(DIRECTIONS), direction)
                solved = model.run(profile.with_direction(float(direction)))
                if not solved.diagnostics.converged:
                    solver_warnings.append(
                        f"Wind comfort direction {direction:g} degrees did not converge after "
                        f"{solved.diagnostics.iterations} iterations; using the available field.")
                sample = solved.sample(criterion.height, method="nearest")
                if sample.sampled_height is None or not np.isclose(sample.sampled_height, criterion.height, atol=1e-6):
                    raise ValueError("Explicit comfort grid did not sample the criterion height")
                xx, yy = np.meshgrid(solved.x.astype(float) + solved.origin[0],
                                     solved.y.astype(float) + solved.origin[1])
                current = np.column_stack([xx.ravel(), yy.ravel(),
                                           np.full(xx.size, ground + criterion.height)])
                if points is None:
                    crop = ((current[:, 0] >= xy[0]) & (current[:, 0] < xy[2]) &
                            (current[:, 1] >= xy[1]) & (current[:, 1] < xy[3]))
                    if not crop.any():
                        raise ValueError("Assessment bounds contain no solver cell centres; reduce resolution")
                    points = current[crop]
                    domain_bounds = list(solved.metadata["domain"]["effective_bounds"])
                    preparation["footprints"] = deepcopy(solved.metadata["footprints"])
                    preparation["versions"] = deepcopy(solved.metadata["versions"])
                elif not np.array_equal(points, current[crop]):
                    raise ValueError("Directional pedestrian coordinates changed")
                speeds = sample.speed.ravel()[crop].copy()
                speeds[~sample.valid.ravel()[crop]] = np.nan
                fields.append(speeds)
                if turbulence is not None:
                    std = sample.streamwise_std.ravel()[crop].copy()
                    std[~sample.stress_valid.ravel()[crop]] = np.nan
                    gems.append(comfort.gust_equivalent_mean(speeds, std,
                                peak_factor=comfort.SCREENING_PEAK_FACTOR))
                runs.append(dict(direction=float(direction), reference=deepcopy(solved.metadata["profile"]["reference"]),
                    requested_height=criterion.height, sampled_height=sample.sampled_height,
                    diagnostics=asdict(solved.diagnostics), qualification=solved.qualification,
                    solver=deepcopy(solved.solver), timings=deepcopy(solved.metadata["timings"])))
                # Keep planes only. In particular, neither sample nor solved
                # survives into the following solve's volume allocation.
                del sample, solved
        gem_metadata = None if not gems else dict(source="QES-Turb", model="algebraic screening",
            numerics_version=NUMERICS_VERSION,
            peak_factor=comfort.SCREENING_PEAK_FACTOR, gust_ratio=1.85,
            mean_averaging_time="unspecified", gust_averaging_time="unspecified",
            validity_policy="all directions require fluid finite mean and valid stress",
            limitations="Unvalidated pedestrian gust screening; constant peak factor, no QES calibration")
        assessment = comfort.assess(climate.speeds, climate.directions, np.stack(fields), DIRECTIONS,
            REFERENCE_SPEED, criterion, times=climate.times, height=criterion.height,
            gem_fields=np.stack(gems) if gems else None, gem_metadata=gem_metadata,
            run_metadata={"directions": runs})
        result = _product(points, xy, ground, args, assessment)
        context = self.create_context(args)
        context.provenance.generated_at = datetime.now(UTC).isoformat()
        for upstream in (source.dataset_context, climate.context):
            if upstream is not None:
                context.provenance.derived_from.append(upstream.model_dump(mode="json"))
        context.provenance.processing_steps.append(dict(operation=self.name, policy=POLICY_VERSION,
            weather=climate.metadata, preparation=preparation,
            domain=dict(fetch_bounds=fetch_bounds, buffer_m=buffer, simulation_bounds=domain_bounds,
                        assessment_bounds=xy, vertical_faces=list(vertical.faces), max_cells=args.max_cells),
            directions=runs, assessment=_plain(assessment.metadata),
            timings=dict(weather_seconds=weather_seconds, preparation=setup_timings,
                         total_seconds=time.perf_counter()-started)))
        context.warnings.extend(climate.warnings + solver_warnings + list(assessment.warnings) + self.presentation_limitations)
        context.warnings = list(dict.fromkeys(context.warnings))
        valid = result.field("valid").values.astype(bool)
        context.health = dict(valid_samples=int(valid.sum()), invalid_samples=int((~valid).sum()),
                              weather_coverage=climate.metadata["coverage"], required_directions=len(DIRECTIONS),
                              completed_directions=len(runs), screening_only=True,
                              solver_converged=all(run["diagnostics"]["converged"] for run in runs))
        result.metadata_payload["weather"] = climate.metadata
        result.dataset_context = context
        return result


def _buffered_city(args, xy):
    """Fetch preliminary geometry, then enough surroundings for five roof heights.

    This provisional isotropic policy is recorded, not an accuracy qualification.
    Buildings discovered at the edge can enlarge the buffer; never silently stop
    before the height policy stabilises.
    """
    buffer = max(40., 10 * args.resolution)
    for _ in range(4):
        bounds = [xy[0]-buffer, xy[1]-buffer, xy[2]+buffer, xy[3]+buffer]
        source = _fetch_city(bounds, args.source, args.strict_live)
        heights = [b.measured_height or b.estimated_height for b in source.buildings]
        maximum = max((h for h in heights if h is not None and np.isfinite(h)), default=0.)
        # Quantise upward: lidar-derived heights can change slightly with the
        # fetched terrain extent. Millimetre changes must not trigger a new city
        # fetch on every pass, while the five-height requirement still holds.
        needed = float(20 * np.ceil(max(40., 10 * args.resolution, 5 * maximum) / 20))
        if needed <= buffer:
            if len(args.bounds) == 6:
                bounds = [bounds[0], bounds[1], args.bounds[2], bounds[2], bounds[3], args.bounds[5]]
            return source, bounds, buffer
        buffer = needed
    raise ValueError("Comfort geometry buffer did not stabilise after four city fetches")


def _vertical_grid(height, spacing, top):
    # A dedicated 0.5 m layer has its centre exactly on either criterion height.
    # Lower layers are <= 1 m; above the pedestrian plane cells grow by <= 15%.
    lower = height - .25
    faces = list(np.linspace(0., lower, int(np.ceil(lower / min(spacing, 1.))) + 1))
    faces.append(height + .25)
    thickness = .5
    while faces[-1] < top:
        thickness = min(thickness * 1.15, max(spacing, .5))
        if top - faces[-1] <= 1.5 * thickness:
            faces.append(top)
        else:
            faces.append(faces[-1] + thickness)
    return wind.VerticalGrid.from_faces(faces)


def _product(points, xy, ground, args, assessment):
    criterion = assessment.criterion
    legends = {"comfort": list(criterion.comfort.labels), "safety": list(criterion.safety.labels)}
    obj = ComfortFieldSlice(name="qes_wind_comfort", points=points, slice_axis="z", axes=(0, 1),
        crs="EPSG:3006", transform=Transform(srs="EPSG:3006"),
        domain_bounds=Bounds(xmin=xy[0], ymin=xy[1], xmax=xy[2], ymax=xy[3],
                             zmin=ground, zmax=ground+criterion.height),
        metadata_payload=dict(dataset="qes_wind_comfort", policy=POLICY_VERSION,
            criterion=criterion.name, requested_height=criterion.height, sampled_height=criterion.height,
            sampling="solver cell centres; no categorical interpolation", solver_resolution=args.resolution,
            legends=legends, unassessed_class=-1, assessment=_plain(assessment.metadata)))
    values = {"comfort": assessment.comfort, "safety": assessment.safety,
              "valid": (assessment.comfort >= 0).astype(np.uint8)}
    for threshold, fractions in assessment.exceedance.items():
        values[f"exceedance_{threshold:g}"] = fractions
    for name, classes in assessment.seasonal.items():
        values[f"comfort_{name}"] = classes
        legends[f"comfort_{name}"] = list(criterion.comfort.labels)
    for name, _ in criterion.activities:
        values[name] = assessment.activity(name)
        legends[name] = list(criterion.activity_labels)
    for name, data in values.items():
        obj.add_field(Field(name=name, values=np.asarray(data), dim=1, unit="1", association="sample"))
    return obj


def _plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


class ComfortFieldSlice(FieldSlice):
    """FieldSlice with discrete class legends and a climate wind rose."""

    def to_plot_product(self, field_name="comfort"):
        return super().to_plot_product(field_name=field_name)

    def write_artifact(self, path, format=None):
        fmt = (format or self.default_artifact_format).lower().lstrip(".")
        if fmt != "png":
            return super().write_artifact(path, format=fmt)
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        figure = Figure(figsize=(10, 8), layout="constrained")
        FigureCanvasAgg(figure)
        self.plot(ax=figure.subplots(), show=False)
        figure.savefig(Path(path), format="png", dpi=150)

    def plot(self, ax=None, show=True, *, field_name="comfort", presentation=True, **kwargs):
        import matplotlib.pyplot as plt
        from matplotlib.colors import BoundaryNorm, ListedColormap
        from matplotlib.patches import Patch

        field = self.field(field_name)
        if field is None:
            raise ValueError(f"No field named {field_name!r}")
        if ax is None:
            _, ax = plt.subplots(layout="constrained")
        values = np.asarray(field.values).ravel()
        labels = self.metadata_payload["legends"].get(field_name)
        spacing = self.metadata_payload["solver_resolution"]
        from matplotlib.collections import PolyCollection
        half = spacing / 2
        offsets = np.array([[-half, -half], [half, -half], [half, half], [-half, half]])
        vertices = self.points[:, None, :2] + offsets
        if labels:
            colours = ["#3288bd", "#abdda4", "#ffffbf", "#fdae61", "#d53e4f"]
            if len(labels) == 2:
                colours = ["#abdda4", "#d53e4f"]
            elif len(labels) == 3:
                colours = ["#abdda4", "#fdae61", "#d53e4f"]
            colours = colours[:len(labels)]
            cmap = ListedColormap(["#bdbdbd", *colours])
            norm = BoundaryNorm(np.arange(-1.5, len(labels)+.5), cmap.N)
            artist = PolyCollection(vertices, array=values.astype(float), cmap=cmap, norm=norm, **kwargs)
            ax.legend(handles=[Patch(color="#bdbdbd", label="unassessed"),
                       *(Patch(color=c, label=label) for c, label in zip(colours, labels))],
                      loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
        else:
            artist = PolyCollection(vertices, array=np.ma.masked_invalid(values), **kwargs)
            ax.figure.colorbar(artist, ax=ax, label=field_name)
        ax.add_collection(artist)
        ax.set_xlim(self.domain_bounds.xmin, self.domain_bounds.xmax)
        ax.set_ylim(self.domain_bounds.ymin, self.domain_bounds.ymax)
        ax.set_aspect("equal")
        ax.set_xlabel("Easting (EPSG:3006)")
        ax.set_ylabel("Northing (EPSG:3006)")
        title = self.metadata_payload["criterion"] + " — " + field_name
        if presentation and "weather" in self.metadata_payload:
            weather = self.metadata_payload["weather"]
            title += f"\n{weather['start'][:10]} to {weather['end_exclusive'][:10]} (exclusive), {weather['coverage']:.3%} coverage"
        ax.set_title(title)
        if show:
            plt.show()
        return ax

    def plot_wind_rose(self, ax=None, show=True):
        import matplotlib.pyplot as plt
        if ax is None:
            _, ax = plt.subplots(subplot_kw={"projection": "polar"})
        rose = self.metadata_payload["weather"]["wind_rose"]
        counts = np.asarray(rose["counts"], dtype=float)
        total = counts.sum() + rose["calm_hours"]
        ax.bar(np.deg2rad(rose["directions"]), counts / total * 100., width=np.deg2rad(22.5))
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_title(f"Wind FROM (% of valid hours); calm {rose['calm_hours']/total:.1%}")
        if show:
            plt.show()
        return ax


__all__ = ["QESWindComfortArgs", "QESWindComfortDataset"]
