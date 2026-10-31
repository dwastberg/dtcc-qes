"""Reproducible QES turbulence implementation gate; not physical gust validation.

Run workers serially in fresh processes. Three repetitions are mandatory for
the full matrix. Large temporary native arrays stay under build/, while JSON
retains timings, diagnostics, sample tensors, masks and excluded locations.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HEIGHTS = (1.5, 1.75)
RTOL, ATOL = 1e-4, 1e-7


def clean(value):
    """JSON uses null for unavailable numbers; never nonstandard NaN tokens."""
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(destination, value):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(clean(value), indent=2, allow_nan=False) + "\n")


def archive_sources(files, root):
    """Snapshot the hashed sources beside the record; artifact checks verify these copies."""
    shutil.rmtree(root, ignore_errors=True)
    for source in files:
        target = root/Path(source).relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def quantiles(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(count=0, p50=None, p95=None, maximum=None)
    q = np.quantile(values, [.5, .95, 1])
    return dict(count=len(values), p50=q[0], p95=q[1], maximum=q[2])


def changes(a, b, eligible=None):
    """Account for both exclusions and zero denominators before quantiles."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    eligible = np.ones(a.shape, bool) if eligible is None else np.asarray(eligible, bool)
    common = eligible & np.isfinite(a) & np.isfinite(b)
    zero = common & (a == 0)
    relative = common & (a != 0)
    return dict(common_count=int(common.sum()), excluded_indices=np.flatnonzero(~common),
                zero_denominator_indices=np.flatnonzero(zero),
                zero_denominator_count=int(zero.sum()),
                absolute=quantiles(np.abs(b[common]-a[common])),
                relative=quantiles(np.abs((b[relative]-a[relative])/a[relative])),
                zero_denominator_absolute=quantiles(np.abs(b[zero]-a[zero])))


def accepted(run):
    """A converged solve can still fail extraction/validity correctness."""
    v = run.get("validity", {})
    return bool(run["diagnostics"]["converged"] and
                all(v.get(k, 0) == 0 for k in (
                    "mask_mismatches", "invalid_finite_std", "invalid_finite_ti",
                    "computed_nonfinite", "count_mismatches")))


def pair(a, b):
    if not (accepted(a) and accepted(b)):
        return dict(accepted=False, reason="failed convergence or validity gate")
    comparisons = []
    for sa, sb in zip(a["samples"], b["samples"], strict=True):
        if sa["method"] != "linear":
            continue
        assert sa["locations_xy"] == sb["locations_xy"]
        comparisons.append(dict(height=sa["height"],
            locations_xy=sa["locations_xy"],
            sigma=changes(sa["sigma"], sb["sigma"]),
            intensity=changes(sa["intensity"], sb["intensity"]),
            velocity_change=quantiles(np.linalg.norm(
                np.asarray(sb["velocity"], float)-np.asarray(sa["velocity"], float), axis=-1)),
            a_coverage=sa["coverage"], b_coverage=sb["coverage"]))
    return dict(accepted=True, comparisons=comparisons)


def independent(stress, velocity):
    """Float64 unnormalized eigen oracle, independent of production classifier."""
    raw = np.asarray(stress, dtype=float)
    matrix = np.zeros((*raw.shape[:-1], 3, 3), dtype=float)
    matrix[..., 0, 0], matrix[..., 1, 1], matrix[..., 2, 2] = raw[..., 0], raw[..., 3], raw[..., 5]
    matrix[..., 0, 1] = matrix[..., 1, 0] = raw[..., 1]
    matrix[..., 0, 2] = matrix[..., 2, 0] = raw[..., 2]
    matrix[..., 1, 2] = matrix[..., 2, 1] = raw[..., 4]
    finite = np.isfinite(raw).all(axis=-1)
    eigen = np.full((*raw.shape[:-1], 3), np.nan)
    eigen[finite] = np.linalg.eigvalsh(matrix[finite])
    tolerance = 32*np.finfo(np.float32).eps*np.max(np.abs(eigen), axis=-1)
    valid = finite & (eigen[..., 0] >= -tolerance)
    speed = np.hypot.reduce(np.asarray(velocity, dtype=float), axis=-1)
    direction = np.zeros_like(velocity, dtype=float)
    np.divide(velocity, speed[..., None], out=direction, where=speed[..., None] > 0)
    projected = np.einsum("...i,...ij,...j->...", direction, matrix, direction)
    return valid, eigen[..., 0], projected, tolerance


