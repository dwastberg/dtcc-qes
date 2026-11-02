"""Run one RunSpec through dtcc-qes and record the probe values with provenance.

A record (``<key>.json``) holds the spec, provenance, grid, solver diagnostics,
timings and the probe values; the probe-height plane goes to ``<key>.npz``.
Monitor runs add the probe-speed history at every checkpoint.
"""

import hashlib
import json
import os
import platform
import resource
import subprocess
import time
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely

from . import ROOT, CASE_D_XLS, CASE_E_XLS, case_d, case_e, cityutil, grids, inflow, sampling, tables
from .runspec import FINE_TOP, MAX_ASPECT, RunSpec

RECORD_SCHEMA = "aij-run-v1"
REPO = ROOT.parent
# Modules whose code changes a run's output; report and metrics code is deliberately excluded.
RUN_MODULES = ("case_d", "case_e", "cityutil", "conventions", "dxf", "grids", "inflow", "prisms",
               "runner", "runspec", "sampling", "tables")


def _sha256_files(paths) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(Path(path).name).encode())
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def fingerprint() -> str:
    """Hash of the code that determines a run: the validation modules and the dtcc_qes package."""
    import dtcc_qes
    package = Path(dtcc_qes.__file__).parent
    paths = [ROOT / "aij" / f"{name}.py" for name in RUN_MODULES]
    paths += sorted(package.glob("*.py")) + sorted(package.glob("_qes*.so")) + sorted(package.glob("_qes*.pyd"))
    return _sha256_files(paths)


def git_state() -> dict:
    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()
    return dict(revision=git("rev-parse", "HEAD"),
                dirty=bool(git("status", "--porcelain", "--", "src", "CMakeLists.txt", "pyproject.toml")))


@lru_cache(maxsize=8)
def city(case: str, state: str = "-", variant: str = "exact"):
    """The City of a case in the dtcc-qes input contract (``cityutil.qes_city``)."""
    if case == "D":
        return cityutil.qes_city(case_d.build_case_d().city)
    if variant == "slabs_filled":
        return cityutil.qes_city(cityutil.fill_slabs(case_e.build_case_e(state).city))
    build = case_e.build_case_e if variant == "exact" else case_e.build_case_e_qes
    return cityutil.qes_city(build(state).city)


def city_digest(city_) -> str:
    """Hash of the footprints and heights dtcc-qes receives (ids, exact WKB, heights)."""
    digest = hashlib.sha256()
    for id_, polygon, height in sorted(cityutil.footprints(city_), key=lambda row: row[0]):
        digest.update(id_.encode())
        digest.update(shapely.to_wkb(polygon))
        digest.update(np.float64(height).tobytes())
    return digest.hexdigest()


def inputs(spec: RunSpec) -> dict:
    """Everything wind.run needs for ``spec``, plus the probes and the reference speed."""
    from dtcc_qes import wind
    city_ = city(spec.case, spec.state, spec.city)
    rows = cityutil.footprints(city_)
    polygons, heights = [p for _, p, _ in rows], np.array([h for _, _, h in rows])
    data = tables.load_inflow_d() if spec.case == "D" else tables.load_inflow_e()
    probes = tables.load_points_d() if spec.case == "D" else tables.load_points_e()
    options = {}
    if spec.inflow in ("measured", "canopy"):
        options.update(interpolation=spec.interpolation, roughness_length=spec.ground_roughness)
    if spec.inflow == "canopy":
        options.update(canopy_roughness=spec.canopy_roughness, blending_height=spec.blending_height)
    profile = inflow.profile(data, spec.inflow, spec.direction, **options)
    # K is normalised by the approach flow; it differs from the run's inflow only for "canopy".
    normaliser = inflow.approach_profile(data, spec.inflow, spec.direction, **options)
    # Case E states share one vertical grid (that of "after"), so they differ only in the buildings.
    top_heights = heights if spec.case == "D" else [60.0]
    top = grids.required_top(top_heights, spec.clearance, data.reference["height"])
    layer = spec.probe_layer
    faces = grids.vertical_faces(layer, top, FINE_TOP[spec.case],
                                 growth=grids.GROWTH if spec.vertical == "stretched" else None,
                                 max_dz=MAX_ASPECT * layer)
    solver = dict(tolerance=spec.tolerance, max_iterations=spec.max_iterations, precision=spec.precision)
    if spec.monitor:
        xy = probes.xyz[:, :2]
        region = (float(xy[:, 0].min() - 10), float(xy[:, 0].max() + 10),
                  float(xy[:, 1].min() - 10), float(xy[:, 1].max() + 10))
        receptors = tuple(wind.Receptor(f"p{i}", float(x), float(y), float(z), required=False)
                          for i, (x, y, z) in zip(probes.ids, probes.xyz))
        checkpoints = spec.max_iterations // spec.checkpoint_interval + 2
        solver.update(max_solve_seconds=86400.0, checkpoint_interval=spec.checkpoint_interval,
                      monitor=wind.MonitorSpec(region=region, heights=(), receptors=receptors, frame="world",
                                               history_limit=checkpoints, memory_limit_bytes=512 * 2 ** 20))
    return dict(
        city=city_, polygons=polygons, probes=probes, profile=profile,
        reference_speed=inflow.reference_speed(normaliser),
        run=dict(resolution=spec.resolution, bounds=grids.horizontal_bounds(spec.case, polygons, spec.padding),
                 vertical_grid=wind.VerticalGrid.from_faces(faces), solver=wind.Solver(**solver),
                 turbulence=wind.Turbulence() if spec.turbulence else None,
                 parameterizations=spec.parameterization_spec(),
                 footprints=None if spec.min_detail is None else wind.Footprints(
                     min_detail=spec.min_detail, exposed_faces=True, fallback="error"),
                 vertical_clearance=spec.clearance, max_cells=spec.max_cells))


