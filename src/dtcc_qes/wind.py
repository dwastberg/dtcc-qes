"""Run canonical LOD0 DTCC buildings through the in-memory QES CPU solver."""

from importlib.metadata import distribution
import json
import math
from numbers import Integral
import numpy as np

from dtcc_core.common import get_python_logger
from dtcc_core.model import Bounds

from . import __version__, _qes
from ._city import extract_city, number, prepare_domain
from .result import ConvergenceError, SolveDiagnostics, WindResult, WindSample
from .vertical_grid import GridPreview, VerticalGrid

__all__ = ["run", "preview_grid", "WindResult", "WindSample", "GridPreview",
           "SolveDiagnostics", "ConvergenceError", "VerticalGrid"]


def _dtcc_version():
    installed = distribution("dtcc-core")
    direct_url = installed.read_text("direct_url.json")
    details = json.loads(direct_url) if direct_url else {}
    return dict(version=installed.version, revision=details.get("vcs_info", {}).get("commit_id"))


def run(city, speed: float, direction: float, *, reference_height: float = 10.0,
        roughness_length: float = 0.1, resolution: float = 2.0, bounds=None,
        horizontal_padding: float = 20.0, vertical_clearance: float = 20.0,
        max_cells: int = 20_000_000, tolerance: float = 1e-5, max_iterations: int = 500,
        raise_on_nonconvergence: bool = False, terrain=None, height_policy="measured",
        vertical_grid: VerticalGrid | None = None, solver_precision: str = "float32") -> WindResult:
    """Solve one explicit wind condition without modifying the source city.

    Speed is in m/s. Direction is clockwise from north and denotes where the
    wind comes from. Reference height, roughness and cell resolution are metres.
    With ``vertical_grid=VerticalGrid.from_faces(...)``, resolution sets x/y
    spacing and the supplied faces set the vertical layers above flat ground.
    ``VerticalGrid.auto(...)`` generates a provisional geometry-based grid;
    its policy settings have not yet passed the C2 accuracy/cost study.
    Nonuniform results retain their coordinates and cannot be exported directly
    to DTCC's uniform VolumeGrid.
    Bounds are DTCC Bounds or (xmin, ymin, zmin, xmax, ymax, zmax); upper edges
    expand to whole cells horizontally. Automatic vertical grids fit the selected
    top before native coordinate rounding. Automatic bounds use at least three
    cells of padding.
    Non-convergence logs a warning and returns the available result unless
    raise_on_nonconvergence=True.

    ``solver_precision='float64'`` opts into double multiplier storage, RHS,
    updates and face corrections. Geometry, coefficients and returned velocities
    remain float32. Tolerance bounds follow the selected arithmetic precision;
    convergence still measures multiplier change, not a residual guarantee.

    The input uses one shared planar frame in metres (or an unlabelled local
    metre frame). Only single, hole-free LOD0 Surfaces are accepted; footprints
    may not overlap or touch, and building parts are unsupported. Measured
    heights are required unless ``height_policy='allow_estimated'`` explicitly
    permits estimates when measurements are absent. Invalid measurements do
    not fall back to estimates.

    With no city terrain, consistent footprint elevations define flat ground.
    City terrain or inconsistent bases require explicit ``terrain='flat'``
    (the bounds' zmin or lowest base) or a numeric ground elevation. Explicit
    bounds use global coordinates, including any supported input translation.

    DTCC transforms are absolute local-to-global translations. Identity
    inherits the enclosing frame, repeated equal translations apply once, and
    conflicting declarations raise. Rotations, scales and shears are rejected.
    Other city objects are omitted and listed in result metadata.
    """
    condition = _validate_condition(speed, direction, reference_height, roughness_length)
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    solver = _validate_solver(tolerance, max_iterations, raise_on_nonconvergence, solver_precision)
    geometry, prepared = _prepare_city(city, condition, grid, terrain, height_policy)
    native_condition = _qes.WindCondition()
    for name in ("speed", "direction", "reference_height"):
        setattr(native_condition, name, condition[name])
    native_solver = _qes.SolverOptions()
    native_solver.tolerance, native_solver.max_iterations = solver["tolerance"], solver["max_iterations"]
    native_solver.precision = solver["precision"]
    runner = _qes.WindRunner()
    try:
        runner.prepare(prepared.grid, prepared.model, **prepared.arrays, dz_layers=prepared.dz_layers)
        native = runner.solve(native_condition, native_solver)
    finally:
        # Arrays already own their storage. A retained Python exception's
        # traceback must not retain the much larger prepared native domain.
        del runner
    diagnostics = SolveDiagnostics(**native["diagnostics"])
    if not diagnostics.converged:
        if solver["raise_on_nonconvergence"]:
            raise ConvergenceError(diagnostics)
        get_python_logger("dtcc-qes").warning(str(ConvergenceError(diagnostics)))
    model_names = ("wall_roughness", "rooftop_flag", "upwind_cavity_flag", "street_canyon_flag",
                   "street_intersection_flag", "wake_flag", "high_rise_flag", "sidewall_flag")
    metadata = dict(
        divergence_diagnostic=dict(unit="s^-1", norm="volume-weighted RMS and maximum",
            lateral_boundary_cells="excluded", last_solved_band="reported separately",
            highest_physical_layer="unassessed"),
        domain=prepared.domain, condition=condition, solver=solver, terrain=prepared.terrain,
        effective_condition={name: float(np.float32(value)) for name, value in condition.items()},
        height_policy=height_policy, ignored_city_objects=geometry.ignored_objects,
        model=dict(backend=_qes.cpu_backend, log_law_flag=0, mesh_type_flag=0, halo_x=0, halo_y=0,
                   vertical_stretching=0 if vertical_grid is None else 1,
                   boundary_layer="neutral logarithmic", sensor=(prepared.model.sensor_x, prepared.model.sensor_y),
                   timestamp="2020-01-01T00:00:00", **{name: getattr(prepared.model, name) for name in model_names}),
        versions=dict(dtcc_qes=__version__, qes=dict(version=_qes.qes_version, revision=_qes.qes_revision),
                      dtcc_core=_dtcc_version(), native_build=dict(compiler_id=_qes.compiler_id,
                          compiler_version=_qes.compiler_version, build_type=_qes.build_type,
                          openmp_enabled=_qes.openmp_enabled)),
        buildings=[dict(native_id=i, source_id=source_id, height=height, height_source=source,
                        original_base_range=base_range, redundant_vertices_removed=removed)
                   for i, (source_id, height, source, base_range, removed) in enumerate(zip(
                       geometry.source_ids, geometry.heights, geometry.height_sources,
                       geometry.base_ranges, geometry.removed_vertices))],
        simplifications=["LOD0 footprints extruded to constant heights", "flat ground",
                         "stair-step cells" if vertical_grid is None else
                         f"stair-step cells with {'automatic' if vertical_grid.mode == 'auto' else 'explicit'} vertical layers"],
        transform_policy="absolute translations applied once; identity inherits enclosing frame",
        coordinates="local metres; add origin to recover the input global frame",
        dtcc_cell_order="y, x, z fastest (VolumeGrid.coordinates meshgrid xy)",
    )
    return WindResult(native["velocity"], native["x"], native["y"], native["z"], native["cell_flags"],
                      prepared.origin, geometry.crs, prepared.resolution, diagnostics, metadata,
                      z_faces=native["z_faces"])