def rss():
    # macOS ru_maxrss is bytes; Linux uses KiB. Includes Python and imports.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def configuration(name, geometry, *, method=0, grid="2", speed=5, direction=270,
                  domain="explicit", top=64):
    return dict(name=name, geometry=geometry, method=method, grid=grid, speed=speed,
                direction=direction, domain=domain, top=top)


def geometry_rectangles(name):
    from run_auto_grid_controls import rectangles
    if name in ("flat", "tiny"):
        return []
    if name == "city":
        # 25 separated blocks; 200 x 200 x 32 = 1,280,000 physical cells.
        return [[x, y, 12, 12, 8] for y in range(60, 341, 70) for x in range(60, 341, 70)]
    if name in ("midrise", "regenerated"):
        return [r[:4] + [15] for r in rectangles("array")]
    return rectangles(name)


def prepare_configuration(config):
    from dtcc_qes import wind
    from dtcc_qes.vertical_grid import effective_faces
    from run_auto_grid_controls import make_city

    city = make_city(geometry_rectangles(config["geometry"]))
    extent = 400 if config["geometry"] == "city" else 24 if config["geometry"] in ("flat", "tiny") else 80
    spacing = float(config["grid"]) if config["grid"] != "auto" else 2.
    spec = wind.VerticalGrid.auto(fine_region_height=40) if config["geometry"] == "regenerated" else (
        wind.VerticalGrid.auto() if config["grid"] == "auto" else None)
    opts = dict(resolution=spacing, max_cells=3_000_000, vertical_grid=spec)
    if config["domain"] == "explicit":
        opts["bounds"] = (0, 0, 0, extent, extent, config["top"])
        if "vertical_spacing" in config:
            vertical = config["vertical_spacing"]
            opts["vertical_grid"] = (wind.VerticalGrid.auto() if vertical == "auto" else
                wind.VerticalGrid.from_faces(np.arange(0, config["top"]+float(vertical)/2, float(vertical))))
    elif config["domain"] in ("tall", "regenerated_tall", "grown_off"):
        base = wind.preview_grid(city, **opts, turbulence=True)
        # Reuse planned operands, not differences of rounded effective faces.
        vertical = base.domain["vertical_grid"]
        operands = (np.diff(vertical["planned_faces"]) if spec is not None else
                    base.solver_dz.astype(float))
        layers = list(operands)
        if config["domain"] in ("tall", "regenerated_tall"):
            target = float(base.z_faces[-1]) + 32
            while effective_faces(layers)[-1] < target:
                layers.append(operands[-1])
        faces = np.r_[0., np.cumsum(layers)]
        opts["vertical_grid"] = (spec if config["domain"] == "regenerated_tall" else
                                 wind.VerticalGrid.from_faces(faces))
        opts["bounds"] = (*base.domain["effective_bounds"][:5], float(faces[-1]))
    elif config["domain"] != "auto":
        raise ValueError("Unknown domain policy")
    condition = wind._validate_condition(config["speed"], config["direction"], 10, .1)
    grid = wind._validate_grid(opts["resolution"], opts.get("bounds"), 20, 20,
                               opts["max_cells"], vertical_grid=opts["vertical_grid"])
    geometry, prepared = wind._prepare_city(city, condition, grid, None, "measured",
                                             turbulence=config["method"] is not None)
    return geometry, prepared, condition


def fingerprint():
    from dtcc_qes import _qes
    files = [*sorted((ROOT/"src/dtcc_qes").glob("*.py")), Path(__file__).resolve(),
             *sorted((ROOT/"src/cpp").glob("*.cpp")), *sorted((ROOT/"src/qes_core/dtcc").rglob("*.cpp")),
             *sorted((ROOT/"src/qes_core/dtcc").rglob("*.h")),
             *[p for p in sorted((ROOT/"src/qes_core").rglob("*")) if p.suffix in (".cpp", ".h", ".txt")],
             ROOT/"tools/run_auto_grid_controls.py", ROOT/"src/dtcc_qes/_qes_revision.txt", Path(_qes.__file__)]
    return hashlib.sha256(b"".join(hashlib.sha256(f.read_bytes()).digest() for f in files)).hexdigest()


