"""Check that a native change leaves every wind and turbulence output bitwise unchanged.

Builds the extension from a baseline git revision and from a candidate (the
working tree by default) with identical CMake settings, runs one fixed case
matrix against each build in a separate subprocess, and compares every output
array and diagnostic bitwise. ``--binaries`` also compares the object files and
extension modules byte for byte, which only holds for pure moves.

Example::

    uv run --frozen python tools/compare_native_builds.py --baseline HEAD~1 --backends openmp serial

The case matrix covers the public ``wind.run`` paths (float32/float64, uniform,
explicit and automatic vertical grids, both mixing-length methods, nonconverged
and calm runs) and the native runner directly: every supported combination of
the parameterization flags and one runner reused for several directions, which
pins any state carried between solves. ``wake_flag=0`` is excluded because it
leaves sidewall and rooftop inputs undefined.
"""

from __future__ import annotations

import argparse
import filecmp
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {"openmp": "ON", "serial": "OFF"}
NATIVE_TARGETS = ("qesutil", "qeswindscore", "qesbridge", "_qes")


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def export_tree(ref, work_dir):
    """Export a committed tree once per commit; the submodule is not needed to build."""
    commit = run(["git", "-C", str(ROOT), "rev-parse", "--verify", ref + "^{commit}"],
                 capture_output=True).stdout.strip()
    dest = work_dir / "trees" / commit
    if not (dest / ".exported").exists():
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        archive = subprocess.Popen(["git", "-C", str(ROOT), "archive", commit], stdout=subprocess.PIPE)
        run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout)
        if archive.wait() != 0:
            raise RuntimeError(f"git archive of {ref} failed")
        (dest / ".exported").write_text(commit + "\n")
    return dest, commit[:12]


def build(tree, build_dir, backend):
    run(["cmake", "-S", str(tree), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release",
         f"-DPython_EXECUTABLE={sys.executable}", f"-DDTCC_QES_OPENMP={BACKENDS[backend]}"],
        capture_output=True)
    run(["cmake", "--build", str(build_dir), "--target", "_qes", "-j", str(os.cpu_count() or 2)],
        capture_output=True)
    modules = sorted(build_dir.glob("_qes*.so")) + sorted(build_dir.glob("_qes*.pyd"))
    if len(modules) != 1:
        raise RuntimeError(f"Expected one extension module in {build_dir}")
    return modules[0]


