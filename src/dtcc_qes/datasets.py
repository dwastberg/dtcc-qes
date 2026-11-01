"""Bounds-based QES datasets, including experimental automatic vertical grids."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import time
from typing import Annotated, Any, Literal, NotRequired, TypedDict

import numpy as np
from pydantic import ConfigDict, Field as Argument, model_validator, model_serializer

from dtcc_core import datasets as core_datasets
from dtcc_core.datasets import DatasetBaseArgs, DatasetDescriptor
from dtcc_core.model import Bounds, City, Field, FieldSlice, Transform

from . import __version__, wind
from ._dataset_city import prepare_city
from ._footprints import plan_footprint_domain
from .solver_control import Solver

__all__ = ["QESWindArgs", "QESWindDataset"]


class _ProfilePayload(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Annotated[int, Argument(strict=True, ge=2, le=2)]
    roughness_length: NotRequired[float]
    metadata: NotRequired[dict[str, Any] | None]


class _AnalyticPayload(_ProfilePayload):
    speed: float
    direction: float


class _LogPayload(_AnalyticPayload):
    kind: Literal["log"]
    reference_height: NotRequired[float]


class _UniformPayload(_AnalyticPayload):
    kind: Literal["uniform"]
    reference_height: NotRequired[float]


class _PowerPayload(_AnalyticPayload):
    kind: Literal["power_law"]
    reference_height: float
    exponent: float


class _MeasuredPayload(_ProfilePayload):
    kind: Literal["measured"]
    heights: list[float]
    reference_height: float
    speeds: NotRequired[list[float]]
    direction: NotRequired[float]
    directions: NotRequired[list[float]]
    u: NotRequired[list[float]]
    v: NotRequired[list[float]]
    below: NotRequired[Literal["error", "log"]]
    above: NotRequired[Literal["constant", "error"]]
    interpolation: NotRequired[Literal["log_height", "linear"]]


_ProfileRequest = Annotated[_LogPayload | _UniformPayload | _PowerPayload | _MeasuredPayload,
                            Argument(discriminator="kind")]


class _SolverPayload(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Annotated[int, Argument(strict=True, ge=1, le=1)]
    tolerance: NotRequired[float]
    max_iterations: NotRequired[int]
    precision: NotRequired[Literal["float32", "float64"]]
    max_solve_seconds: NotRequired[float | None]
    monitor: NotRequired[dict | None]
    policy: NotRequired[Literal["pedestrian-v1"] | None]
    checkpoint_interval: NotRequired[int]
    residual_interval: NotRequired[int]
    raise_on_failure: NotRequired[bool]


class QESWindArgs(DatasetBaseArgs):
    """A city selection in EPSG:3006 and one steady wind condition."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    profile: _ProfileRequest | None = Argument(None, description="Versioned horizontal profile: kind plus analytic parameters or measured arrays and tails.")
    source: Literal["LM", "OSM"] = "LM"
    smallest_building_size: float = Argument(15.0, ge=0, description="Source area filter in square metres.")
    min_building_detail: float = Argument(0.5, gt=0, description="Core footprint cleaning/merging scale in metres.")
    speed: float = Argument(5.0, ge=0, description="Log-profile speed in m/s at the default 10 m reference; use profile for other references.")
    direction: float = Argument(270.0, ge=0, lt=360, description="Meteorological direction FROM, clockwise from north.")
    resolution: float = Argument(2.0, gt=0, description="Horizontal cell spacing in metres; also vertical spacing in uniform mode.")
    vertical_grid: Literal["uniform", "auto"] = Argument(
        "uniform", description="Uniform cells or experimental automatic vertical layers; auto requires a slice product.")
    pedestrian_height: float = Argument(1.5, gt=0, description="Automatic-grid pedestrian target in metres above flat ground.")
    growth_rate: float = Argument(1.15, gt=1, le=1.20, description="Maximum adjacent-layer growth for the experimental automatic grid.")
    horizontal_padding: float = Argument(20.0, ge=0)
    vertical_clearance: float = Argument(20.0, ge=0)
    max_cells: int = Argument(200_000_000, ge=1)
    solver: _SolverPayload = Argument(default_factory=lambda: Solver(tolerance=1e-4, max_iterations=1000).to_dict(),
        description="Versioned Solver specification; dataset defaults remain 1e-4/1000 pending the shared-default study.")
    solver_policy_revision: str | None = Argument(None, description="Automatically bound native policy/arithmetic identity for cache provenance.")
    product: Literal["field", "slice"] = "field"
    slice_axis: Literal["x", "y", "z"] = "z"
    slice_sampling: Literal["nearest", "linear"] = Argument(
        "nearest", description="Linear interpolates vertically on z slices; display sampling remains nearest in x/y.")
    slice_position: float = Argument(0.5, ge=0, le=1, description="Relative position within the cell-centre extent.")
    slice_height: float | None = Argument(
        None, ge=0,
        description="Slice height in metres above flat ground; overrides slice_axis to 'z' and slice_position.",
    )
    slice_resolution: int = Argument(128, ge=2, le=1024, description="Samples per display axis, independent of solver spacing.")

    @model_validator(mode="after")
    def validate_solver_options(self):
        if not np.isfinite(self.bounds).all():
            raise ValueError("bounds must contain finite coordinates")
        if self.slice_height is not None:
            self.slice_axis = "z"
        if self.vertical_grid == "auto" and self.product == "field":
            raise ValueError("Automatic vertical grids require product='slice'; a uniform VolumeGrid cannot represent them")
        if self.slice_sampling == "linear" and (self.product != "slice" or self.slice_axis != "z"):
            raise ValueError("Linear slice_sampling requires product='slice' and slice_axis='z'")
        if self.product == "slice" and self.slice_height is not None and len(self.bounds) == 6:
            if self.slice_height > self.bounds[5] - self.bounds[2]:
                raise ValueError("slice_height must be within the simulation domain")
        # Reuse the solver's float32 and integer limits before fetching data.
        if self.profile is not None:
            profile = wind.profile_from_dict(self.profile)
            names = {"speed", "direction"}
            conflicts = self.model_fields_set & names
            if conflicts:
                raise ValueError(f"profile conflicts with explicit scalar condition fields: {sorted(conflicts)}")
            wind._resolve_condition(None, None, profile)
            object.__setattr__(self, "profile", profile.to_dict())
        else:
            profile = wind._resolve_condition(self.speed, self.direction, None)
        wind._validate_grid(self.resolution, None, self.horizontal_padding,
                            self.vertical_clearance, self.max_cells, vertical_grid=self.vertical_grid_spec())
        solver = Solver.from_dict(self.solver)
        self.solver = solver.to_dict()
        if solver.mode == "adaptive":
            actual_revision = wind._qes.solver_policy_revision
            if self.solver_policy_revision not in (None, actual_revision):
                raise ValueError("Solver policy implementation changed; re-create the request for this build")
            self.solver_policy_revision = actual_revision
        elif self.solver_policy_revision is not None:
            raise ValueError("solver_policy_revision requires adaptive solver")
        wind._check_solver_inputs(solver, profile, None)
        return self

    def vertical_grid_spec(self):
        if self.vertical_grid == "auto":
            return wind.VerticalGrid.auto(pedestrian_height=self.pedestrian_height, growth_rate=self.growth_rate)
        return None

    @model_serializer(mode="wrap")
    def serialize_request(self, handler):
        result = handler(self)
        if self.profile is not None:
            for name in ("speed", "direction"):
                result.pop(name, None)
        return result

    def reference_condition(self):
        return wind._resolve_condition(None if self.profile else self.speed,
            None if self.profile else self.direction, wind.profile_from_dict(self.profile) if self.profile else None).reference

    def wind_options(self):
        options = dict(speed=self.speed, direction=self.direction,
                    resolution=self.resolution, horizontal_padding=self.horizontal_padding,
                    vertical_clearance=self.vertical_clearance, max_cells=self.max_cells,
                    solver=Solver.from_dict(self.solver), vertical_grid=self.vertical_grid_spec())
        if self.profile is not None:
            for name in ("speed", "direction"):
                options.pop(name)
            options["profile"] = wind.profile_from_dict(self.profile)
        return options