def worker(config, arrays_file=None):
    from dtcc_qes import _qes, wind
    from dtcc_qes.result import _stress_validity

    start = time.perf_counter()
    geometry, prepared, condition = prepare_configuration(config)
    planning = time.perf_counter()-start
    native_condition, solver = _qes.WindCondition(), _qes.SolverOptions()
    for name in ("speed", "direction", "reference_height"):
        setattr(native_condition, name, condition[name])
    # Scale the absolute multiplier threshold with input speed.
    solver.tolerance, solver.max_iterations, solver.precision = 1e-7*config["speed"]/5, 20000, "float64"
    options = {}
    if config["method"] is not None:
        settings = _qes.TurbulenceSettings()
        settings.enabled, settings.mixing_length_method = True, config["method"]
        options["turbulence"] = settings
    memory = dict(imports_and_planning=rss())
    runner = _qes.WindRunner()
    start = time.perf_counter()
    runner.prepare(prepared.grid, prepared.model, **prepared.arrays,
                   dz_layers=prepared.dz_layers, **options)
    prep = time.perf_counter()-start
    memory["after_prepare"] = rss()
    start = time.perf_counter()
    native = runner.solve(native_condition, solver)
    solve = time.perf_counter()-start
    memory["after_solve"] = rss()
    # Match public lifetime: native ownership ends before Python statistics.
    del runner
    result = wind.WindResult(native["velocity"], native["x"], native["y"], native["z"],
        native["cell_flags"], prepared.origin, geometry.crs, prepared.resolution,
        wind.SolveDiagnostics(**native["diagnostics"]), {}, z_faces=native["z_faces"])
    record = dict(config=config, fingerprint=fingerprint(), diagnostics=native["diagnostics"], domain=prepared.domain,
        cells=int(native["cell_flags"].size), shape=list(native["cell_flags"].shape),
        z=native["z"], z_faces=native["z_faces"], origin=prepared.origin,
        solver_dz=(np.full(len(native["z"]), prepared.resolution, dtype=np.float32)
                   if prepared.dz_layers is None else prepared.dz_layers.astype(np.float32)),
        seconds=dict(planning=planning, prepare=prep, solve=solve), peak_rss_bytes=memory,
        velocity_sha256=hashlib.sha256(native["velocity"].tobytes()).hexdigest(),
        solver=dict(precision=solver.precision, tolerance=solver.tolerance, max_iterations=solver.max_iterations))
    fields = native["turbulence"]
    if fields is None:
        return clean(record)
    t = wind.TurbulenceFields(fields["stress"], fields["tke"], fields["co_eps"], fields["mixing_length"],
        fields["state"] > 0, fields["state"] == 2, fields["stress_valid"].astype(bool),
        *(fields[k] for k in ("friction_velocity", "reference_speed", "reference_height",
                             "roughness_length", "displacement_height")))
    from dataclasses import replace
    result = replace(result, turbulence=t)
    start = time.perf_counter()
    python_valid, _ = _stress_validity(t.stress)
    record["seconds"]["python_validity"] = time.perf_counter()-start
    memory["after_python_validity"] = rss()
    start = time.perf_counter()
    sigma = result.streamwise_std
    record["seconds"]["streamwise_std"] = time.perf_counter()-start
    start = time.perf_counter()
    intensity = result.turbulence_intensity
    record["seconds"]["turbulence_intensity_including_std"] = time.perf_counter()-start
    memory["after_derived"] = rss()
    computed = t.computed.ravel()
    invalid_indices, minimum, negative, materially_negative, mismatch = [], np.inf, 0, 0, 0
    raw = t.stress.reshape(-1, 6)
    mean = result.velocity.reshape(-1, 3)
    # This independent oracle is excluded from production timings above.
    for begin in range(0, len(raw), 32768):
        indices = begin + np.flatnonzero(computed[begin:begin+32768])
        valid, eigen_min, projected, tolerance = independent(raw[indices], mean[indices])
        minimum = min(minimum, float(np.min(eigen_min, initial=np.inf)))
        invalid_indices.extend(indices[~valid].tolist())
        negative += int(np.count_nonzero(projected < 0))
        materially_negative += int(np.count_nonzero(projected < -tolerance))
        mismatch += int(np.count_nonzero(valid != t.stress_valid.ravel()[indices]))
    invalid = t.computed & ~t.stress_valid
    nonfinite = sum(int(np.count_nonzero(~np.isfinite(getattr(t, k)[t.computed])))
                    for k in ("stress", "tke", "co_eps", "mixing_length"))
    nonfinite += int(np.count_nonzero(~np.isfinite(result.velocity[t.computed])))
    record["validity"] = dict(computed=int(computed.sum()), capped=int(t.capped.sum()),
        capped_fraction=float(t.capped.sum()/computed.sum()), invalid=int(invalid.sum()),
        invalid_fraction=float(invalid.sum()/computed.sum()), minimum_eigenvalue=minimum,
        negative_projected_variances=negative, materially_negative_projected_variances=materially_negative,
        invalid_flat_indices=invalid_indices, index_order="C order (z,y,x); shape and z recorded; x/y are (i+.5)*resolution",
        invalid_tensor_witnesses=[dict(index=i, stress=raw[i]) for i in invalid_indices[:12]],
        computed_nonfinite=nonfinite,
        mask_mismatches=mismatch+int(np.count_nonzero(python_valid[t.computed] != t.stress_valid[t.computed])),
        count_mismatches=sum((fields["invalid_stress_cells"] != len(invalid_indices),
                              fields["computed_cells"] != int(computed.sum()),
                              fields["capped_cells"] != int(t.capped.sum()),
                              bool(t.stress_valid[~t.computed].any()))),
        invalid_finite_std=int(np.isfinite(sigma[invalid]).sum()),
        invalid_finite_ti=int(np.isfinite(intensity[invalid]).sum()),
        zero_speed=int(np.count_nonzero(t.computed & (result.speed == 0))))
    samples = []
    stride = 8 if config["geometry"] == "city" else 1
    iy, ix = np.meshgrid(np.arange(1, len(result.y)-1, stride),
                         np.arange(1, len(result.x)-1, stride), indexing="ij")
    selection = (iy.ravel(), ix.ravel())
    locations = np.column_stack((result.x[selection[1]], result.y[selection[0]]))
    start = time.perf_counter()
    for height in HEIGHTS:
        for method in ("linear", "nearest"):
            sample = result.sample(height, method)
            std, ti = sample.streamwise_std[selection], sample.turbulence_intensity[selection]
            s, v = sample.stress[selection], sample.velocity[selection]
            oracle, eigen, projection, tolerance = independent(s, v)
            # Explicitly check contributors, not just the interpolated tensor.
            z = result.z.astype(float)
            if method == "nearest":
                contributors = [int(np.argmin(np.abs(z-height)))]
            else:
                hi = int(np.searchsorted(z, height))
                contributors = [hi] if hi < len(z) and z[hi] == height else [hi-1, hi]
            source_valid = np.ones(len(s), bool)
            covered = np.ones(len(s), bool)
            cap = np.zeros(len(s), bool)
            for k in contributors:
                source_valid &= t.stress_valid[k][selection]
                covered &= t.computed[k][selection]
                cap |= t.capped[k][selection]
            usable = sample.valid[selection] & source_valid & oracle
            expected_sigma = np.where(usable & (np.linalg.norm(v, axis=-1) > 0) & (projection >= -tolerance),
                                      np.sqrt(np.maximum(0, projection)), np.nan)
            np.testing.assert_allclose(std, expected_sigma, rtol=1e-12, atol=1e-12, equal_nan=True)
            invalid_source = covered & ~source_valid
            samples.append(dict(height=height, method=method, sampled_height=sample.sampled_height,
                locations_xy=locations, velocity=v, stress=s, sigma=std, intensity=ti,
                coverage=dict(total=len(s), mean_valid=int(sample.valid[selection].sum()),
                    computed=int(covered.sum()), capped=int((cap & covered).sum()),
                    invalid_contributor=int(invalid_source.sum()),
                    invalid_interpolant=int(np.count_nonzero(covered & ~oracle)),
                    contributor_invalid_but_interpolant_valid=int(np.count_nonzero(invalid_source & oracle)),
                    derived_valid=int(np.isfinite(std).sum()),
                    minimum_interpolant_eigenvalue=float(np.nanmin(eigen)),
                    negative_projected_variances=int(np.count_nonzero(projection < 0)),
                    materially_negative_projected_variances=int(np.count_nonzero(projection < -tolerance)),
                    invalid_finite_derived=int(np.isfinite(std[invalid_source | ~oracle]).sum())),
                excluded_indices=np.flatnonzero(~np.isfinite(std)),
                invalid_contributor_indices=np.flatnonzero(invalid_source)))
    record["seconds"]["pedestrian_sampling_and_oracle"] = time.perf_counter()-start
    record["samples"] = samples
    record["friction_velocity"] = t.friction_velocity
    record["raw_stress_sha256"] = hashlib.sha256(t.stress.tobytes()).hexdigest()
    if config["geometry"] == "flat":
        # Centre column is boundary free; compare derivative and interpolation separately.
        j, i = len(result.y)//2, len(result.x)//2
        inflow = .4*config["speed"]/np.log((10+.1)/.1)
        analytic_centres = 2.5*result.z.astype(float)/(result.z.astype(float)+.1)
        flat = []
        for height in HEIGHTS:
            exact = 2.5*height/(height+.1)
            # Public sampling interpolates covariance before taking sqrt.
            # Interpolating analytic sigma would misattribute sampling error
            # to the derivative discretization, especially on the coarse grid.
            interpolated_exact = float(np.sqrt(np.interp(height, result.z, analytic_centres**2)))
            linear = result.sample(height, "linear").streamwise_std[j, i]/inflow
            nearest = result.sample(height, "nearest")
            k = int(np.argmin(np.abs(result.z.astype(float)-height)))
            flat.append(dict(height=height, analytic=exact, linear=linear,
                total_error=linear-exact, derivative_error=linear-interpolated_exact,
                analytic_sampling_error=interpolated_exact-exact,
                nearest_height=nearest.sampled_height,
                nearest=nearest.streamwise_std[j, i]/inflow,
                nearest_derivative_error=nearest.streamwise_std[j, i]/inflow-analytic_centres[k]))
        record["flat_profile"] = flat
    if arrays_file is not None:
        np.savez(arrays_file, velocity=result.velocity, stress=t.stress, co_eps=t.co_eps,
                 tke=t.tke, sigma=sigma, intensity=intensity, computed=t.computed,
                 valid=t.stress_valid, capped=t.capped, zero_speed=result.speed == 0)
    memory["after_benchmark_oracle"] = rss()
    return clean(record)


