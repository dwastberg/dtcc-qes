"""Run canonical LOD0 DTCC buildings through the in-memory QES CPU solver."""

from importlib.metadata import distribution
from copy import deepcopy
import time
import json
from dataclasses import replace
import math
from typing import Literal
import numpy as np

from dtcc_core.common import get_python_logger
from dtcc_core.model import Bounds

from . import __version__, _qes
from ._city import extract_city, near_contacts, number, prepare_domain
from .result import ConvergenceError, SolveDiagnostics, TurbulenceFields, WindPointSample, WindResult, WindSample
from .turbulence import Turbulence, _resolve_turbulence, _turbulence_metadata
from .vertical_grid import GridPreview, VerticalGrid
from .footprints import Footprints
from ._validation import integer
from .solver_control import (Solver, MonitorSpec, Receptor, MassRegion, BudgetExhaustedError,
                             NumericalFailureError, UnacceptedResultError)
from .profiles import (LogProfile, MeasuredProfile, PowerLawProfile, UniformProfile,
                       PROFILE_TYPES, profile_from_dict, evaluate, _profile_record)

__all__ = ["run", "preview_grid", "WindResult", "WindSample", "WindPointSample", "GridPreview",
           "SolveDiagnostics", "ConvergenceError", "VerticalGrid", "Turbulence", "TurbulenceFields",
           "Solver", "MonitorSpec", "Receptor", "MassRegion", "BudgetExhaustedError",
           "NumericalFailureError", "UnacceptedResultError",
           "LogProfile", "MeasuredProfile", "PowerLawProfile", "UniformProfile", "profile_from_dict", "evaluate", "Footprints"]


def _dtcc_version():
    installed = distribution("dtcc-core")
    direct_url = installed.read_text("direct_url.json")
    details = json.loads(direct_url) if direct_url else {}
    return dict(version=installed.version, revision=details.get("vcs_info", {}).get("commit_id"))


