"""One frozen 74-condition main/candidate regression; no physics sweep."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    from aij.evidence import write_json
    write_json(path, value)


def prepare(folder, candidate):
    from aij import campaigns
    import aij
    from importlib.metadata import version
    specs = [s for resolution in (2., 1.) for s in campaigns.ab_baseline(resolution) + campaigns.baseline(resolution)]
    assert len(specs) == 74 and len({s.key for s in specs}) == 74
    folder.mkdir(parents=True, exist_ok=False)
    source = WORK / 'trees/f17db8ee504b2961b55a4f66f85bbbaa261ae142'
    arms = {'main': {'package': WORK / 'baseline-package', 'source': source},
            'candidate': {'package': candidate.resolve(), 'source': ROOT}}
    for arm in arms.values():
        files = list((arm['package'] / 'dtcc_qes').glob('*.py')) + list((arm['package'] / 'dtcc_qes').glob('_qes*.so'))
        files += list((arm['source'] / 'validation/aij').glob('*.py'))
        arm['hashes'] = {str(p.resolve()): sha(p) for p in files}
        arm['native_sha256'] = sha(next((arm['package'] / 'dtcc_qes').glob('_qes*.so')))
    jobs = []
    for index, spec in enumerate(specs):
        for arm in (('main', 'candidate') if index % 2 == 0 else ('candidate', 'main')):
            jobs.append({'id': f'{len(jobs):03d}-{arm}', 'arm': arm, 'spec': spec.to_dict(), 'key': spec.key})
    manifest = dict(schema='ready-integration-full-v1', baseline_commit=source.name,
        candidate_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        arms=arms, jobs=jobs, source_driver_sha256=sha(__file__), python=sys.version,
        dependencies={name: version(name) for name in ('numpy', 'dtcc-core', 'xlrd', 'ezdxf', 'shapely')},
        data_hashes={str(getattr(aij, name)): sha(getattr(aij, name)) for name in
            ('CASE_A_XLS', 'CASE_B_XLS', 'CASE_D_XLS', 'CASE_D_DXF', 'CASE_E_XLS', 'CASE_E_DXF')},
        protocol=dict(workers=148, order='alternating paired implementations, 2 m then 1 m',
            omp_threads=4, blas_threads=1, worker_deadline_seconds=900,
            physical_claim='Regression preservation only; fixed work is not physical acceptance',
            performance_rule='Investigate grouped median increases exceeding both 10% and 0.01 s; review every outlier',
            memory_rule='Review paired peak RSS increases over 10%; no memory cap'))
    save(folder / 'manifest.json', manifest)


def worker(manifest, job, folder):
    import dtcc_qes
    from dtcc_qes import _qes
    from aij import runner
    from aij.runspec import RunSpec
    arm = manifest['arms'][job['arm']]
    package = Path(arm['package']).resolve() / 'dtcc_qes'
    assert Path(dtcc_qes.__file__).resolve().is_relative_to(package)
    assert Path(_qes.__file__).resolve().is_relative_to(package)
    assert Path(runner.__file__).resolve().is_relative_to(Path(arm['source']) / 'validation')
    assert sha(_qes.__file__) == arm['native_sha256']
    spec = RunSpec.from_dict(job['spec'])
    started = time.perf_counter()
    record, arrays = runner.run(spec)
    path = runner.write(record, arrays, folder / 'records' / job['arm'] / spec.case)
    save(folder / (job['id'] + '.worker.json'), dict(complete=True, key=spec.key,
        native_sha256=sha(_qes.__file__), package=str(package), runner=str(runner.__file__),
        source=arm['source'], native_build=dict(compiler=_qes.compiler_id, compiler_version=_qes.compiler_version,
            fp_contract=_qes.fp_contract, policy_revision=_qes.solver_policy_revision, backend=_qes.cpu_backend),
        record_sha256=sha(path), arrays_sha256=sha(path.with_suffix('.npz')),
        worker_seconds=time.perf_counter()-started))


def execute(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert sha(__file__) == manifest['source_driver_sha256']
    assert len(manifest['jobs']) == 148
    (folder / 'started').touch(exist_ok=False)
    assert all(sha(p) == expected for p, expected in manifest['data_hashes'].items())
    for arm in manifest['arms'].values():
        assert all(sha(p) == expected for p, expected in arm['hashes'].items())
    for number, job in enumerate(manifest['jobs']):
        arm = manifest['arms'][job['arm']]
        env = dict(os.environ, PYTHONPATH=f"{arm['package']}:{arm['source']}/validation",
            OMP_NUM_THREADS='4', OMP_DYNAMIC='FALSE', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        command = [sys.executable, __file__, '--output', str(folder), '--worker', str(number)]
        started = time.perf_counter()
        print(f"{number+1}/148 {job['id']} {job['spec']['case']} {job['spec']['state']} {job['spec']['label']} {job['spec']['resolution']} m", flush=True)
        with (folder / (job['id'] + '.log')).open('x') as out:
            try:
                result = subprocess.run(command, env=env, stdout=out, stderr=subprocess.STDOUT,
                    timeout=manifest['protocol']['worker_deadline_seconds'])
                outcome = dict(complete=result.returncode == 0, returncode=result.returncode)
            except subprocess.TimeoutExpired:
                outcome = dict(complete=False, returncode=None, timeout=True)
        outcome.update(wall_seconds=time.perf_counter()-started, job=job)
        save(folder / (job['id'] + '.outcome.json'), outcome)
        if not outcome['complete']:
            raise RuntimeError(f"Worker failed: {job['id']}; preserve evidence before investigating")
    save(folder / 'completed.json', dict(workers=148, completed=True))
    analyse(folder)


def analyse(folder):
    import numpy as np
    from aij import compare
    from aij.runspec import RunSpec
    manifest = json.loads((folder / 'manifest.json').read_text())
    pairs = []
    for first, second in zip(manifest['jobs'][::2], manifest['jobs'][1::2]):
        spec = RunSpec.from_dict(first['spec'])
        records = {}; paths = {}; seconds = {}
        for job in (first, second):
            arm = job['arm'];path = folder / 'records' / arm / spec.case / (spec.key + '.json')
            records[arm] = json.loads(path.read_text());paths[arm] = path
            evidence = json.loads((folder / (job['id'] + '.worker.json')).read_text())
            assert sha(path) == evidence['record_sha256']
            assert sha(path.with_suffix('.npz')) == evidence['arrays_sha256']
            outcome = json.loads((folder / (job['id'] + '.outcome.json')).read_text())
            assert outcome['complete'];seconds[arm] = outcome['wall_seconds']
        a, b = records['main'], records['candidate']
        checks = {name: a.get(name) == b.get(name) for name in
            ('spec', 'grid', 'profile', 'diagnostics', 'centreline', 'footprints', 'ignored_city_objects')}
        checks['measurement'] = a['provenance']['xls_sha256'] == b['provenance']['xls_sha256']
        checks['geometry'] = a['provenance']['city_digest'] == b['provenance']['city_digest']
        checks['probes'] = all(k in b['probes'] and value == b['probes'][k] for k, value in a['probes'].items())
        checks['declared_probe_additions'] = set(b['probes']) - set(a['probes']) <= {'sampling_provenance', 'stress', 'stress_valid'}
        with np.load(paths['main'].with_suffix('.npz')) as x, np.load(paths['candidate'].with_suffix('.npz')) as y:
            checks['planes'] = set(x.files) == set(y.files) and all(x[k].dtype == y[k].dtype and x[k].shape == y[k].shape and np.array_equal(x[k], y[k], equal_nan=True) for k in x.files)
        pairs.append(dict(key=spec.key, case=spec.case, resolution=spec.resolution, passed=all(checks.values()),
            checks=checks, wall_seconds=seconds,
            wind_run_seconds={arm: r['wall_seconds'] for arm,r in records.items()},
            solve_seconds={arm: r['timings']['native']['solve_seconds'] for arm,r in records.items()},
            rss={arm: r['peak_rss_bytes'] for arm,r in records.items()},
            converged={arm: r['diagnostics']['converged'] for arm,r in records.items()}))
    scores = {};groups = {}
    for resolution in (2., 1.):
        specs = [RunSpec.from_dict(j['spec']) for j in manifest['jobs'] if j['arm'] == 'main' and j['spec']['resolution'] == resolution]
        for arm in ('main', 'candidate'):
            records = compare.load_records(folder / 'records' / arm, specs)
            comparisons = compare.isolated(records, 'A') + compare.isolated(records, 'B') + compare.case_d(records) + compare.case_e_comparisons(records)
            scores[f'{arm}-{resolution:g}m'] = {c.name: c.scores() for c in comparisons}
        for case in ('A', 'B', 'D', 'E'):
            rows = [r for r in pairs if r['case'] == case and r['resolution'] == resolution]
            median = {arm: float(np.median([r['wind_run_seconds'][arm] for r in rows])) for arm in ('main', 'candidate')}
            ratio = median['candidate'] / median['main'];delta = median['candidate'] - median['main']
            rss_ratio = max(r['rss']['candidate']/r['rss']['main'] for r in rows)
            groups[f'{case}-{resolution:g}m'] = dict(conditions=len(rows), median_wind_run_seconds=median,
                ratio=ratio, delta_seconds=delta, maximum_rss_ratio=rss_ratio,
                timing_review=ratio > 1.10 and delta > .01, memory_review=rss_ratio > 1.10)
    save(folder / 'report.json', dict(regression_passed=all(r['passed'] for r in pairs),
        pairs=pairs, performance=groups, measured_scores=scores,
        scope='Exact preservation on the canonical 74 fixed-work conditions; no new physical accuracy qualification'))
    print('Full regression:', all(r['passed'] for r in pairs), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--analyse', action='store_true')
    parser.add_argument('--worker', type=int)
    args = parser.parse_args();folder = args.output.resolve()
    if args.prepare:
        prepare(folder, args.candidate)
    elif args.worker is not None:
        m = json.loads((folder / 'manifest.json').read_text());worker(m, m['jobs'][args.worker], folder)
    elif args.analyse:
        analyse(folder)
    else:
        execute(folder)