def invoke(config, directory, suffix="", keep_arrays=False, resume=False):
    name = config["name"] + suffix
    request, output = directory/(name+"-request.json"), directory/(name+".json")
    arrays = directory/(name+".npz") if keep_arrays else None
    if resume and output.exists() and (arrays is None or arrays.exists()):
        cached = json.loads(output.read_text())
        if cached["config"] == config and cached.get("fingerprint") == fingerprint():
            return cached
    write_json(request, config)
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(request), "--output", str(output)]
    if arrays is not None:
        command += ["--arrays", str(arrays)]
    log = directory/(name+".log")
    with log.open("w") as handle:
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, timeout=7200)
    if completed.returncode:
        raise RuntimeError(f"Worker failed: {name}; see {log}")
    return json.loads(output.read_text())


def scaling(a, b, file_a, file_b):
    if not (accepted(a) and accepted(b)):
        return dict(passed=False, accepted=False, reason="failed solve")
    checks = {}
    with np.load(file_a) as first, np.load(file_b) as second:
        for key in ("computed", "valid", "capped", "zero_speed"):
            checks[key] = dict(mismatches=int(np.count_nonzero(first[key] != second[key])))
        for key, factor in (("velocity", 2), ("sigma", 2), ("stress", 4), ("tke", 4),
                            ("co_eps", 8), ("intensity", 1)):
            x, y = np.asarray(first[key], float), np.asarray(second[key], float)
            same_finite = np.isfinite(x) == np.isfinite(y)
            finite = np.isfinite(x) & np.isfinite(y)
            delta = np.abs(y[finite]-factor*x[finite])
            allowed = ATOL + RTOL*np.abs(factor*x[finite])
            checks[key] = dict(finite_mask_mismatches=int(np.count_nonzero(~same_finite)),
                outside_tolerance=int(np.count_nonzero(delta > allowed)),
                max_absolute_error=float(np.max(delta, initial=0)))
    passed = all(v.get("mismatches", 0) == 0 and v.get("finite_mask_mismatches", 0) == 0
                 and v.get("outside_tolerance", 0) == 0 for v in checks.values())
    return dict(accepted=True, passed=passed, rtol=RTOL, atol=ATOL, checks=checks)