def run(city, profile: LogProfile | MeasuredProfile | PowerLawProfile | UniformProfile | None = None, *,
        speed: float | None = None, direction: float | None = None,
        resolution: float = 2.0,
        bounds: Bounds | tuple[float, float, float, float, float, float | None] | None = None,
        horizontal_padding: float = 20.0, vertical_clearance: float = 20.0,
        max_cells: int = 20_000_000, solver: Solver = Solver(),
        terrain: Literal["flat"] | float | None = None,
        height_policy: Literal["measured", "allow_estimated"] = "measured", vertical_grid: VerticalGrid | None = None,
        turbulence: Turbulence | None = None, footprints: Footprints | None = None) -> WindResult:
    """Solve one explicit wind condition without modifying the source city.

    Supply an immutable profile as the second argument or via ``profile=``.
    Keyword ``speed=`` and ``direction=`` construct LogProfile with default
    reference height and roughness. They cannot be combined with a profile.
    Each profile carries roughness_length for ground and measured lower tails.
    Measured vectors interpolate in log height by default (physical height is
    optional); out-of-range evaluation
    requires an explicit lower tail; the upper default holds the last vector.
    New profiles are experimental. Turning and turbulence are supported. Profiles
    initialize the entire background field before building models and correction.

    Speed is in m/s. Direction is clockwise from north and denotes where the
    wind comes from. Reference height, roughness and cell resolution are metres.
    With ``vertical_grid=VerticalGrid.from_faces(...)``, resolution sets x/y
    spacing and the supplied faces set the vertical layers above flat ground.
    ``VerticalGrid.auto(...)`` generates a provisional geometry-based grid;
    its policy settings have not yet passed the C2 accuracy/cost study.
    Nonuniform results retain their coordinates and cannot be exported directly
    to DTCC's uniform VolumeGrid.
    Bounds are DTCC Bounds or (xmin, ymin, zmin, xmax, ymax, zmax). A tuple
    with zmax=None fixes x/y and ground while computing the top using the same
    wind-only planning and turbulence extension as automatic bounds. Numeric
    tops and explicit vertical faces remain fixed. Upper edges
    expand to whole cells horizontally. Automatic vertical grids fit the selected
    top before native coordinate rounding. Automatic bounds use at least three
    cells of padding.
    ``solver=Solver(...)`` owns tolerance, iterations, precision and failure
    behavior. A budget plus MonitorSpec selects bounded native execution;
    policy="pedestrian-v1" additionally requests adaptive numerical assessment.
    Solver() retains the legacy tolerance/iteration stop. The cooperative budget
    covers mutex wait, initialization and monitoring, with preparation and final
    output/turbulence outside the solve budget. A zero-sweep deadline always
    raises BudgetExhaustedError. Completed-work failures return the available
    fields with a warning, or raise when solver.raise_on_failure is true.
    result.solver records the specification, untouched native control record
    (None in legacy mode) and execution environment separately. Acceptance and
    legacy multiplier-change convergence remain independent.

    ``turbulence=Turbulence()`` also returns QES-Turb stresses, TKE, C0*epsilon and
    mixing lengths. ``Turbulence(mixing_length='wall_distance')`` selects the
    qualified serial wall method; the provisional default is height. Automatic
    bounds may grow to provide the reference-height margin. Explicit bounds
    and faces are checked. Derived streamwise standard deviation and intensity
    mask uncomputed or invalid covariance and undefined mean directions.
    This algebraic model has not been validated for pedestrian gusts.

    ``footprints=Footprints(...)`` opts into cleaning touching, overlapping,
    multipart and holed footprints into height-preserving canonical solids.
    Its default exposure rules suppress parameterizations from hidden walls.
    Cleaning tolerance is in metres and independent of grid resolution.
    Source-to-solid mappings and cleaning decisions are recorded in metadata.

    The input uses one shared planar frame in metres (or an unlabelled local
    metre frame). With ``footprints=None``, only single, hole-free LOD0 Surfaces
    are accepted; footprints
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

    Metadata timings nest: public_call_seconds includes city preparation,
    native execution, output construction and cleanup. Native totals include
    their phase timers; do not add parents and children. Unavailable native
    timings are None when the calling path did not measure them.
    """
    public_started = time.perf_counter()
    turbulence_spec = _resolve_turbulence(turbulence)
    if not isinstance(solver, Solver):
        raise TypeError("solver must be Solver")
    profile_spec = _resolve_condition(speed, direction, profile)
    exclusions = _check_solver_inputs(solver, profile_spec, turbulence_spec)
    if exclusions:
        _warn_solver_outcome(str(UnacceptedResultError(None, None, exclusions=exclusions)), turbulence_spec)
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    preparation_started = time.perf_counter()
    geometry, prepared = _prepare_city(city, profile_spec, grid, terrain, height_policy,
                                        turbulence=turbulence_spec is not None,
                                        footprints=footprints)
    preparation_seconds = time.perf_counter() - preparation_started
    result = _solve_prepared(geometry, prepared, profile_spec, solver, vertical_grid=vertical_grid,
        turbulence_spec=turbulence_spec, height_policy=height_policy,
        _known_exclusions=exclusions)
    result.metadata["timings"]["city_preparation_seconds"] = preparation_seconds
    result.metadata["timings"]["public_call_seconds"] = time.perf_counter() - public_started
    return result


