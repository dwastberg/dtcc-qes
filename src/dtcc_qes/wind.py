"""Run canonical LOD0 DTCC buildings through the in-memory QES CPU solver."""

from dataclasses import asdict
from importlib.metadata import distribution
import json
import numpy as np

from dtcc_core.common import get_python_logger

from . import __version__, _qes
from ._city import extract_city
from ._config import FlatTerrain, GridSpec, SolverOptions, WindCondition, prepare_config
from .result import ConvergenceError, SolveDiagnostics, WindResult

__all__ = ["run", "WindCondition", "GridSpec", "SolverOptions", "FlatTerrain",
           "WindResult", "SolveDiagnostics", "ConvergenceError"]


def _dtcc_version():
    installed = distribution("dtcc-core")
    direct_url = installed.read_text("direct_url.json")
    details = json.loads(direct_url) if direct_url else {}
    return dict(version=installed.version, revision=details.get("vcs_info", {}).get("commit_id"))


def run(city, condition: WindCondition, *, grid=GridSpec(), solver=SolverOptions(),
        terrain=None, height_policy="measured") -> WindResult:
    """Solve one explicit wind condition without modifying the source city.

    The input uses one shared planar frame in metres (or an unlabelled local
    metre frame). Only single, hole-free LOD0 Surfaces are accepted; footprints
    may not overlap or touch, and building parts are unsupported. Measured
    heights are required unless ``height_policy='allow_estimated'`` explicitly
    permits estimates when measurements are absent. Invalid measurements do
    not fall back to estimates.

    With no city terrain, consistent footprint elevations define flat ground.
    City terrain or inconsistent bases require explicit ``terrain='flat'``
    (the bounds' zmin or lowest base) or ``FlatTerrain(elevation=...)``. Explicit
    bounds use global coordinates, including any supported input translation.

    DTCC transforms are absolute local-to-global translations. Identity
    inherits the enclosing frame, repeated equal translations apply once, and
    conflicting declarations raise. Rotations, scales and shears are rejected.
    Other city objects are omitted and listed in result metadata.
    """
    for value, expected, name in ((condition, WindCondition, "condition"), (grid, GridSpec, "grid"),
                                  (solver, SolverOptions, "solver")):
        if not isinstance(value, expected):
            raise TypeError(f"{name} must be a {expected.__name__}")
    geometry = extract_city(city, height_policy)
    prepared = prepare_config(geometry, condition, grid, terrain)
    native_condition = _qes.WindCondition()
    for name in ("speed", "direction", "reference_height"):
        setattr(native_condition, name, getattr(condition, name))
    native_solver = _qes.SolverOptions()
    native_solver.tolerance, native_solver.max_iterations = solver.tolerance, solver.max_iterations
    runner = _qes.WindRunner()
    try:
        runner.prepare(prepared.grid, prepared.model, **prepared.arrays)
        native = runner.solve(native_condition, native_solver)
    finally:
        # Arrays already own their storage. A retained Python exception's
        # traceback must not retain the much larger prepared native domain.
        del runner
    diagnostics = SolveDiagnostics(**native["diagnostics"])
    if not diagnostics.converged:
        if solver.raise_on_nonconvergence:
            raise ConvergenceError(diagnostics)
        get_python_logger("dtcc-qes").warning(str(ConvergenceError(diagnostics)))
    model_names = ("wall_roughness", "rooftop_flag", "upwind_cavity_flag", "street_canyon_flag",
                   "street_intersection_flag", "wake_flag", "high_rise_flag", "sidewall_flag")
    metadata = dict(
        domain=prepared.domain, condition=asdict(condition), solver=asdict(solver), terrain=prepared.terrain,
        effective_condition={name: float(np.float32(value)) for name, value in asdict(condition).items()},
        height_policy=height_policy, ignored_city_objects=geometry.ignored_objects,
        model=dict(backend="serial CPU", log_law_flag=0, mesh_type_flag=0, halo_x=0, halo_y=0,
                   boundary_layer="neutral logarithmic", sensor=(prepared.model.sensor_x, prepared.model.sensor_y),
                   timestamp="2020-01-01T00:00:00", **{name: getattr(prepared.model, name) for name in model_names}),
        versions=dict(dtcc_qes=__version__, qes=dict(version=_qes.qes_version, revision=_qes.qes_revision),
                      dtcc_core=_dtcc_version()),
        buildings=[dict(native_id=i, source_id=source_id, height=height, height_source=source,
                        original_base_range=base_range, redundant_vertices_removed=removed)
                   for i, (source_id, height, source, base_range, removed) in enumerate(zip(
                       geometry.source_ids, geometry.heights, geometry.height_sources,
                       geometry.base_ranges, geometry.removed_vertices))],
        simplifications=["LOD0 footprints extruded to constant heights", "flat ground", "stair-step cells"],
        transform_policy="absolute translations applied once; identity inherits enclosing frame",
        coordinates="local metres; add origin to recover the input global frame",
        dtcc_cell_order="y, x, z fastest (VolumeGrid.coordinates meshgrid xy)",
    )
    return WindResult(native["velocity"], native["x"], native["y"], native["z"], native["cell_flags"],
                      prepared.origin, geometry.crs, prepared.resolution, diagnostics, metadata)