def matrix():
    configs = []
    for geometry in ("isolated", "passage", "array", "tower", "city"):
        for method in (None, 0, 1):
            configs.append(configuration(f"cost-{geometry}-{method}", geometry, method=method))
        for method in (0, 1):
            configs.append(configuration(f"scaling-{geometry}-{method}", geometry, method=method, speed=10) |
                           dict(scaling_baseline=f"cost-{geometry}-{method}"))
    for direction in (270, 225):
        for grid in ("2", "1", "0.5", "auto"):
            configs.append(configuration(f"flat-{direction}-{grid}", "flat", direction=direction, grid=grid, top=32))
        configs.append(configuration(f"scaling-flat-{direction}", "flat", direction=direction, top=32, speed=10) |
                       dict(scaling_baseline=f"flat-{direction}-2"))
    for geometry in ("isolated", "passage", "array", "tower"):
        for grid in ("1", "0.5", "auto"):
            # Retain horizontal 2 m spacing for building vertical sensitivity.
            configs.append(configuration(f"sensitivity-{geometry}-{grid}", geometry, grid="2") |
                           dict(vertical_spacing=grid))
    for geometry in ("midrise", "regenerated"):
        for grid in (("2", "auto") if geometry == "midrise" else ("auto",)):
            controls = [("auto", None), ("grown_off", None), ("auto", 0), ("auto", 1), ("tall", 0), ("tall", 1)]
            if geometry == "regenerated":
                controls += [("regenerated_tall", 0), ("regenerated_tall", 1)]
            for domain, method in controls:
                # A wind-only regenerated case cannot fit its fine band: omit it,
                # retaining the already archived explicit regeneration failure.
                if geometry == "regenerated" and domain == "auto" and method is None:
                    continue
                base = configuration(f"domain-{geometry}-{grid}-{domain}-{method}", geometry,
                                     grid=grid, domain=domain, method=method)
                configs.append(base)
                if domain == "auto" and method is not None:
                    configs.append(base | dict(name="scaling-"+base["name"], speed=10,
                                               scaling_baseline=base["name"]))
    return configs


