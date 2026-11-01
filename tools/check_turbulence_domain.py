"""Measure lower-grid sensitivity when a turbulence preview needs regeneration.

The wind-only 35 m endpoint cannot contain the requested 40 m fine band. The
first feasible turbulence grid is compared with a taller regenerated grid and
with a taller grid retaining every base operand. This is a focused mean-wind
control, not the Task 9 turbulence or physical gust validation gate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil

import numpy as np
from dtcc_qes import _qes, wind
from dtcc_qes.vertical_grid import effective_faces

from run_auto_grid_controls import make_city, rectangles

ROOT = Path(__file__).resolve().parents[1]


def error_metrics(ka,kb):
    """Absolute ΔK uses Uref; relative peaks use the comparison reference kb."""
    delta=np.abs(np.asarray(kb)-np.asarray(ka))
    reference=float(np.max(kb))
    peak=abs(float(np.max(kb)-np.max(ka)))/reference if reference>0 else None
    return dict(p95_abs_delta_K=float(np.quantile(delta,.95)),max_abs_delta_K=float(delta.max()),
        peak_relative_difference=peak,
        passed=bool(np.quantile(delta,.95)<=.05 and peak is not None and peak<=.05))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rects = [(*r[:4],15.) for r in rectangles("array")]
    city = make_city(rects)
    spec = wind.VerticalGrid.auto(fine_region_height=40)
    base = wind.preview_grid(city, vertical_grid=spec, turbulence=wind.Turbulence())
    vertical = base.domain["vertical_grid"]
    layers = np.diff(vertical["planned_faces"])
    np.testing.assert_array_equal(layers.astype(np.float32),base.solver_dz)
    record = base.domain["turbulence"]
    assert not record["lower_layers_preserved"]
    bounds = base.domain["effective_bounds"]
    target = record["regeneration"]["generated_top"] + 20
    preserved = list(layers)
    # Stop at or above the control top using the original final operand.
    while float(effective_faces(preserved)[-1]) < target:
        if len(preserved) >= 10000:
            raise ValueError("Control extension exceeds 10000 layers")
        preserved.append(layers[-1])
    preserved = np.asarray(preserved)
    np.testing.assert_array_equal(effective_faces(preserved)[:len(base.z_faces)],base.z_faces)
    control_top = float(np.cumsum(preserved)[-1])
    tall = wind.preview_grid(city, bounds=(*bounds[:5],control_top), vertical_grid=spec, turbulence=wind.Turbulence())
    tall_layers = np.diff(tall.domain["vertical_grid"]["planned_faces"])
    count = vertical["effective_settings"]["fine_layer_count"]
    np.testing.assert_array_equal(tall.solver_dz[:count],base.solver_dz[:count])
    runs, samples = {}, {}
    for name, operands in (("base",layers),("regenerated_tall",tall_layers),("preserved_tall",preserved)):
        planned = np.r_[0.,np.cumsum(operands)]
        result = wind.run(city, speed=5, direction=270, bounds=(*bounds[:5],float(planned[-1])), vertical_grid=wind.VerticalGrid.from_faces(planned), solver=wind.Solver(precision="float64", tolerance=1e-8, max_iterations=20000, raise_on_failure=True))
        np.testing.assert_array_equal(result.z_faces,effective_faces(operands))
        samples[name] = {h: result.sample(h,method="linear") for h in (1.5,1.75)}
        runs[name] = dict(layers=len(operands),effective_top=float(result.z_faces[-1]),
            solver_dz_sha256=hashlib.sha256(operands.astype(np.float32).tobytes()).hexdigest(),
            iterations=result.diagnostics.iterations,converged=result.diagnostics.converged,
            max_divergence=result.diagnostics.max_divergence,
            rms_divergence=result.diagnostics.rms_divergence)
    comparisons = []
    for baseline,name in (("base","regenerated_tall"),("base","preserved_tall"),
                          ("preserved_tall","regenerated_tall")):
        for height in (1.5,1.75):
            a,b = samples[baseline][height],samples[name][height]
            assert np.array_equal(a.valid,b.valid)
            ka,kb = a.speed[a.valid]/5,b.speed[b.valid]/5
            comparisons.append(dict(baseline=baseline,control=name,height=height,fluid_points=int(a.valid.sum()),
                **error_metrics(ka,kb)))
    files = ("src/dtcc_qes/_city.py","src/dtcc_qes/_turbulence_domain.py",
             "src/dtcc_qes/_auto_grid.py","tools/check_turbulence_domain.py")
    output = dict(case=dict(rectangles=rects,speed=5,direction=270,resolution=2,fine_region_height=40),
        solver=dict(precision="float64",tolerance=1e-8,max_iterations=20000),
        sampling=dict(method="linear",heights=[1.5,1.75],normalized_speed="magnitude of sampled velocity / 5 m/s"),
        turbulence_domain=record,base_vertical_grid=vertical,runs=runs,comparisons=comparisons,
        taller_control_planned_top=control_top,
        taller_effective_top_difference=runs["regenerated_tall"]["effective_top"]-runs["preserved_tall"]["effective_top"],
        fine_band_operands_identical=True,preserved_control_prefix_identical=True,
        targets=dict(p95_abs_delta_K=.05,peak_relative_difference=.05),
        scope="Focused mean-wind control; Task 9 and physical gust validation remain required",
        build=dict(qes_revision=_qes.qes_revision,compiler_id=_qes.compiler_id,
            compiler_version=_qes.compiler_version,openmp=_qes.openmp_enabled,platform=platform.platform()),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        passed=all(c["passed"] for c in comparisons))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    # Artifact checks verify the record against these snapshots, not live files.
    sources = args.output.parent/"sources"
    shutil.rmtree(sources,ignore_errors=True)
    for name in files:
        (sources/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,sources/name)
    print(json.dumps({k:output[k] for k in ("runs","comparisons","passed")},indent=2))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