def _solve_prepared(geometry, prepared, profile, solver, *, vertical_grid=None,
                    turbulence_spec=None, height_policy="measured",
                    _known_exclusions=()):
    """Solve a validated prepared domain and assemble the common result metadata."""
    adaptive = solver.mode == "adaptive"
    if profile is None:
        raise ValueError("Solving requires a known inflow profile")
    profile_record = prepared.domain["profile"]
    native_condition = _native_condition(profile_record)
    if profile_record["max_turning_deg"] > 45:
        get_python_logger("dtcc-qes").warning(
            "Background profile turns %.1f degrees across physical layers (>45 degrees); "
            "building wakes follow each roof-level direction, including where lower layers turn.",
            profile_record["max_turning_deg"])
    native_solver = _native_solver(solver)
    eligibility = _preflight_eligibility(prepared,geometry,profile,solver,turbulence_spec)
    if eligibility["exclusions"]:
        if solver.raise_on_failure:
            raise UnacceptedResultError(None,None,exclusions=eligibility["exclusions"])
        if not _known_exclusions:
            _warn_solver_outcome(str(UnacceptedResultError(None,None,exclusions=eligibility["exclusions"])),turbulence_spec)
        _known_exclusions = eligibility["exclusions"]
    runner = _qes.WindRunner()
    try:
        turbulence_options = {}
        if turbulence_spec is not None:
            native_turbulence = _qes.TurbulenceSettings()
            native_turbulence.enabled = True
            native_turbulence.mixing_length_method = turbulence_spec.qes_method
            turbulence_options["turbulence"] = native_turbulence
        runner.prepare(prepared.grid, prepared.model, **prepared.arrays, dz_layers=prepared.dz_layers,
                       **turbulence_options)
        control_options = {} if solver.mode == "legacy" else {"control":solver._native(prepared.origin, geometry.crs)}
        native = runner.solve(native_condition, native_solver, **control_options)
    finally:
        # Arrays already own their storage. A retained Python exception's
        # traceback must not retain the much larger prepared native domain.
        del runner
    diagnostics = SolveDiagnostics(**native["diagnostics"])
    record = native.get("control")
    failure = None
    if adaptive and not record["accepted"]:
        failure = UnacceptedResultError(diagnostics, record)
    elif not adaptive and not diagnostics.converged:
        failure = ConvergenceError(diagnostics, record)
    if failure is not None:
        if solver.raise_on_failure:
            raise failure
        if not _known_exclusions:
            _warn_solver_outcome(str(failure), turbulence_spec)
    elif record is not None and record["termination_reason"] == "time_limit" and not _known_exclusions:
        _warn_solver_outcome(f"Wind solve reached time_limit after {diagnostics.iterations} iterations", turbulence_spec)
    model_names = ("wall_roughness", "rooftop_flag", "upwind_cavity_flag", "street_canyon_flag",
                   "street_intersection_flag", "wake_flag", "high_rise_flag", "sidewall_flag")
    metadata = dict(
        divergence_diagnostic=dict(unit="s^-1", norm="volume-weighted RMS and maximum",
            lateral_boundary_cells="excluded", last_solved_band="reported separately",
            highest_physical_layer="unassessed"),
        domain=prepared.domain, terrain=prepared.terrain,
        height_policy=height_policy, ignored_city_objects=geometry.ignored_objects,
        model=dict(backend=_qes.cpu_backend, log_law_flag=0, mesh_type_flag=0, halo_x=0, halo_y=0,
                   vertical_stretching=0 if vertical_grid is None else 1,
                   boundary_layer=profile_record["boundary_layer"], sensor=(prepared.model.sensor_x, prepared.model.sensor_y),
                   timestamp="2020-01-01T00:00:00", **{name: getattr(prepared.model, name) for name in model_names}),
        versions=dict(dtcc_qes=__version__, qes=dict(version=_qes.qes_version, revision=_qes.qes_revision),
                      dtcc_core=_dtcc_version(), native_build=dict(compiler_id=_qes.compiler_id,
                          compiler_version=_qes.compiler_version, build_type=_qes.build_type,
                          openmp_enabled=_qes.openmp_enabled, fp_contract=_qes.fp_contract,
                          solver_policy_build_supported=_qes.solver_policy_build_supported)),
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
    if prepared.footprints is not None:
        final = prepared.footprints
        metadata["footprints"] = final.metadata
        metadata["solids"] = final.metadata["solids"]
        metadata["buildings"] = [dict(row)
            for row in final.metadata["buildings"]]
        metadata["model"].update(exposed_faces=prepared.model.exposed_faces,
            building_geometry="canonical-prisms-v1", exposure_rule="initial-mask-normal-dda-v1")
    if prepared.near_contacts:
        metadata["near_contacts"] = list(prepared.near_contacts)
    metadata["profile"] = profile_record
    turbulence_fields = None
    metadata["solver"] = dict(spec=solver.to_dict(), record=record,
        environment=dict(precision=solver.precision, backend=_qes.cpu_backend,
            sweep_order=_qes.cpu_sweep_order, native_build=dict(metadata["versions"]["native_build"]),
            source_revision=_qes.qes_revision, shape=list(native["cell_flags"].shape)))
    metadata["timings"] = _timing_report(record,native.get("timings"))
    if turbulence_spec is not None:
        fields = native["turbulence"]
        turbulence_fields = TurbulenceFields(stress=fields["stress"],tke=fields["tke"],co_eps=fields["co_eps"],
            mixing_length=fields["mixing_length"],computed=fields["state"] > 0,capped=fields["state"] == 2,
            stress_valid=fields["stress_valid"].astype(bool),friction_velocity=fields["friction_velocity"],
            reference_speed=fields["reference_speed"],reference_height=fields["reference_height"],
            roughness_length=fields["roughness_length"],displacement_height=fields["displacement_height"])
        metadata["turbulence"] = _turbulence_metadata(turbulence_spec,fields,prepared.domain["turbulence"],
                                                    native["velocity"],bool(geometry.heights))
        if profile_record["kind"] != "log":
            metadata["turbulence"]["caveats"] = list(profile_record["caveats"])
    return WindResult(native["velocity"], native["x"], native["y"], native["z"], native["cell_flags"],
                      prepared.origin, geometry.crs, prepared.resolution, diagnostics, metadata,
                      z_faces=native["z_faces"],turbulence=turbulence_fields)


def preview_grid(city, profile: LogProfile | MeasuredProfile | PowerLawProfile | UniformProfile | None = None, *,
                 speed: float | None = None, direction: float | None = None,
                 resolution: float = 2.0,
                 bounds: Bounds | tuple[float, float, float, float, float, float | None] | None = None,
                 horizontal_padding: float = 20.0,
                 vertical_clearance: float = 20.0, max_cells: int = 20_000_000,
                 terrain: Literal["flat"] | float | None = None,
                 height_policy: Literal["measured", "allow_estimated"] = "measured",
                 vertical_grid: VerticalGrid | None = None, turbulence: Turbulence | None = None,
                 footprints: Footprints | None = None, solver: Solver | None = None) -> GridPreview:
    """Inspect a uniform, explicit or automatic grid without QES wind arrays.

    ``footprints=Footprints(...)`` uses the same cleaning and final solid mapping
    as ``run``; details are in ``domain["footprints"]``.

    Geometry, terrain, bounds, clearance and cell limits use the same preparation
    as ``run``. Reference height and roughness use the same profile validation;
    reference height also constrains automatic domain bounds. Omitting inflow
    uses planning defaults (10 m reference, 0.1 m roughness) and records unknown
    inflow. To plan other values, provide LogProfile(1, 0, reference_height=...,
    roughness_length=...). No solver settings are needed. Axes are local metres; add origin
    for global coordinates. This does not predict occupancy or solver accuracy.

    ``turbulence=Turbulence()`` includes the QES reference-height layer margin. Automatic
    domains append a constant tail while retaining a valid wind-only grid;
    explicit bounds/faces are checked. Growth and any required regeneration
    are recorded in ``domain['turbulence']``.
    """
    if solver is not None and not isinstance(solver,Solver):
        raise TypeError("solver must be Solver or None")
    turbulence_spec = _resolve_turbulence(turbulence)
    profile_spec = _resolve_condition(speed, direction, profile, allow_unknown=True)
    if solver is not None and solver.mode == "adaptive":
        if profile_spec is None:
            raise ValueError("Adaptive eligibility requires an explicit profile or speed/direction; grid-only preview remains available without solver")
        if profile_spec.reference["speed"] == 0:
            raise ValueError("Adaptive pedestrian acceptance is unavailable for calm wind")
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    geometry, prepared = _prepare_city(city, profile_spec, grid, terrain, height_policy,
                                        turbulence=turbulence_spec is not None,
                                        footprints=footprints)
    nz, ny, nx = prepared.domain["shape"]
    spacing = np.float32(prepared.resolution)
    faces = np.asarray(prepared.domain["vertical_grid"]["effective_faces"], dtype=np.float32)
    solver_dz = (np.full(nz, spacing, dtype=np.float32) if prepared.dz_layers is None
                 else prepared.dz_layers.astype(np.float32))
    return GridPreview((np.arange(nx, dtype=np.float32) + np.float32(0.5)) * spacing,
                       (np.arange(ny, dtype=np.float32) + np.float32(0.5)) * spacing,
                       np.float32(0.5) * (faces[:-1] + faces[1:]), faces, solver_dz,
                       prepared.origin, geometry.crs, prepared.resolution, prepared.domain, prepared.terrain,
                       None if solver is None else _preflight_eligibility(prepared,geometry,profile_spec,solver,turbulence_spec))


def _prepare_city(city, profile, grid, terrain, height_policy, *, turbulence=False, footprints=None):
    """Shared geometry and domain preparation for solving and grid preview."""
    if not isinstance(turbulence, bool):
        raise ValueError("turbulence must be a bool")
    if terrain is not None and not (isinstance(terrain, str) and terrain == "flat"):
        terrain = number(terrain, "terrain elevation")
    reference_height = profile.reference_height if profile is not None else 10.
    roughness_length = profile.roughness_length if profile is not None else .1
    if footprints is not None:
        if not isinstance(footprints, Footprints):
            raise TypeError("footprints must be Footprints or None")
        from ._footprints import prepare_footprint_domain
        geometry, prepared = prepare_footprint_domain(city, height_policy, footprints,
            reference_height=reference_height, roughness_length=roughness_length,
            **grid, terrain=terrain, turbulence=turbulence)
    else:
        geometry = extract_city(city, height_policy)
        prepared = prepare_domain(geometry, reference_height=reference_height,
                                  roughness_length=roughness_length, **grid, terrain=terrain,
                                  turbulence=turbulence)
    contacts = near_contacts(geometry, prepared.resolution) if footprints is None else ()
    if contacts:
        get_python_logger("dtcc-qes").warning(
            "%d building pairs are closer than one grid cell; use Footprints for contact-aware preparation", len(contacts))
        prepared = replace(prepared, near_contacts=contacts,
                           domain=dict(prepared.domain, near_contacts=list(contacts)))
    _prepare_profile(prepared, profile)
    return geometry, prepared


def _prepare_profile(prepared, profile):
    """Build exactly one record after canonical solids and the grid stabilize."""
    heights = None
    if profile is None:
        prepared.domain.update(profile=None, inflow="unknown")
    else:
        heights = None if isinstance(profile, LogProfile) else _layer_heights(prepared)
        try:
            prepared.domain["profile"] = _profile_record(profile, heights)
        except ValueError as error:
            growth = prepared.domain.get("turbulence", {})
            if "above last measurement" in str(error) and growth.get("raised"):
                added = growth.get("added_layers", 0)
                base_covered = (profile.heights[-1] >= growth["default_top"]
                    if not growth.get("lower_layers_preserved", True) else
                    added > 0 and heights[-added-1] <= profile.heights[-1])
                if base_covered:
                    requirements = json.dumps(prepared.domain["top_requirements"], allow_nan=False, sort_keys=True)
                    raise ValueError(f"{error}; turbulence domain growth raised the top from "
                        f"{growth['default_top']:.9g} m to {growth['effective_top']:.9g} m; "
                        f"top_requirements={requirements}") from error
            raise
    vertical = prepared.domain["vertical_grid"]
    if vertical["mode"] == "auto":
        from .profiles import _pedestrian_sampling
        centres = _layer_heights(prepared) if heights is None else heights
        vertical["pedestrian_sampling"] = _pedestrian_sampling(profile, centres,
            vertical["requested_settings"]["pedestrian_height"], prepared.domain["profile"])



def _resolve_condition(speed, direction, profile, *, allow_unknown=False):
    if profile is not None:
        if type(profile) not in PROFILE_TYPES:
            raise TypeError("profile must be LogProfile, MeasuredProfile, PowerLawProfile or UniformProfile")
        if speed is not None or direction is not None:
            raise ValueError("profile is mutually exclusive with speed and direction")
    elif allow_unknown and speed is None and direction is None:
        return None
    elif speed is None or direction is None:
        raise TypeError("Provide a profile or both speed and direction")
    else:
        profile = LogProfile(speed, direction)
    if profile.reference["speed"] > float(np.finfo(np.float32).max):
        raise ValueError("Reference speed must remain finite in float32")
    return profile


def _layer_heights(prepared):
    faces = np.asarray(prepared.domain["vertical_grid"]["effective_faces"], dtype=np.float32)
    return (np.float32(.5) * (faces[:-1] + faces[1:])).astype(np.float64)


def _native_condition(profile_record):
    native = _qes.WindCondition()
    reference = profile_record["reference"]
    # The controller normalizes by the declared float64 speed. Narrowing for
    # Log evaluation remains native; do not feed the narrowed metadata back in.
    native.speed = reference["speed"]
    native.reference_height = reference["height"]
    native.direction = (profile_record["requested"]["direction"] if profile_record["kind"] == "log"
                        else reference["direction"] or 0.)
    if profile_record["kind"] != "log":
        table = profile_record["layer_table"]
        native.profile_kind = _qes.ProfileKind.layer_table
        native.layer_u, native.layer_v = table["u"], table["v"]
    return native


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
    max_cells = integer(max_cells,"max_cells",maximum=np.iinfo(np.int64).max)
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
            coordinates = tuple(coordinates)
            if len(coordinates) != 6:
                raise ValueError("bounds must contain six coordinates")
            coordinates = tuple(None if i == 5 and value is None else number(value, "bounds")
                                for i, value in enumerate(coordinates))
        except TypeError as error:
            raise ValueError("bounds must contain six finite coordinates") from error
        if len(coordinates) != 6 or any(coordinates[i + 3] is not None and coordinates[i + 3] <= coordinates[i] for i in range(3)):
            raise ValueError("bounds must be (xmin, ymin, zmin, xmax, ymax, zmax) with positive extents")
        bounds = coordinates
    return dict(**values, bounds=bounds, max_cells=max_cells, vertical_grid=vertical_grid)


def _check_solver_inputs(solver, profile, turbulence):
    """Input-only scope checks; native code remains authoritative at runtime."""
    if solver.mode != "adaptive":
        return []
    if profile.reference["speed"] == 0:
        raise ValueError("Adaptive pedestrian acceptance is unavailable for calm wind")
    kind = _qes.ProfileKind.log if isinstance(profile,LogProfile) else _qes.ProfileKind.layer_table
    exclusions = _qes._pedestrian_input_exclusions(kind,_native_solver(solver),turbulence is not None)
    if exclusions and solver.raise_on_failure:
        raise UnacceptedResultError(None, None, exclusions=exclusions)
    return exclusions


def _warn_solver_outcome(message, turbulence):
    if turbulence is not None:
        message += "; requested turbulence is screening output based on this mean wind"
    get_python_logger("dtcc-qes").warning(message)


def _timing_report(record,native_timings=None):
    """Report nested scopes without inventing unavailable native measurements.

    Public-call time belongs to wind.run, including validation, preparation,
    output construction and cleanup. City preparation includes profile/grid
    resolution. Native totals include native phase children: do not sum them.
    Paths bypassing wind.run leave its public-call measurement unavailable.
    """
    return dict(public_call_seconds=None, city_preparation_seconds=None,
        native=deepcopy(record["timings"] if record is not None else native_timings),
        scopes=dict(public_call="wind.run: validation, city preparation, native execution, output and cleanup",
            city_preparation="geometry, domain planning and profile preparation; nested in public_call",
            native="native totals contain phase timers; do not add parent totals and children"))


def _native_solver(solver):
    options=_qes.SolverOptions()
    options.tolerance,options.max_iterations=solver.tolerance,solver.max_iterations
    options.precision=solver.precision
    return options


def _preflight_eligibility(prepared,geometry,profile,solver,turbulence):
    view=dict(mode=solver.mode,policy=solver.policy,exclusions=[],pending_runtime_checks=[])
    if solver.mode!="adaptive":
        return view
    settings=None
    if turbulence is not None:
        settings=_qes.TurbulenceSettings();settings.enabled=True
        settings.mixing_length_method=turbulence.qes_method
    view.update(_qes._pedestrian_preflight(prepared.grid,prepared.model,
        _native_condition(prepared.domain["profile"]),_native_solver(solver),
        solver._native(prepared.origin,geometry.crs),**prepared.arrays,
        dz_layers=prepared.dz_layers,turbulence=settings))
    return view