def self_test(directory):
    from dataclasses import replace
    from dtcc_qes import wind
    stats = changes([0, 2, np.nan, 4], [1, 3, 1, np.nan])
    assert stats["common_count"] == 2 and stats["zero_denominator_count"] == 1
    np.testing.assert_array_equal(stats["excluded_indices"], [2, 3])
    assert stats["absolute"]["maximum"] == 1
    assert stats["relative"]["maximum"] == .5
    failed = dict(diagnostics=dict(converged=False))
    assert not accepted(failed) and not pair(failed, failed)["accepted"]
    # An indefinite lower contributor can average to a PSD tensor. It must
    # still disqualify the interpolated statistic and retain its raw values.
    stress = np.zeros((2, 1, 1, 6), dtype=np.float32)
    stress[0, 0, 0] = [1, 2, 0, 1, 0, 1]
    stress[1, 0, 0] = [4, 0, 0, 4, 0, 4]
    mask = np.ones((2, 1, 1), bool)
    fields = wind.TurbulenceFields(stress, mask.astype(np.float32), mask.astype(np.float32),
        mask.astype(np.float32), mask, ~mask, np.array([False, True]).reshape(2,1,1), 1, 5, 10, .1, 0)
    result = wind.WindResult(np.broadcast_to([5., 0, 0], (2, 1, 1, 3)).copy(), np.array([1.]),
        np.array([1.]), np.array([1., 3.]), np.ones((2,1,1), np.int32), (0,0,0), None, 2,
        wind.SolveDiagnostics(1, 0, 1e-5, True), {}, z_faces=np.array([0.,2.,4.]), turbulence=fields)
    sample = result.sample(2, "linear")
    assert independent(sample.stress, sample.velocity)[0].all()
    assert not sample.stress_valid.any() and np.isnan(sample.streamwise_std).all()
    np.testing.assert_array_equal(result.turbulence.stress, stress)
    native = invoke(configuration("tiny", "tiny", top=24), directory)
    assert accepted(native)
    return dict(passed=True, checks=dict(failed_solves_rejected=True, zero_denominators_accounted=True,
                                        invalid_interpolation_accounted=True), worker=native)


