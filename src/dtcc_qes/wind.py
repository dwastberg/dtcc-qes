"""Run canonical LOD0 DTCC buildings through the in-memory QES CPU solver."""

from importlib.metadata import distribution
import json
from dataclasses import replace
import math
from numbers import Integral
import numpy as np

from dtcc_core.common import get_python_logger
from dtcc_core.model import Bounds

from . import __version__, _qes
from ._city import extract_city, near_contacts, number, prepare_domain
from .result import ConvergenceError, SolveDiagnostics, TurbulenceFields, WindResult, WindSample
from .turbulence import Turbulence, _resolve_turbulence, _turbulence_metadata
from .vertical_grid import GridPreview, VerticalGrid
from .footprints import Footprints
from .solver_control import (SolverControl, MonitorSpec, Receptor, MassRegion, BudgetExhaustedError,
                             NumericalFailureError, UnacceptedResultError)
from .profiles import (LogProfile, MeasuredProfile, PowerLawProfile, UniformProfile,
                       PROFILE_TYPES, profile_from_dict, evaluate, _layer_record)

_UNSET = object()

__all__ = ["run", "preview_grid", "WindResult", "WindSample", "GridPreview",
           "SolveDiagnostics", "ConvergenceError", "VerticalGrid", "Turbulence", "TurbulenceFields",
           "SolverControl", "MonitorSpec", "Receptor", "MassRegion", "BudgetExhaustedError",
           "NumericalFailureError", "UnacceptedResultError",
           "LogProfile", "MeasuredProfile", "PowerLawProfile", "UniformProfile", "profile_from_dict", "evaluate", "Footprints"]


def _dtcc_version():
    installed = distribution("dtcc-core")
    direct_url = installed.read_text("direct_url.json")
    details = json.loads(direct_url) if direct_url else {}
    return dict(version=installed.version, revision=details.get("vcs_info", {}).get("commit_id"))


def run(city, speed=None, direction=None, *, reference_height=_UNSET,
        roughness_length=_UNSET, profile=None,
        resolution: float = 2.0, bounds=None,
        horizontal_padding: float = 20.0, vertical_clearance: float = 20.0,
        max_cells: int = 20_000_000, tolerance: float = 1e-5, max_iterations: int = 500,
        raise_on_nonconvergence: bool = False, terrain=None, height_policy="measured",
        vertical_grid: VerticalGrid | None = None, solver_precision: str = "float32",
        turbulence: bool | Turbulence = False, solver_control: SolverControl | None = None,
        raise_on_unaccepted: bool = False, footprints: Footprints | None = None) -> WindResult:
    """Solve one explicit wind condition without modifying the source city.

    Supply either legacy speed/direction scalars or an immutable ``profile=``.
    Scalar speed/direction/reference height cannot be combined with a profile.
    Non-log profiles use the run's roughness_length for ground and lower tails.
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
    Bounds are DTCC Bounds or (xmin, ymin, zmin, xmax, ymax, zmax); upper edges
    expand to whole cells horizontally. Automatic vertical grids fit the selected
    top before native coordinate rounding. Automatic bounds use at least three
    cells of padding.
    Non-convergence logs a warning and returns the available result unless
    raise_on_nonconvergence=True.

    ``solver_control=SolverControl(...)`` runs with a cooperative native solve
    budget and bounded diagnostic history. It includes mutex wait and checks
    every complete sweep. Preparation and required final output/turbulence are
    timed separately. ``result.control`` records termination and overshoot;
    bounded accuracy remains ``not_assessed``. No completed sweep raises
    ``BudgetExhaustedError`` with phase/timing evidence.

    ``SolverControl(..., mode='adaptive')`` opts into pedestrian-v1 on its
    qualified small rectangular-building scope. It assesses the declared ROI
    at 1.5/1.75 m and every required receptor, with independent mass/residual
    safeguards. ``control['accepted']`` is separate from legacy ``converged``;
    it does not qualify the full volume, turbulence or physical wind accuracy.
    Unsupported configurations return bounded, unaccepted outputs. Set
    ``raise_on_unaccepted=True`` to raise ``UnacceptedResultError`` instead of
    warning. Adaptive mode rejects ``raise_on_nonconvergence=True`` and calm
    wind. See docs/solver-control-s7.md for the versioned scope and limits.

    ``solver_precision='float64'`` opts into double multiplier storage, RHS,
    updates and face corrections. Geometry, coefficients and returned velocities
    remain float32. Tolerance bounds follow the selected arithmetic precision;
    convergence still measures multiplier change, not a residual guarantee.

    ``turbulence=True`` also returns QES-Turb stresses, TKE, C0*epsilon and
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
    """
    turbulence_spec = _resolve_turbulence(turbulence)
    if solver_control is not None and not isinstance(solver_control, SolverControl):
        raise TypeError("solver_control must be SolverControl or None")
    condition, profile_spec = _resolve_condition(speed, direction, reference_height, roughness_length, profile)
    adaptive = solver_control is not None and solver_control.mode == "adaptive"
    if not isinstance(raise_on_unaccepted, bool):
        raise ValueError("raise_on_unaccepted must be boolean")
    if raise_on_unaccepted and not adaptive:
        raise ValueError("raise_on_unaccepted requires adaptive solver controls")
    if adaptive and raise_on_nonconvergence:
        raise ValueError("Adaptive mode uses raise_on_unaccepted, not raise_on_nonconvergence")
    if adaptive and condition["speed"] == 0:
        raise ValueError("Adaptive pedestrian acceptance is unavailable for calm wind")
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    solver = _validate_solver(tolerance, max_iterations, raise_on_nonconvergence, solver_precision)
    geometry, prepared = _prepare_city(city, condition, grid, terrain, height_policy,
                                        turbulence=turbulence_spec is not None, profile=profile_spec,
                                        footprints=footprints)
    return _solve_prepared(geometry, prepared, condition, solver, vertical_grid=vertical_grid,
        turbulence_spec=turbulence_spec, height_policy=height_policy, profile_spec=profile_spec,
        solver_control=solver_control, raise_on_unaccepted=raise_on_unaccepted)