def _peak_rss() -> int:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if platform.system() == "Darwin" else rss * 1024)


def _history(record, reference_speed) -> dict:
    checkpoints = record["checkpoint_history"]
    iterations = [c["iteration"] for c in checkpoints]
    k = [[float(np.linalg.norm(r["sample"]["velocity"])) / reference_speed if r["sample"]["valid"] else None
          for r in c["receptors"]] for c in checkpoints]
    return dict(iterations=iterations, K=k, truncated=bool(record.get("history_truncated")))


def run(spec: RunSpec) -> tuple[dict, dict]:
    """Solve ``spec``; return the JSON record and the probe-height plane arrays."""
    from dtcc_qes import _qes, wind
    started = time.perf_counter()
    args = inputs(spec)
    result = wind.run(args["city"], args["profile"], **args["run"])
    wall = time.perf_counter() - started
    probes, uref = args["probes"], args["reference_speed"]
    sample = sampling.probe_sample(result, probes.xyz)
    wall_distance = sampling.wall_distance(probes.xyz[:, :2], args["polygons"])
    probe = dict(ids=probes.ids, xyz=probes.xyz, wall_distance=wall_distance,
                 velocity=sample["velocity"], speed=sample["speed"], K=sample["speed"] / uref,
                 K_min=sample["speed_min"] / uref, K_max=sample["speed_max"] / uref,
                 method=sample["method"], sampled=sample["sampled"], radius=sample["radius"])
    if "k" in sample:
        probe.update(k=sample["k"], K_scalar=np.sqrt(sample["speed"] ** 2 + 2 * sample["k"]) / uref)
    metadata = result.metadata
    footprints = metadata.get("footprints")
    record = dict(
        schema=RECORD_SCHEMA, key=spec.key, name=spec.name, spec=spec.to_dict(), fingerprint=fingerprint(),
        provenance=dict(git=git_state(), versions=metadata["versions"], environment=result.solver["environment"],
                        solver_policy_revision=_qes.solver_policy_revision, model=metadata["model"],
                        city_digest=city_digest(args["city"]),
                        xls_sha256=cityutil.sha256(CASE_D_XLS if spec.case == "D" else CASE_E_XLS),
                        omp_num_threads=os.environ.get("OMP_NUM_THREADS"), host=platform.node()),
        grid=dict(shape=list(result.velocity.shape[:3]), cells=int(np.prod(result.velocity.shape[:3])),
                  origin=list(result.origin), resolution=float(result.resolution),
                  z_faces=np.asarray(result.z_faces).tolist(), effective_bounds=metadata["domain"]["effective_bounds"]),
        profile=dict(kind=spec.inflow, reference_height=args["profile"].reference_height,
                     reference_speed=uref, roughness_length=args["profile"].roughness_length),
        diagnostics=asdict(result.diagnostics), qualification=result.qualification,
        timings=metadata["timings"], wall_seconds=wall,
        footprints=None if footprints is None else dict(counts=footprints["counts"], fallbacks=footprints["fallbacks"]),
        ignored_city_objects=metadata["ignored_city_objects"],
        probes=probe)
    if spec.monitor:
        record["history"] = _history(result.solver["record"], uref)
    plane = result.sample(grids.PROBE_HEIGHT, "nearest")
    arrays = dict(x=plane.x.astype(np.float64) + result.origin[0], y=plane.y.astype(np.float64) + result.origin[1],
                  velocity=plane.velocity.astype(np.float32), valid=plane.valid, reference_speed=np.float64(uref),
                  sampled_height=np.float64(plane.sampled_height))
    if plane.stress is not None:
        stress = plane.stress
        arrays["k"] = (0.5 * (stress[..., 0] + stress[..., 3] + stress[..., 5])).astype(np.float32)
    record["peak_rss_bytes"] = _peak_rss()
    return record, arrays


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write(record: dict, arrays: dict, directory: Path) -> Path:
    """Write ``<key>.npz`` then ``<key>.json`` atomically; the JSON marks the run complete."""
    directory.mkdir(parents=True, exist_ok=True)
    key = record["key"]
    tmp = directory / f".{key}.npz.tmp"
    with open(tmp, "wb") as handle:
        np.savez_compressed(handle, **arrays)
    os.replace(tmp, directory / f"{key}.npz")
    tmp = directory / f".{key}.json.tmp"
    tmp.write_text(json.dumps(_clean(record), indent=1, allow_nan=False) + "\n")
    os.replace(tmp, directory / f"{key}.json")
    return directory / f"{key}.json"


def load(directory: Path, key: str) -> dict | None:
    path = Path(directory) / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None