def summary(runs):
    grouped = {}
    for run in runs:
        grouped.setdefault(run["config"]["name"], []).append(run)
    costs, representatives = {}, {}
    for name, group in grouped.items():
        assert len(group) == 3
        first = group[0]
        representatives[name] = first
        costs[name] = dict(config=first["config"], cells=first["cells"],
            accepted_repetitions=sum(accepted(r) for r in group),
            seconds={key: dict(median=float(np.median([r["seconds"][key] for r in group])),
                               minimum=min(r["seconds"][key] for r in group),
                               maximum=max(r["seconds"][key] for r in group)) for key in first["seconds"]},
            peak_rss_bytes={key: int(np.median([r["peak_rss_bytes"][key] for r in group]))
                            for key in first["peak_rss_bytes"]},
            diagnostics=[r["diagnostics"] for r in group], validity=first.get("validity"))
    methods, sensitivity, domains = {}, {}, {}
    for geometry in ("isolated", "passage", "array", "tower", "city"):
        a, b = (representatives[f"cost-{geometry}-{m}"] for m in (0, 1))
        methods[geometry] = pair(a, b)
        for m in (None, 0, 1):
            assert representatives[f"cost-{geometry}-{m}"]["velocity_sha256"] == a["velocity_sha256"]
        if geometry != "city":
            for grid in ("1", "0.5", "auto"):
                sensitivity[f"{geometry}-{grid}"] = pair(a, representatives[f"sensitivity-{geometry}-{grid}"])
    for name, a in representatives.items():
        if name.startswith("domain-") and a["config"]["domain"] == "auto" and a["config"]["method"] is not None:
            method = a["config"]["method"]
            b = representatives[name.removesuffix(f"-auto-{method}")+f"-tall-{method}"]
            np.testing.assert_array_equal(b["z_faces"][:len(a["z_faces"])], a["z_faces"])
            np.testing.assert_array_equal(b["solver_dz"][:len(a["solver_dz"])], a["solver_dz"])
            domains[name] = pair(a, b) | dict(base=a["domain"]["turbulence"],
                taller_effective_top=b["z_faces"][-1], lower_effective_faces_identical=True,
                lower_operands_identical=True)
            if a["config"]["geometry"] == "regenerated":
                regenerated = representatives[name.removesuffix(f"-auto-{method}")+f"-regenerated_tall-{method}"]
                domains[name]["regenerated_tall"] = pair(a, regenerated)
                domains[name]["preserved_vs_regenerated_tall"] = pair(b, regenerated)
                domains[name]["regenerated_tall_effective_faces"] = regenerated["z_faces"]
    flat = {name: r["flat_profile"] for name, r in representatives.items() if "flat_profile" in r}
    flat_passed = all(abs(flat[f"flat-{d}-0.5"][i]["total_error"]) <
                      abs(flat[f"flat-{d}-2"][i]["total_error"])
                      for d in (270, 225) for i in (0, 1))
    return clean(dict(costs=costs, methods=methods, building_vertical_sensitivity=sensitivity,
        domains=domains, flat_profile=flat, flat_refinement_passed=flat_passed,
        accepted_configurations=sum(all(accepted(r) for r in g) for g in grouped.values()),
        total_configurations=len(grouped)))