def preview_grid(city, *, reference_height: float = 10.0, roughness_length: float = 0.1,
                 resolution: float = 2.0, bounds=None, horizontal_padding: float = 20.0,
                 vertical_clearance: float = 20.0, max_cells: int = 20_000_000,
                 terrain=None, height_policy="measured",
                 vertical_grid: VerticalGrid | None = None, turbulence: bool = False) -> GridPreview:
    """Inspect a uniform, explicit or automatic grid without QES wind arrays.

    Geometry, terrain, bounds, clearance and cell limits use the same preparation
    as ``run``. Reference height and roughness use the same profile validation;
    reference height also constrains automatic domain bounds. No wind speed,
    direction or solver settings are needed. Axes are local metres; add origin
    for global coordinates. This does not predict occupancy or solver accuracy.

    ``turbulence=True`` includes the QES reference-height layer margin. Automatic
    domains append a constant tail while retaining a valid wind-only grid;
    explicit bounds/faces are checked. Growth and any required regeneration
    are recorded in ``domain['turbulence']``.
    """
    condition = _validate_condition(0, 0, reference_height, roughness_length)
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    geometry, prepared = _prepare_city(city, condition, grid, terrain, height_policy, turbulence=turbulence)
    nz, ny, nx = prepared.domain["shape"]
    spacing = np.float32(prepared.resolution)
    faces = np.asarray(prepared.domain["vertical_grid"]["effective_faces"], dtype=np.float32)
    solver_dz = (np.full(nz, spacing, dtype=np.float32) if prepared.dz_layers is None
                 else prepared.dz_layers.astype(np.float32))
    return GridPreview((np.arange(nx, dtype=np.float32) + np.float32(0.5)) * spacing,
                       (np.arange(ny, dtype=np.float32) + np.float32(0.5)) * spacing,
                       np.float32(0.5) * (faces[:-1] + faces[1:]), faces, solver_dz,
                       prepared.origin, geometry.crs, prepared.resolution, prepared.domain, prepared.terrain)