class QESWindDataset(DatasetDescriptor):
    """Steady QES wind over a fetched, conditioned, flat-ground city."""

    name = "qes_wind"
    title = "QES Urban Wind"
    description = "Steady background wind over conditioned building footprints on flat ground using QES-Winds."
    ArgsModel = QESWindArgs
    data_category = "simulation"
    result_kind = "vector_field"
    python_return_type = "dtcc_core.model.VolumeGrid"
    source_service = "dtcc-qes"
    default_crs = "EPSG:3006"
    generated_by = {"package": "dtcc-qes", "version": __version__, "license": "GPL-3.0-only"}
    source = [{"name": "dtcc_core.datasets.city", "role": "upstream geometry and heights"}]
    license = "Input data terms are inherited from the selected city sources."
    processing_steps = [
        "Fetch a LOD1 city with LOD0 footprints and estimated heights",
        "Fill source/region courtyards and clean once into height-preserving cells",
        "Plan canonical solids and apply exposure-aware building parameterizations",
        "Flatten terrain and solve one steady QES wind condition",
    ]
    presentation_limitations = [
        "Flat ground and stair-step cells; source/region courtyards are filled, partition holes preserve towers.",
        "Convergence measures multiplier change, not a mass-conservation residual.",
        "Automatic vertical grids are experimental; no automatic comfort-analysis preset is qualified.",
    ]

    def describe(self):
        metadata = super().describe()
        metadata["products"] = [
            {"name": "field", "python_return_type": "dtcc_core.model.VolumeGrid", "formats": [],
             "vertical_grids": ["uniform"], "field_names": ["velocity", "speed", "cell_flags"],
             "profile_field_names": ["velocity", "speed", "speedup", "cell_flags"]},
            {"name": "slice", "python_return_type": "dtcc_core.model.FieldSlice", "formats": [],
             "vertical_grids": ["uniform", "auto"], "experimental_vertical_grids": ["auto"],
             "field_names": ["velocity", "speed", "speedup", "cell_flags", "valid"]},
        ]
        metadata["field_names"] = ["velocity", "speed", "speedup", "cell_flags", "valid"]
        return metadata

    def __call__(self, **kwargs):
        # build attaches realization-specific context; the base implementation
        # would replace it with descriptor-only context after the solve.
        return self.build(self.validate(kwargs))

    def validate(self, kwargs):
        values = dict(kwargs)
        bounds = values.get("bounds")
        if isinstance(bounds, Bounds):
            names = (("xmin", "ymin", "xmax", "ymax") if bounds.zmin == bounds.zmax == 0
                     else ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax"))
            values["bounds"] = [getattr(bounds, name) for name in names]
        return self.ArgsModel(**values)

    def build(self, args: QESWindArgs):
        options = args.wind_options()
        profile = wind._resolve_condition(options.get("speed"), options.get("direction"), options.get("profile"))
        solver = options["solver"]
        exclusions = wind._check_solver_inputs(solver, profile, None)
        if exclusions:
            wind._warn_solver_outcome(str(wind.UnacceptedResultError(None, None, exclusions=exclusions)), None)
        xy = list(args.bounds) if len(args.bounds) == 4 else [args.bounds[i] for i in (0, 1, 3, 4)]
        source_city = core_datasets.city(
            bounds=xy, source=args.source, smallest_building_size=args.smallest_building_size,
            lod="lod1", strict_live=args.strict_live,
        )
        if not isinstance(source_city, City):
            raise TypeError("The city dataset must return a dtcc_core.model.City")
        upstream = source_city.dataset_context
        if upstream is not None and upstream.health and upstream.health.get("partial_result"):
            raise ValueError("QES wind requires a complete city; the upstream dataset returned a partial result")
        preparation_started = time.perf_counter()
        footprints, bounds, preparation = prepare_city(source_city, args)
        vertical_grid = args.vertical_grid_spec()
        grid = wind._validate_grid(args.resolution, bounds, args.horizontal_padding,
                                   args.vertical_clearance, args.max_cells, vertical_grid=vertical_grid)
        geometry, domain = plan_footprint_domain(footprints,
            reference_height=profile.reference_height, roughness_length=profile.roughness_length,
            **grid, terrain=bounds[2])
        wind._prepare_profile(domain, profile)
        preparation_seconds = time.perf_counter()-preparation_started
        solved = wind._solve_prepared(geometry, domain, profile, solver,
            vertical_grid=vertical_grid, height_policy="allow_estimated",
            _known_exclusions=exclusions)
        solved.metadata["timings"]["city_preparation_seconds"] = preparation_seconds
        preparation["footprints"] = deepcopy(solved.metadata["footprints"])
        preparation["dtcc_core"] = deepcopy(solved.metadata["versions"]["dtcc_core"])
        obj = solved.to_dtcc(include_speedup=args.profile is not None) if args.product == "field" else _field_slice(solved, args)
        context = self.create_context(args)
        context.metadata.python_return_type = f"dtcc_core.model.{type(obj).__name__}"
        context.provenance.generated_at = datetime.now(timezone.utc).isoformat()
        if upstream is not None:
            context.provenance.derived_from.append(upstream.model_dump(mode="json"))
            context.metadata.license = upstream.metadata.license
        step = {
            "operation": "qes_wind", "preparation": preparation,
            "simulation": solved.metadata, "diagnostics": asdict(solved.diagnostics),
            "qualification": solved.qualification,
        }
        if args.product == "slice":
            step["sampling"] = obj.metadata_payload.copy()
        context.provenance.processing_steps.append(step)
        context.health = asdict(solved.diagnostics)
        if solved.solver["record"] is not None:
            context.health["solver"] = deepcopy(solved.solver)
            context.health["execution_deterministic"] = False
            if solved.solver["record"]["mode"] == "adaptive":
                context.health["numerically_accepted"] = solved.solver["record"]["accepted"]
                context.health["numerical_assessment_scope"] = solved.solver["record"]["assessment_scope"]
                if solved.solver["record"]["accepted"]:
                    context.warnings.append("Numerical acceptance covers only the declared pedestrian ROI/receptors; full-volume and physical/model accuracy remain unassessed.")
                else:
                    context.warnings.append(f"QES pedestrian output is unaccepted: {solved.solver["record"]['assessment_reason']}.")
            else:
                context.warnings.append("Time-budgeted QES output records actual completed work; accuracy is not assessed.")
        context.health["automatic_grid_experimental"] = args.vertical_grid == "auto"
        counts = solved.metadata["footprints"]["counts"]
        context.health["footprint_fallbacks"] = counts["fallbacks"]
        context.health["excluded_sources"] = counts["excluded"]
        context.health["excluded_components"] = sum(
            status == "excluded" for source in solved.metadata["buildings"]
            for status in source["components"].values())
        if counts["fallbacks"]:
            context.warnings.append(
                f"{counts['fallbacks']} footprint blocks use tallest-height wall-partition fallbacks; "
                "inspect provenance and added volume.")
        if args.vertical_grid == "auto":
            context.warnings.append("Automatic vertical generation is experimental; local grid sensitivity "
                                    "remains unresolved and no comfort-analysis preset is qualified.")
        if args.product == "slice":
            valid = obj.field("valid").values
            context.health["valid_samples"] = int(np.count_nonzero(valid))
            context.health["invalid_samples"] = int(valid.size - np.count_nonzero(valid))
        if not solved.diagnostics.converged and (solved.solver["record"] is None or solved.solver["record"]["mode"] != "adaptive"):
            context.warnings.append("QES solver did not converge; inspect the recorded diagnostics.")
        obj.dataset_context = context
        return obj


def _nearest(axis, positions):
    """Nearest sample indices, choosing the lower index on ties."""
    right = np.clip(np.searchsorted(axis, positions), 0, len(axis) - 1)
    left = np.maximum(right - 1, 0)
    return np.where(np.abs(positions - axis[left]) <= np.abs(axis[right] - positions), left, right)


def _field_slice(result, args):
    # Widen coordinates before scalar arithmetic, as in WindResult.sample.
    axes = tuple(np.asarray(a, dtype=np.float64) for a in (result.x, result.y, result.z))
    normal = "xyz".index(args.slice_axis)
    plane_axes = tuple(i for i in range(3) if i != normal)
    target = axes[normal][0] + args.slice_position * (axes[normal][-1] - axes[normal][0])
    if args.slice_height is not None:
        domain_height = result.metadata["domain"]["effective_bounds"][5] - result.origin[2]
        if args.slice_height > domain_height:
            raise ValueError(f"slice_height must be within the simulation domain (0 to {domain_height:g} metres)")
        target = args.slice_height
    normal_index = int(_nearest(axes[normal], target))
    sample = result.sample(target, method=args.slice_sampling) if normal == 2 else None
    coordinate = target if args.slice_sampling == "linear" else float(axes[normal][normal_index])
    position = float((coordinate - axes[normal][0]) / (axes[normal][-1] - axes[normal][0])
                     if args.slice_height is not None or args.slice_sampling == "linear" else args.slice_position)
    samples = [np.linspace(axes[i][0], axes[i][-1], args.slice_resolution) for i in plane_axes]
    plane = np.stack(np.meshgrid(*samples, indexing="ij"), axis=-1).reshape(-1, 2)
    points = np.empty((len(plane), 3))
    points[:, plane_axes] = plane
    points[:, normal] = coordinate
    indices = [_nearest(axis, points[:, i]) for i, axis in enumerate(axes)]
    flags = result.cell_flags[indices[2], indices[1], indices[0]].copy()
    if sample is not None:
        velocity = sample.velocity[indices[1], indices[0]].copy()
        valid = sample.valid[indices[1], indices[0]].copy()
    else:
        velocity = result.velocity[indices[2], indices[1], indices[0]].astype(np.float64, copy=True)
        valid = (flags != 0) & (flags != 2) & np.isfinite(velocity).all(axis=-1)
        velocity[~valid] = np.nan
    speed = np.linalg.norm(velocity.astype(np.float64), axis=1)
    # Speed-up is undefined for calm inflow; keep NaN rather than divide by zero.
    reference_speed = result.reference_speed if args.profile is not None else args.speed
    speedup = speed / reference_speed if reference_speed > 0 else np.full_like(speed, np.nan)
    points += np.asarray(result.origin)
    physical_bounds = result.metadata["domain"]["effective_bounds"]
    field_slice = FieldSlice(
        name="qes_wind_slice", points=points, slice_axis=args.slice_axis,
        slice_position=position, resolution=args.slice_resolution, axes=plane_axes,
        crs=result.crs, transform=Transform(srs=result.crs or ""),
        domain_bounds=Bounds(**dict(zip(("xmin", "ymin", "zmin", "xmax", "ymax", "zmax"), physical_bounds))),
        metadata_payload={"dataset": "qes_wind",
                          "sampling": "vertical_linear_nearest_horizontal" if args.slice_sampling == "linear" else "nearest_cell",
                          "vertical_sampling": args.slice_sampling, "horizontal_sampling": "nearest_cell",
                          "slice_coordinate": float(points[0, normal]),
                          "slice_height": sample.sampled_height if sample is not None else None,
                          "requested_slice_height": args.slice_height,
                          "requested_height": float(target) if normal == 2 else None,
                          "sampled_height": sample.sampled_height if sample is not None else None,
                          "solid_cell_flags": [0, 2], "cell_flags_sampling": "nearest_cell_categorical",
                          "validity": "All contributing cells must be fluid with finite velocity; invalid vectors are NaN.",
                          "speedup_reference": {"speed": reference_speed, "height": args.reference_condition()["height"]},
                          "profile": result.metadata.get("profile"),
                          "qualification": result.qualification,
                          "vertical_grid": result.metadata["domain"].get("vertical_grid", {"mode": "uniform"}),
                          "solver_precision": result.diagnostics.precision,
                          "automatic_grid_experimental": args.vertical_grid == "auto"},
    )
    for name, values, dim, unit in (
        ("velocity", velocity, 3, "m/s"),
        ("speed", speed, 1, "m/s"),
        ("speedup", speedup, 1, "1"),
        ("cell_flags", flags, 1, "1"),
        ("valid", valid, 1, "1"),
    ):
        field_slice.add_field(Field(name=name, values=values, dim=dim, unit=unit, association="sample"))
    return field_slice
