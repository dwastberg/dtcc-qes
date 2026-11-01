"""Reproducible numerical verification, scaling and profile cost measurements.

No physical validation claim. Acceptance thresholds are specified here before
execution; reports preserve failures. Uses a synthetic, fixed 10x10x8 m block.
"""
import argparse
import hashlib
import platform
import json
import logging
from pathlib import Path
import re
import subprocess
import time

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind, _qes

# Absolute normalized-velocity tolerances at the 5 m/s baseline. These assess
# numerical scaling/discretization only; no physical comparison threshold exists.
SCALING_ATOL = 2e-3
TABULATION_ATOL = 2e-3


def city_with_block():
    city = City()
    block = Building(id="profile-verification-block")
    block.measured_height = 8.
    block.add_geometry(Surface(vertices=np.array([[30,25,0],[30,35,0],[40,35,0],[40,25,0]], dtype=float)), GeometryType.LOD0)
    city.add_building(block)
    return city


class Timings(logging.Handler):
    def __init__(self):
        super().__init__()
        self.expect_elapsed = False
        self.seconds = []

    def emit(self, record):
        message = record.getMessage()
        if "Applying Wind Profile" in message:
            self.expect_elapsed = True
        elif self.expect_elapsed and "elapsed time:" in message:
            self.seconds.append(float(re.search(r"elapsed time:\s*([\d.eE+-]+)", message)[1]))
            self.expect_elapsed = False