def _solve_prepared(geometry, prepared, condition, solver, *, vertical_grid=None,
                    turbulence_spec=None, height_policy="measured", profile_spec=None,
                    solver_control=None, raise_on_unaccepted=False):
    """Solve a validated prepared domain and assemble the common result metadata."""
    adaptive = solver_control is not None and solver_control.mode == "adaptive"
    _prepare_profile(prepared, condition, profile_spec)
    profile_record = prepared.domain.get("profile")
    if profile_record is None:
        log_profile = profile_spec or LogProfile(**condition)
        profile_record = dict(schema_version=1, type="log", requested=log_profile.to_dict(),
            reference=log_profile.reference, height_datum="metres above flat ground",
            horizontal_only=True, experimental=False, interpolation="analytic", max_turning_deg=0.,
            tail_layers=dict(below=0, above=0))
    if profile_record["type"] == "log":
        profile_record["native_reference_scalars"] = {
            name: float(np.float32(condition[name])) for name in ("speed", "direction", "reference_height")}
    native_condition = _native_condition(condition, profile_record)
    if profile_record["max_turning_deg"] > 45:
        get_python_logger("dtcc-qes").warning(
            "Background profile turns %.1f degrees across physical layers (>45 degrees); "
            "building wakes follow each roof-level direction, including where lower layers turn.",
            profile_record["max_turning_deg"])
    native_solver = _qes.SolverOptions()
    native_solver.tolerance, native_solver.max_iterations = solver["tolerance"], solver["max_iterations"]
    native_solver.precision = solver["precision"]
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
        control_options = {} if solver_control is None else {"control":solver_control._native(prepared.origin, geometry.crs)}
        native = runner.solve(native_condition, native_solver, **control_options)
    finally:
        # Arrays already own their storage. A retained Python exception's
        # traceback must not retain the much larger prepared native domain.
        del runner
    diagnostics = SolveDiagnostics(**native["diagnostics"])
    if adaptive:
        if not native["control"]["accepted"]:
            failure = UnacceptedResultError(diagnostics, native["control"])
            if raise_on_unaccepted:
                raise failure
            get_python_logger("dtcc-qes").warning(str(failure))
    elif not diagnostics.converged:
        if solver["raise_on_nonconvergence"]:
            raise ConvergenceError(diagnostics,native.get("control"))
        get_python_logger("dtcc-qes").warning(str(ConvergenceError(diagnostics,native.get("control"))))
    model_names = ("wall_roughness", "rooftop_flag", "upwind_cavity_flag", "street_canyon_flag",
                   "street_intersection_flag", "wake_flag", "high_rise_flag", "sidewall_flag")
    solver_metadata = dict(solver)
    if adaptive:
        solver_metadata["raise_on_unaccepted"] = raise_on_unaccepted
    metadata = dict(
        divergence_diagnostic=dict(unit="s^-1", norm="volume-weighted RMS and maximum",
            lateral_boundary_cells="excluded", last_solved_band="reported separately",
            highest_physical_layer="unassessed"),
        domain=prepared.domain, condition=condition, solver=solver_metadata, terrain=prepared.terrain,
        effective_condition={name: float(np.float32(value)) for name, value in condition.items()},
        height_policy=height_policy, ignored_city_objects=geometry.ignored_objects,
        model=dict(backend=_qes.cpu_backend, log_law_flag=0, mesh_type_flag=0, halo_x=0, halo_y=0,
                   vertical_stretching=0 if vertical_grid is None else 1,
                   boundary_layer="neutral logarithmic", sensor=(prepared.model.sensor_x, prepared.model.sensor_y),
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
    if profile_spec is not None and profile_spec.kind != "log":
        metadata["effective_condition"] = dict(metadata["effective_condition"],
            speed=profile_record["reference"]["speed"],
            direction=profile_record["reference"]["direction"])
        metadata["model"]["boundary_layer"] = f"experimental {profile_spec.kind} horizontal profile"
    turbulence_fields = None
    if "control" in native:
        metadata["solver_control"] = native["control"]
        metadata["solver_control"]["execution"] = dict(precision=solver["precision"],backend=_qes.cpu_backend,
            sweep_order=_qes.cpu_sweep_order,native_build=metadata["versions"]["native_build"],
            source_revision=_qes.qes_revision,shape=list(native["cell_flags"].shape))
    if turbulence_spec is not None:
        fields = native["turbulence"]
        turbulence_fields = TurbulenceFields(stress=fields["stress"],tke=fields["tke"],co_eps=fields["co_eps"],
            mixing_length=fields["mixing_length"],computed=fields["state"] > 0,capped=fields["state"] == 2,
            stress_valid=fields["stress_valid"].astype(bool),friction_velocity=fields["friction_velocity"],
            reference_speed=fields["reference_speed"],reference_height=fields["reference_height"],
            roughness_length=fields["roughness_length"],displacement_height=fields["displacement_height"])
        metadata["turbulence"] = _turbulence_metadata(turbulence_spec,fields,prepared.domain["turbulence"],
                                                    native["velocity"],bool(geometry.heights))
        if profile_spec is not None and profile_spec.kind != "log":
            metadata["turbulence"]["profile_caveat"] = profile_record["turbulence_caveat"]
    return WindResult(native["velocity"], native["x"], native["y"], native["z"], native["cell_flags"],
                      prepared.origin, geometry.crs, prepared.resolution, diagnostics, metadata,
                      z_faces=native["z_faces"],turbulence=turbulence_fields)


def preview_grid(city, *, reference_height=_UNSET, roughness_length=_UNSET,
                 profile=None,
                 resolution: float = 2.0, bounds=None, horizontal_padding: float = 20.0,
                 vertical_clearance: float = 20.0, max_cells: int = 20_000_000,
                 terrain=None, height_policy="measured",
                 vertical_grid: VerticalGrid | None = None, turbulence: bool | Turbulence = False,
                 footprints: Footprints | None = None) -> GridPreview:
    """Inspect a uniform, explicit or automatic grid without QES wind arrays.

    ``footprints=Footprints(...)`` uses the same cleaning and final solid mapping
    as ``run``; details are in ``domain["footprints"]``.

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
    turbulence_spec = _resolve_turbulence(turbulence)
    condition, profile_spec = _resolve_condition(
        0 if profile is None else None, 0 if profile is None else None,
        reference_height, roughness_length, profile)
    grid = _validate_grid(resolution, bounds, horizontal_padding, vertical_clearance, max_cells,
                          vertical_grid=vertical_grid)
    geometry, prepared = _prepare_city(city, condition, grid, terrain, height_policy,
                                        turbulence=turbulence_spec is not None, profile=profile_spec,
                                        footprints=footprints)
    nz, ny, nx = prepared.domain["shape"]
    spacing = np.float32(prepared.resolution)
    faces = np.asarray(prepared.domain["vertical_grid"]["effective_faces"], dtype=np.float32)
    solver_dz = (np.full(nz, spacing, dtype=np.float32) if prepared.dz_layers is None
                 else prepared.dz_layers.astype(np.float32))
    return GridPreview((np.arange(nx, dtype=np.float32) + np.float32(0.5)) * spacing,
                       (np.arange(ny, dtype=np.float32) + np.float32(0.5)) * spacing,
                       np.float32(0.5) * (faces[:-1] + faces[1:]), faces, solver_dz,
                       prepared.origin, geometry.crs, prepared.resolution, prepared.domain, prepared.terrain)


def _prepare_city(city, condition, grid, terrain, height_policy, *, turbulence=False,
                  profile=None, footprints=None):
    """Shared geometry and domain preparation for solving and grid preview."""
    if not isinstance(turbulence, bool):
        raise ValueError("turbulence must be a bool")
    if terrain is not None and not (isinstance(terrain, str) and terrain == "flat"):
        terrain = number(terrain, "terrain elevation")
    if footprints is not None:
        if not isinstance(footprints, Footprints):
            raise TypeError("footprints must be Footprints or None")
        from ._footprints import prepare_footprint_domain
        geometry, prepared = prepare_footprint_domain(city, height_policy, footprints,
            reference_height=condition["reference_height"], roughness_length=condition["roughness_length"],
            **grid, terrain=terrain, turbulence=turbulence)
    else:
        geometry = extract_city(city, height_policy)
        prepared = prepare_domain(geometry, reference_height=condition["reference_height"],
                                  roughness_length=condition["roughness_length"], **grid, terrain=terrain,
                                  turbulence=turbulence)
    contacts = near_contacts(geometry, prepared.resolution) if footprints is None else ()
    if contacts:
        get_python_logger("dtcc-qes").warning(
            "%d building pairs are closer than one grid cell; use Footprints for contact-aware preparation", len(contacts))
        prepared = replace(prepared, near_contacts=contacts,
                           domain=dict(prepared.domain, near_contacts=list(contacts)))
    _prepare_profile(prepared, condition, profile)
    return geometry, prepared


def _prepare_profile(prepared, condition, profile):
    """Build profile tables only after canonical solids and the grid stabilize."""
    if profile is not None and profile.kind != "log" and "profile" not in prepared.domain:
        prepared.domain["profile"] = _layer_record(profile, _layer_heights(prepared), condition["roughness_length"])
        prepared.domain["profile"]["native_reference_scalars"] = {
            name: float(np.float32(condition[name])) for name in ("speed", "direction", "reference_height")}


def _resolve_condition(speed, direction, reference_height, roughness_length, profile):
    if profile is not None:
        if type(profile) not in PROFILE_TYPES:
            raise TypeError("profile must be LogProfile, MeasuredProfile, PowerLawProfile or UniformProfile")
        if speed is not None or direction is not None or reference_height is not _UNSET:
            raise ValueError("profile is mutually exclusive with speed, direction and reference_height")
        if isinstance(profile, LogProfile):
            if roughness_length is not _UNSET:
                raise ValueError("LogProfile carries roughness_length; do not also supply it to run")
            return _validate_condition(profile.speed, profile.direction, profile.reference_height,
                                       profile.roughness_length), profile
        roughness = number(.1 if roughness_length is _UNSET else roughness_length, "roughness_length", positive=True)
        with np.errstate(over="ignore", under="ignore"):
            native_roughness = np.float32(roughness)
        if not np.isfinite(native_roughness) or native_roughness <= 0:
            raise ValueError("roughness_length must remain positive and finite in float32")
        reference = profile.reference_at(roughness)
        if reference["speed"] > float(np.finfo(np.float32).max):
            raise ValueError("Reference speed must remain finite in float32")
        return dict(speed=reference["speed"], direction=reference["direction"] or 0.0,
                    reference_height=profile.reference_height, roughness_length=roughness), profile
    if speed is None or direction is None:
        raise TypeError("run requires speed and direction, or profile=")
    return _validate_condition(speed, direction,
                               10.0 if reference_height is _UNSET else reference_height,
                               .1 if roughness_length is _UNSET else roughness_length), None


def _layer_heights(prepared):
    faces = np.asarray(prepared.domain["vertical_grid"]["effective_faces"], dtype=np.float32)
    return (np.float32(.5) * (faces[:-1] + faces[1:])).astype(np.float64)


def _native_condition(condition, profile_record):
    native = _qes.WindCondition()
    for name in ("speed", "direction", "reference_height"):
        setattr(native, name, condition[name])
    if profile_record["type"] != "log":
        table = profile_record["layer_table"]
        native.profile_kind = _qes.ProfileKind.layer_table
        native.layer_u, native.layer_v = table["u"], table["v"]
    return native


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