def _prepare_city(city, condition, grid, terrain, height_policy, *, turbulence=False):
    """Shared geometry and domain preparation for solving and grid preview."""
    if not isinstance(turbulence, bool):
        raise ValueError("turbulence must be a bool")
    if terrain is not None and not (isinstance(terrain, str) and terrain == "flat"):
        terrain = number(terrain, "terrain elevation")
    geometry = extract_city(city, height_policy)
    prepared = prepare_domain(geometry, reference_height=condition["reference_height"],
                              roughness_length=condition["roughness_length"], **grid, terrain=terrain,
                              turbulence=turbulence)
    return geometry, prepared


def _validate_condition(speed, direction, reference_height, roughness_length):
    values = dict(speed=speed, direction=direction, reference_height=reference_height, roughness_length=roughness_length)
    for name in ("speed", "direction", "reference_height", "roughness_length"):
        value = number(values[name], name, positive=name in ("reference_height", "roughness_length"))
        if abs(value) > float(np.finfo(np.float32).max):
            raise ValueError(f"{name} must be representable in float32")
        values[name] = value
    if values["speed"] < 0 or not 0 <= values["direction"] < 360:
        raise ValueError("speed must be nonnegative and direction must be in [0, 360)")
    height = float(np.float32(values["reference_height"]))
    roughness = float(np.float32(values["roughness_length"]))
    if roughness <= 0 or height <= 0 or height + roughness > float(np.finfo(np.float32).max):
        raise ValueError("Reference height and roughness must form a finite float32 profile")
    ratio = float(np.float32(height + roughness)) / roughness
    if not 1 < ratio <= float(np.finfo(np.float32).max) or np.float32(ratio) <= 1:
        raise ValueError("Reference height and roughness must form a finite float32 log profile")
    return values


def _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells, *, vertical_grid=None):
    if vertical_grid is not None and not isinstance(vertical_grid, VerticalGrid):
        raise ValueError("vertical_grid must be a VerticalGrid.from_faces(...) or VerticalGrid.auto(...) specification, or None")
    values = dict(resolution=resolution, horizontal_padding=horizontal_padding, vertical_clearance=vertical_clearance)
    for name in ("resolution", "horizontal_padding", "vertical_clearance"):
        value = number(values[name], name, positive=name == "resolution")
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
        values[name] = value
    resolution = values["resolution"]
    if (isinstance(max_cells, (bool, np.bool_)) or not isinstance(max_cells, Integral)
            or not 1 <= max_cells <= np.iinfo(np.int64).max):
        raise ValueError("max_cells must be a positive int64 integer")
    max_cells = int(max_cells)
    # Match the native coefficient check without overflowing float casts.
    limit = float(np.finfo(np.float32).max)
    if not math.sqrt(1 / limit) <= resolution <= math.sqrt(limit):
        raise ValueError("resolution cannot form finite float32 solver coefficients")
    # Near these limits, narrowing can cross the boundary. Check the actual
    # native operations so preview cannot accept a grid rejected by prepare.
    with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
        spacing = np.float32(resolution)
        squared = spacing * spacing
        coefficient = np.float32(1) / squared
    if not np.isfinite(squared) or squared <= 0 or not np.isfinite(coefficient):
        raise ValueError("resolution cannot form finite float32 solver coefficients")
    if bounds is not None:
        coordinates = bounds
        if isinstance(coordinates, Bounds):
            coordinates = (coordinates.xmin, coordinates.ymin, coordinates.zmin,
                           coordinates.xmax, coordinates.ymax, coordinates.zmax)
        try:
            coordinates = tuple(number(value, "bounds") for value in coordinates)
        except TypeError as error:
            raise ValueError("bounds must contain six finite coordinates") from error
        if len(coordinates) != 6 or any(coordinates[i + 3] <= coordinates[i] for i in range(3)):
            raise ValueError("bounds must be (xmin, ymin, zmin, xmax, ymax, zmax) with positive extents")
        bounds = coordinates
    return dict(**values, bounds=bounds, max_cells=max_cells, vertical_grid=vertical_grid)


def _validate_solver(tolerance, max_iterations, raise_on_nonconvergence, precision="float32"):
    if not isinstance(precision, str) or precision not in ("float32", "float64"):
        raise ValueError("solver_precision must be 'float32' or 'float64'")
    tolerance = number(tolerance, "tolerance", positive=True)
    limits = np.finfo(precision)
    if not float(limits.eps) <= tolerance <= float(limits.max):
        raise ValueError(f"tolerance must be at least {precision} epsilon and finite in {precision}")
    if (isinstance(max_iterations, (bool, np.bool_)) or not isinstance(max_iterations, Integral)
            or not 1 <= max_iterations <= np.iinfo(np.int32).max):
        raise ValueError("max_iterations must be a positive int32 integer")
    if not isinstance(raise_on_nonconvergence, bool):
        raise ValueError("raise_on_nonconvergence must be a bool")
    max_iterations = int(max_iterations)
    return dict(tolerance=tolerance, max_iterations=max_iterations,
                raise_on_nonconvergence=raise_on_nonconvergence, precision=precision)