def verify(repeats=5, tolerance=1e-5):
    logger = get_python_logger("dtcc-qes")
    old = logger.handlers[:], logger.level, logger.propagate
    timings = Timings()
    logger.handlers, logger.propagate = [timings], False
    logger.setLevel(logging.DEBUG)
    try:
        root = Path(__file__).resolve().parents[1]
        digest = hashlib.sha256()
        sources = [p for p in (root / "src").rglob("*") if p.suffix in (".py", ".cpp", ".h")]
        sources += [root / "CMakeLists.txt", root / "src/qes_core/CMakeLists.txt",
                    root / "pyproject.toml", Path(__file__).resolve()]
        for source in sorted(sources):
            digest.update(str(source.relative_to(root)).encode() + b"\0" + source.read_bytes())
        report = dict(implementation_sha256=digest.hexdigest(), python=platform.python_version(),
            platform=platform.platform(), numpy=np.__version__, schema_version=1, scope="numerical verification; independent physical validation pending",
            source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            openmp_enabled=_qes.openmp_enabled, backend=_qes.cpu_backend,
            compiler=dict(id=_qes.compiler_id, version=_qes.compiler_version),
            acceptance=dict(scaling_normalized_vector_atol=SCALING_ATOL, tabulation_vector_atol=TABULATION_ATOL,
                            unit="m/s at baseline amplitude", physical_validation="not assessed"), cases=[], costs=[])
        profiles = [wind.LogProfile(5,270), wind.UniformProfile(5,270),
            wind.PowerLawProfile(5,270,10,.22),
            wind.MeasuredProfile([1,5,10,20,40],[1.5,3.5,5,6,7],direction=270,reference_height=10, below="log")]
        grid = dict(resolution=2., bounds=(0,0,0,80,60,40))
        report["grid"] = dict(grid, uniform_shape=[20,30,40], nonuniform_faces=[0,1,2,3,5,8,12,18,26,40])
        report["geometry"] = dict(block_bounds=[30,25,0,40,35,8], ground="flat", sampling="all fluid cell centres")
        for geometry in ("empty", "block"):
            city = City() if geometry == "empty" else city_with_block()
            for precision in ("float32", "float64"):
                for nonuniform in (False, True):
                    options = dict(grid, solver=wind.Solver(tolerance=tolerance, max_iterations=2000, precision=precision))
                    if nonuniform:
                        options["vertical_grid"] = wind.VerticalGrid.from_faces([0,1,2,3,5,8,12,18,26,40])
                    for p in profiles:
                        base = wind.run(city, profile=p, **options)
                        fluid = (base.cell_flags != 0) & (base.cell_flags != 2)
                        errors, comparisons = [], []
                        for factor in (.5, 2., 3.):
                            changed = wind.run(city, profile=p.scaled(factor), **options)
                            error = float(np.max(np.abs(changed.velocity[fluid]/factor-base.velocity[fluid])))
                            errors.append(error)
                            comparisons.append(dict(scale=factor, max_vector_component_error=error,
                                converged=changed.diagnostics.converged,
                                iterations=changed.diagnostics.iterations,
                                multiplier_change=changed.diagnostics.max_lagrange_multiplier_change,
                                masks_equal=bool(np.array_equal(base.cell_flags, changed.cell_flags))))
                        item = dict(kind=p.kind, profile=p.to_dict(), geometry=geometry,
                            precision=precision, nonuniform=nonuniform, reference=p.reference,
                            scales=[.5,2,3], scaling_errors=errors, scaling_comparisons=comparisons,
                            scaling_pass=max(errors) <= SCALING_ATOL, converged=base.diagnostics.converged,
                            conservative_divergence=base.diagnostics.max_divergence)
                        if p.kind == "log":
                            legacy = wind.run(city, **options, speed=5, direction=270)
                            item["legacy_bitwise_equal"] = bool(np.array_equal(base.velocity,legacy.velocity))
                            item["legacy_converged"] = legacy.diagnostics.converged
                        if p.kind == "power_law":
                            # Independent dense knots: retain the declared reference,
                            # but never insert solver supports to force exact equality.
                            h = np.unique(np.r_[np.linspace(.1,40,2001),10.])
                            uv = p.evaluate(h)
                            table = wind.MeasuredProfile.from_components(h,uv[:,0],uv[:,1],reference_height=10)
                            table_result = wind.run(city,profile=table,**options)
                            error = float(np.max(np.abs(base.velocity[fluid]-table_result.velocity[fluid])))
                            item.update(tabulation_error=error, tabulation_pass=error <= TABULATION_ATOL,
                                tabulation_converged=table_result.diagnostics.converged,
                                tabulation_masks_equal=bool(np.array_equal(base.cell_flags,table_result.cell_flags)),
                                tabulation_knots=len(h))
                        report["cases"].append(item)
        city = city_with_block()
        # The internal timer covers profile field construction, excludes allocation,
        # and precedes building models. Wall time covers the complete public call.
        for p in profiles:
            seconds, profile_seconds, python_seconds = [], [], []
            wind.run(city, profile=p, **grid)  # warm
            original_evaluate = type(p).evaluate
            evaluations = []
            def timed_evaluate(self, *args, **kwargs):
                start = time.perf_counter()
                try:
                    return original_evaluate(self, *args, **kwargs)
                finally:
                    evaluations.append(time.perf_counter()-start)
            type(p).evaluate = timed_evaluate
            try:
                for _ in range(repeats):
                    evaluations.clear()
                    start = time.perf_counter()
                    wind.run(city, profile=p, **grid)
                    seconds.append(time.perf_counter()-start)
                    python_seconds.append(sum(evaluations))
                    profile_seconds.append(timings.seconds[-1])
            finally:
                type(p).evaluate = original_evaluate
            full, native, python = map(float, (np.median(seconds), np.median(profile_seconds), np.median(python_seconds)))
            report["costs"].append(dict(kind=p.kind,repeats=repeats,public_call_median_seconds=full,
                native_field_copy_median_seconds=native,python_evaluation_median_seconds=python,
                profile_fraction_of_public_call=(native+python)/full))
        report["numerical_comparisons_passed"] = all(
            c["scaling_pass"] and c.get("tabulation_pass", True) and c.get("legacy_bitwise_equal", True)
            and all(s["masks_equal"] for s in c["scaling_comparisons"])
            and c.get("tabulation_masks_equal", True) for c in report["cases"])
        report["all_comparisons_converged"] = all(
            c["converged"] and c.get("legacy_converged", True) and c.get("tabulation_converged", True)
            and all(s["converged"] for s in c["scaling_comparisons"]) for c in report["cases"])
        report["passed"] = report["numerical_comparisons_passed"] and report["all_comparisons_converged"]
        return report
    finally:
        logger.handlers, logger.level, logger.propagate = old


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--tolerance", type=float, default=1e-5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if not np.isfinite(args.tolerance) or args.tolerance < np.finfo(np.float32).eps:
        parser.error("--tolerance must be finite and at least float32 epsilon")
    report = verify(args.repeats, args.tolerance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(f"{args.output}: passed={report['passed']}")
    raise SystemExit(0 if report["passed"] else 1)
