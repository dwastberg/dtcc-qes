"""Bounded OpenMP API timings and same-grid pedestrian errors against saved references.

Historical archives are read-only. Every subprocess has a 30-second deadline;
the complete matrix has a 180-second wall budget. Timings exclude imports,
City creation and pedestrian sampling, as in the old normal-API measurements.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

import numpy as np

from run_auto_grid_controls import collocate, make_city, rectangles
from run_horizontal_sensitivity import array, audit_point, digest, values
from run_joint_grid_verification import atomic_json, read
from run_precision_verification import gate

OLD_API = Path('docs/data/finest-reference/runtime-review.json')
REFERENCE = Path('docs/data/generated-grid-pilot/raw.json.gz')
POINTS = [[27, 21], [21, 23], [51, 35], [15, 47], [15, 29]]


def metrics(actual, reference):
    a, b = array(actual), array(reference)
    am, bm = np.isfinite(a).all(axis=1), np.isfinite(b).all(axis=1)
    valid = am & bm
    vector = np.linalg.norm(a[valid]-b[valid], axis=1)
    speed = np.abs(np.linalg.norm(a[valid], axis=1)-np.linalg.norm(b[valid], axis=1))
    return dict(common_fluid_points=int(valid.sum()), validity_changes=int((am != bm).sum()),
        p95_vector_error_mps=float(np.percentile(vector, 95)),
        max_vector_error_mps=float(vector.max()),
        p95_speed_error_mps=float(np.percentile(speed, 95)), max_speed_error_mps=float(speed.max()))


def worker(precision, iterations, output):
    from dtcc_qes import wind, _qes
    assert _qes.openmp_enabled and _qes.cpu_backend == 'OpenMP CPU'
    reference = next(r for r in read(REFERENCE)['serial']['runs'] if r['task']['extent'] == 160)
    assert gate(reference)['accepted']
    city = make_city(rectangles('tower'))
    start = perf_counter()
    result = wind.run(city, 5, 270, resolution=.5, bounds=(-40, -40, 0, 120, 120, 64),
        vertical_grid=wind.VerticalGrid.auto(), max_cells=40000000,
        solver_precision=precision, max_iterations=iterations)
    elapsed = perf_counter()-start
    # The physical grid matches the archive; the public profile uses one sensor,
    # hence is horizontally uniform. Sensor positions are retained explicitly.
    np.testing.assert_array_equal(result.z_faces, np.asarray(reference['z_faces'], np.float32))
    x = result.x.astype(float)+result.origin[0]
    y = result.y.astype(float)+result.origin[1]
    sx, sy = np.asarray(reference['sample_x']), np.asarray(reference['sample_y'])
    ix, iy = np.searchsorted(x, sx), np.searchsorted(y, sy)
    np.testing.assert_array_equal(x[ix], sx)
    np.testing.assert_array_equal(y[iy], sy)
    planes, comparisons = [], []
    for height in (1.5, 1.75):
        sample = result.sample(height, method='linear')
        velocity = sample.velocity[iy[:, None], ix[None, :]].reshape(-1, 3)
        valid = sample.valid[iy[:, None], ix[None, :]].ravel()
        planes.append(dict(height=height, velocity=[v.tolist() if ok else None
            for v, ok in zip(velocity, valid)]))
    sampled = dict(sample_x=sx.tolist(), sample_y=sy.tolist(), checkpoints=[dict(planes=planes)])
    for plane in planes:
        height = plane['height']
        row = metrics(collocate(plane['velocity'], sx, sy), values(reference, height))
        local = []
        for point in POINTS:
            a = audit_point(sampled, height, point, 'final')
            b = audit_point(reference, height, point, 'final')
            assert a['valid'] and b['valid']
            local.append(dict(point=point, K=a['K'], reference_K=b['K'],
                abs_speed_error_mps=abs(a['K']-b['K'])*5,
                relative_speed_error=abs(a['K']-b['K'])/b['K']))
        comparisons.append(row | dict(height=height, mandatory_points=local))
    atomic_json(output, dict(status='completed', precision=precision,
        requested_iterations=iterations, api_run_seconds=elapsed,
        backend=_qes.cpu_backend, build_type=_qes.build_type, compiler=_qes.compiler_version,
        extension_sha256=digest(_qes.__file__), shape=list(result.velocity.shape[:3]),
        cells=int(np.prod(result.velocity.shape[:3])), diagnostics=asdict(result.diagnostics),
        metadata=result.metadata, reference_final_iterations=reference['checkpoints'][-1]['iterations'],
        grid_equal=True, comparisons=comparisons, sampled_planes=planes,
        reference_scope='Same grid, geometry, profile and production flags; archived single sensor at world (5,5), public sensor position recorded in metadata; initial-field equality not directly measured.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', choices=('float32', 'float64'))
    parser.add_argument('--iterations', type=int, default=500)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker, args.iterations, args.output)
    if args.output is None:
        args.output = Path('build/openmp-benchmark')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    # Fixed matrix: scaling, float32 production behavior, extra iterations within
    # the same wall cap, and repeated four-thread timings. No adaptive expansion.
    matrix = [(1, 'float64', 500), (2, 'float64', 500), (4, 'float64', 500),
              (8, 'float64', 500), (4, 'float32', 500), (4, 'float64', 1000),
              (4, 'float64', 500), (4, 'float32', 500)]
    old = read(OLD_API)
    for p, sha in old['source_sha256'].items():
        if p != 'tools/benchmark_fast_wind.py':
            assert digest(p) == sha, f'Changed numerical/API source: {p}'
    protocol = dict(utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
        cpu_count=os.cpu_count(), matrix=matrix, per_case_seconds=30, total_seconds=180,
        old_api_sha256=digest(OLD_API), reference_sha256=digest(REFERENCE),
        tool_sha256=digest(__file__), old_api=old['runs'],
        scope='Diagnostic fixed-iteration performance and same-grid error; no comfort qualification or reference certification. Historical serial API timings have one repetition and were measured earlier.')
    atomic_json(root/'protocol.json', protocol)
    rows = []
    start = perf_counter()
    for index, (threads, precision, iterations) in enumerate(matrix):
        remaining = 180-(perf_counter()-start)
        if remaining < 2:
            rows.append(dict(status='skipped_total_budget', threads=threads, precision=precision,
                             requested_iterations=iterations))
            continue
        path = root/f'{index}-{precision}-{threads}threads-{iterations}.json'
        command = [str(Path(sys.executable).absolute()), str(Path(__file__).absolute()),
                   '--worker', precision, '--iterations', str(iterations), '--output', str(path)]
        case_start = perf_counter()
        with path.with_suffix('.log').open('w') as log:
            try:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True,
                    timeout=min(30, remaining), env=os.environ | {
                        'OMP_NUM_THREADS': str(threads), 'OMP_DYNAMIC': 'FALSE'})
                row = read(path)
                row.pop('sampled_planes')
                row.pop('metadata')
            except subprocess.TimeoutExpired:
                row = dict(status='timeout', wall_limit_seconds=min(30, remaining))
            except subprocess.CalledProcessError as error:
                row = dict(status='failed', exit_code=error.returncode)
        row.update(threads=threads, precision=precision, requested_iterations=iterations,
                   process_seconds=perf_counter()-case_start, record=str(path))
        rows.append(row)
        atomic_json(root/'summary.json', protocol | dict(runs=rows, elapsed_seconds=perf_counter()-start))
        print({k: row[k] for k in ('threads', 'precision', 'requested_iterations', 'status', 'process_seconds')}, flush=True)
    summary = protocol | dict(runs=rows, elapsed_seconds=perf_counter()-start)
    atomic_json(root/'summary.json', summary)
    print(root/'summary.json', flush=True)


if __name__ == '__main__':
    main()