def stage_package(tree, module, pkg_dir):
    shutil.rmtree(pkg_dir, ignore_errors=True)
    shutil.copytree(tree / "src/dtcc_qes", pkg_dir / "dtcc_qes",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_qes*.so", "_qes*.pyd"))
    shutil.copy2(module, pkg_dir / "dtcc_qes" / module.name)


def objects(build_dir):
    found = {}
    for target in NATIVE_TARGETS:
        # Targets defined in subdirectories keep their objects below that directory.
        for target_dir in build_dir.rglob(f"{target}.dir"):
            for path in target_dir.rglob("*.o"):
                if (target, path.name) in found:
                    raise RuntimeError(f"Ambiguous object name {target}/{path.name}")
                found[(target, path.name)] = path
    return found


def compare_binaries(a, b, module_a, module_b):
    """Object paths depend on source layout, so match objects by target and file name."""
    oa, ob = objects(a), objects(b)
    problems = [f"object set differs: {sorted(set(oa) ^ set(ob))}"] if set(oa) != set(ob) else []
    problems += [f"object differs: {k[0]}/{k[1]}" for k in sorted(set(oa) & set(ob))
                 if not filecmp.cmp(oa[k], ob[k], shallow=False)]
    if not filecmp.cmp(module_a, module_b, shallow=False):
        problems.append(f"extension module differs: {module_a.name}")
    return problems, len(oa)


def compare_results(a, b):
    """Return the keys whose values differ; arrays must match dtype, shape and bytes."""
    with np.load(a) as x, np.load(b) as y:
        keys = set(x.files) - {"_module"}
        other = set(y.files) - {"_module"}
        problems = [f"only in one result: {k}" for k in sorted(keys ^ other)]
        for key in sorted(keys & other):
            u, v = x[key], y[key]
            if u.dtype != v.dtype or u.shape != v.shape or u.tobytes() != v.tobytes():
                problems.append(f"differs: {key}")
        return problems, len(keys)


# --------------------------------------------------------------------------
# Case matrix (runs inside a subprocess against one staged package)
# --------------------------------------------------------------------------

BLOCKS = [(20, 20, 12, 30, 18), (44, 20, 10, 12, 9), (44, 40, 16, 10, 24),
          (70, 18, 8, 34, 12), (24, 62, 40, 8, 15), (80, 60, 10, 10, 30)]
NATIVE_BLOCKS = [(14, 12, 10, 16, 10), (32, 12, 8, 8, 6), (32, 26, 12, 8, 14)]


def make_city(blocks):
    from dtcc_core.model import Building, City, GeometryType, Surface
    city = City()
    for i, (x, y, w, d, h) in enumerate(blocks):
        building = Building(id=str(i))
        building.measured_height = h
        ring = [(x, y), (x, y + d), (x + w, y + d), (x + w, y)]  # clockwise
        building.add_geometry(Surface(vertices=np.c_[np.asarray(ring, float), np.zeros(4)]), GeometryType.LOD0)
        city.add_building(building)
    return city


def store(out, name, value):
    if isinstance(value, dict):
        arrays = {k: v for k, v in value.items() if isinstance(v, np.ndarray)}
        for key, array in arrays.items():
            out[f"{name}/{key}"] = array
        rest = {k: v for k, v in value.items() if k not in arrays and not isinstance(v, dict)}
        out[f"{name}/scalars"] = np.array(json.dumps(rest, sort_keys=True, default=repr))
        for key, nested in value.items():
            if isinstance(nested, dict):
                store(out, f"{name}/{key}", nested)
    else:
        out[name] = np.asarray(value)


def public_runs():
    from dtcc_qes import wind
    from dtcc_qes.turbulence import Turbulence
    from dtcc_qes.vertical_grid import VerticalGrid
    small = make_city([(30, 25, 10, 10, 8)])
    city = make_city(BLOCKS)
    common = dict(reference_height=10.0, roughness_length=0.1, resolution=2.0, bounds=(0, 0, 0, 110, 90, 60))
    tall = {**common, "bounds": (0, 0, 0, 110, 90, 72.5)}
    stretched = np.r_[np.arange(0, 6, 0.5), np.arange(6, 20, 1.0), np.arange(20, 73, 2.5)]
    runs = {
        "flat": (make_city([]), 5.0, 270.0, dict(bounds=(0, 0, 0, 80, 60, 40))),
        "flat_turbulence": (make_city([]), 5.0, 270.0, dict(bounds=(0, 0, 0, 80, 60, 40), turbulence=True)),
        "one_building": (small, 5.0, 270.0, dict(bounds=(0, 0, 0, 80, 60, 40))),
        "one_building_turbulence": (small, 5.0, 270.0, dict(bounds=(0, 0, 0, 80, 60, 40), turbulence=True)),
        "calm": (city, 0.0, 90.0, common),
        "roughness_reference": (city, 6.0, 135.0, {**common, "roughness_length": 0.5, "reference_height": 25.0}),
        "float64": (city, 5.0, 33.0, {**common, "solver_precision": "float64"}),
        "nonconverged": (city, 7.0, 120.0, {**common, "max_iterations": 40}),
        "turbulence_height": (city, 5.0, 200.0, {**common, "turbulence": Turbulence("height")}),
        "turbulence_wall": (city, 5.0, 200.0, {**common, "turbulence": Turbulence("wall_distance")}),
        "automatic_grid": (city, 5.0, 300.0, {**common, "vertical_grid": VerticalGrid.auto()}),
        "uniform_explicit_grid": (city, 5.0, 300.0,
                                  {**common, "vertical_grid": VerticalGrid.from_faces(np.arange(0, 62, 2.0))}),
        "stretched_turbulence": (city, 4.0, 10.0,
                                 {**tall, "vertical_grid": VerticalGrid.from_faces(stretched), "turbulence": True}),
        "fine": (city, 5.0, 45.0, {**common, "resolution": 1.0, "bounds": (0, 0, 0, 110, 90, 40)}),
    }
    for direction in (0.0, 90.0, 180.0, 270.0, 33.0, 247.5):
        runs[f"direction_{direction:g}"] = (city, 5.0, direction, common)
    for name, (c, speed, direction, options) in runs.items():
        r = wind.run(c, speed, direction, **options)
        result = {k: getattr(r, k) for k in ("velocity", "x", "y", "z", "cell_flags", "z_faces") if getattr(r, k) is not None}
        result["diagnostics"] = dict(r.diagnostics.__dict__)
        result["metadata"] = r.metadata
        if r.turbulence is not None:
            result["turbulence"] = dict(r.turbulence.__dict__)
        yield f"public/{name}", result


def native_inputs(blocks, nx=50, ny=40, nz=20, cell=2.0):
    from dtcc_qes import _qes
    grid = _qes.GridConfig()
    grid.nx, grid.ny, grid.nz, grid.cell_size = nx, ny, nz, cell
    vertices, offsets = [], [0]
    for x, y, w, d, _ in blocks:
        vertices += [(x, y), (x, y + d), (x + w, y + d), (x + w, y), (x, y)]
        offsets.append(len(vertices))
    arrays = dict(vertices=np.asarray(vertices, np.float64).reshape(-1, 2), offsets=np.asarray(offsets, np.int64),
                  heights=np.asarray([b[4] for b in blocks], np.float64),
                  base_heights=np.zeros(len(blocks)), ids=np.arange(len(blocks), dtype=np.int64))
    return grid, arrays


def native_model(**flags):
    from dtcc_qes import _qes
    model = _qes.ModelSettings()
    model.sensor_x, model.sensor_y = 5.0, 5.0
    for key, value in flags.items():
        setattr(model, key, value)
    return model


def native_solve(runner, speed, direction, iterations=60, precision="float32"):
    from dtcc_qes import _qes
    condition = _qes.WindCondition()
    condition.speed, condition.direction, condition.reference_height = speed, direction, 10.0
    options = _qes.SolverOptions()
    options.max_iterations, options.precision = iterations, precision
    return runner.solve(condition, options)


def native_runs():
    from dtcc_qes import _qes
    grid, arrays = native_inputs(NATIVE_BLOCKS)
    flags = itertools.product((0, 1, 2), (0, 1, 2, 3), (0, 1), (1, 2), (0, 1), (0, 1))
    for rooftop, cavity, canyon, wake, high_rise, sidewall in flags:
        model = native_model(rooftop_flag=rooftop, upwind_cavity_flag=cavity, street_canyon_flag=canyon,
                             wake_flag=wake, high_rise_flag=high_rise, sidewall_flag=sidewall)
        name = f"r{rooftop}c{cavity}s{canyon}w{wake}h{high_rise}d{sidewall}"
        for direction in (270.0, 27.0):  # aligned with the canyon, and oblique
            runner = _qes.WindRunner()
            runner.prepare(grid, model, **arrays)
            yield f"native/flags/{name}/{direction:g}", native_solve(runner, 5.0, direction)
    for roughness in (0.001, 0.05):
        runner = _qes.WindRunner()
        runner.prepare(grid, native_model(wall_roughness=roughness, rooftop_flag=2), **arrays)
        yield f"native/wall_roughness/{roughness:g}", native_solve(runner, 5.0, 315.0)
    # One runner, several directions: pins every piece of state carried between solves.
    for rooftop in (1, 2):
        runner = _qes.WindRunner()
        runner.prepare(grid, native_model(rooftop_flag=rooftop), **arrays)
        for step, direction in enumerate((270.0, 45.0, 33.0, 300.0, 33.0, 225.0, 45.0)):
            yield f"native/reuse/r{rooftop}/{step}", native_solve(runner, 5.0, direction)
        yield f"native/reuse/r{rooftop}/float64", native_solve(runner, 5.0, 33.0, precision="float64")
    turbulence = _qes.TurbulenceSettings()
    turbulence.enabled = True
    for method in (0, 1):
        turbulence.mixing_length_method = method
        runner = _qes.WindRunner()
        runner.prepare(grid, native_model(), **arrays, dz_layers=np.full(grid.nz, 2.0), turbulence=turbulence)
        for step, direction in enumerate((250.0, 160.0)):
            yield f"native/turbulence/m{method}/{step}", native_solve(runner, 5.0, direction)


def run_cases(output):
    from dtcc_qes import _qes
    out = {"_module": np.array(_qes.__file__), "qes_revision": np.array(_qes.qes_revision)}
    count = 0
    for name, result in itertools.chain(public_runs(), native_runs()):
        store(out, name, result)
        count += 1
    np.savez(output, **out)
    print(json.dumps(dict(cases=count, module=_qes.__file__)))


def evaluate(pkg_dir, output, threads):
    env = {**os.environ, "PYTHONPATH": str(pkg_dir), "OMP_NUM_THREADS": str(threads), "OMP_DYNAMIC": "FALSE"}
    completed = run([sys.executable, str(Path(__file__).resolve()), "--run-cases", str(output)],
                    capture_output=True, env=env, cwd=str(pkg_dir))
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    if not Path(report["module"]).resolve().is_relative_to(pkg_dir.resolve()):
        raise RuntimeError(f"Cases imported {report['module']} instead of the staged package")
    return report["cases"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--baseline", default="HEAD", help="baseline git revision (default: %(default)s)")
    ap.add_argument("--candidate", default=None, help="candidate git revision (default: working tree)")
    ap.add_argument("--backends", nargs="+", choices=sorted(BACKENDS), default=["openmp", "serial"])
    ap.add_argument("--binaries", action="store_true", help="also require byte-identical objects and modules")
    ap.add_argument("--threads", type=int, default=4, help="OpenMP team size for the case runs")
    ap.add_argument("--work-dir", type=Path, default=ROOT / "build/compare-native")
    ap.add_argument("--run-cases", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.run_cases:
        run_cases(args.run_cases)
        return
    work = args.work_dir.resolve()
    baseline, baseline_id = export_tree(args.baseline, work)
    candidate, candidate_id = export_tree(args.candidate, work) if args.candidate else (ROOT, "worktree")
    failed = False
    for backend in args.backends:
        built = {}
        for label, tree, tree_id in (("baseline", baseline, baseline_id), ("candidate", candidate, candidate_id)):
            build_dir = work / "builds" / f"{tree_id}-{backend}"
            module = build(tree, build_dir, backend)
            pkg = work / "packages" / f"{tree_id}-{backend}"
            stage_package(tree, module, pkg)
            result = work / "results" / f"{tree_id}-{backend}.npz"
            result.parent.mkdir(parents=True, exist_ok=True)
            cases = evaluate(pkg, result, args.threads)
            built[label] = (build_dir, module, result)
        problems, records = compare_results(built["baseline"][2], built["candidate"][2])
        print(f"{backend}: {cases} cases, {records} records compared, {len(problems)} differences")
        if args.binaries:
            binary_problems, count = compare_binaries(built["baseline"][0], built["candidate"][0],
                                                      built["baseline"][1], built["candidate"][1])
            print(f"{backend}: {count} objects and the extension module compared, {len(binary_problems)} differences")
            problems += binary_problems
        for problem in problems[:50]:
            print("  " + problem)
        failed = failed or bool(problems)
    if failed:
        raise SystemExit(f"Native builds differ from baseline {baseline_id}")
    print(f"Bitwise identical to baseline {baseline_id}")


if __name__ == "__main__":
    main()