def verify(directory, output):
    """Retain exit codes and complete logs for the non-benchmark gate evidence."""
    from dtcc_qes import _qes
    audited = ROOT/"build/qes-turbulence-reference/audited"/_qes.qes_revision/"build/qesWinds/qesWinds"
    commands = [
        ("release-build", ["cmake", "--build", "build/native", "--parallel", "8"]),
        ("release-tests", ["ctest", "--test-dir", "build/native", "--output-on-failure"]),
        ("release-symbols", ["cmake", "--build", "build/native", "--target", "check_native_symbols"]),
        ("sanitizer-build", ["cmake", "--build", "build/asan", "--parallel", "6"]),
        ("sanitizer-tests", ["ctest", "--test-dir", "build/asan", "--output-on-failure"]),
        ("independent-eigen", [sys.executable, "tools/check_stress_validity.py"]),
        ("audited-parity", [sys.executable, "tools/make_reference.py", "--turbulence", "--baseline",
                            "audited", "--exe", str(audited), "--check"]),
        ("domain-control", [sys.executable, "tools/check_turbulence_domain.py", "--output",
                            str(directory/"domain-control.json")]),
        ("python-tests", [sys.executable, "-m", "pytest", "tests", "-q"]),
    ]
    evidence = dict(qes_revision=_qes.qes_revision, platform=platform.platform(),
                    python=sys.version, fingerprint=fingerprint(), checks=[])
    for name, command in commands:
        log = directory/(name+".log")
        start = time.perf_counter()
        with log.open("w") as handle:
            completed = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        evidence["checks"].append(dict(name=name, command=command, exit_code=completed.returncode,
            elapsed_seconds=time.perf_counter()-start, log=log.name,
            log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(), tail=log.read_text()[-5000:]))
        evidence["passed"] = len(evidence["checks"]) == len(commands) and all(
            c["exit_code"] == 0 for c in evidence["checks"])
        write_json(output, evidence)
        print(f"{name}: exit {completed.returncode}", flush=True)
    if not evidence["passed"]:
        raise SystemExit("Verification failed; inspect the logs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT/"build/turbulence-benchmark")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--verify", action="store_true", help="run native, sanitizer, parity and Python checks")
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--arrays", type=Path)
    parser.add_argument("--resume", action="store_true", help="reuse workers only when inputs and source/binary fingerprints match")
    parser.add_argument("--host-description", default=platform.processor())
    args = parser.parse_args()
    if args.worker:
        write_json(args.output, worker(json.loads(args.worker.read_text()), args.arrays))
        return
    args.work_dir.mkdir(parents=True, exist_ok=True)
    if args.verify:
        verify(args.work_dir, args.output)
        return
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory(dir=args.work_dir, prefix="self-test-") as temporary:
            write_json(args.output, self_test(Path(temporary)))
        print("Turbulence benchmark self-test passed")
        return
    from dtcc_qes import _qes
    runs, scaling_checks = [], {}
    started = datetime.now(timezone.utc).isoformat()
    configs = matrix()
    scaling_baselines = {c["scaling_baseline"] for c in configs if "scaling_baseline" in c}
    for config in configs:
        for repetition in range(3):
            name = config["name"]
            arrays = repetition == 0 and (name in scaling_baselines or "scaling_baseline" in config)
            run = invoke(config, args.work_dir, f"-r{repetition}", arrays, args.resume)
            run["repetition"] = repetition
            if repetition:
                run.pop("samples", None)
                if "validity" in run:
                    run["validity"].pop("invalid_flat_indices", None)
                    run["validity"].pop("invalid_tensor_witnesses", None)
            runs.append(run)
            print(f"{name} repetition {repetition+1}/3: converged={run['diagnostics']['converged']} "
                  f"prepare={run['seconds']['prepare']:.3f}s solve={run['seconds']['solve']:.3f}s", flush=True)
    by_name = {r["config"]["name"]: r for r in runs if r["repetition"] == 0}
    for config in configs:
        if "scaling_baseline" in config:
            a, b = config["scaling_baseline"], config["name"]
            scaling_checks[a] = scaling(by_name[a], by_name[b],
                args.work_dir/(a+"-r0.npz"), args.work_dir/(b+"-r0.npz"))
    files = [*sorted((ROOT/"src/dtcc_qes").glob("*.py")), Path(__file__).resolve(),
             *sorted((ROOT/"src/cpp").glob("*.cpp")), *sorted((ROOT/"src/qes_core/dtcc").rglob("*.cpp")),
             *sorted((ROOT/"src/qes_core/dtcc").rglob("*.h")), ROOT/"src/dtcc_qes/_qes_revision.txt",
             *[p for p in sorted((ROOT/"src/qes_core").rglob("*")) if p.suffix in (".cpp", ".h", ".txt")],
             ROOT/"tools/run_auto_grid_controls.py", ROOT/"src/qes_core/dtcc/api/stress_validity.h"]
    summed = summary(runs)
    raw_file = args.output.with_name(args.output.stem+"-runs.json.gz")
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_bytes(gzip.compress(json.dumps(clean(runs), separators=(",", ":"),
                                                 allow_nan=False).encode(), mtime=0))
    output = dict(schema_version=1, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
        scope="implementation correctness and measured sensitivity; no observational gust or comfort validation",
        environment=dict(platform=platform.platform(), machine=platform.machine(), python=sys.version,
            host_description=args.host_description,
            numpy=np.__version__, compiler_id=_qes.compiler_id, compiler_version=_qes.compiler_version,
            build_type=_qes.build_type, qes_revision=_qes.qes_revision, openmp=_qes.openmp_enabled,
            cpu_count=os.cpu_count(), timing_policy="serial fresh subprocesses; 3 repetitions; median; no host isolation"),
        source_sha256={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        summary=summed, scaling=scaling_checks,
        raw_runs=dict(file=raw_file.name, sha256=hashlib.sha256(raw_file.read_bytes()).hexdigest(),
                      count=len(runs), encoding="gzip compressed JSON; null denotes unavailable floats"),
        benchmark_passed=all(accepted(r) for r in runs) and summed["flat_refinement_passed"] and
                         all(v["passed"] for v in scaling_checks.values()))
    write_json(args.output, output)
    archive_sources(files, args.output.parent/"sources")
    if not output["benchmark_passed"]:
        raise SystemExit("Numerical benchmark failed; inspect archived evidence before downstream work")


if __name__ == "__main__":
    main()
