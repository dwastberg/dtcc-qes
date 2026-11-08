"""Directed repeated RSS review of the two flagged 1 m isolated-building cases.

Run only after the full timing matrix. Twelve fresh workers preserve all original
settings and alternate order; phase observations do not change the solver.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent


def allocator_reader():
    """Read the SDK-defined sum of statistics for all Darwin malloc zones.

    These are allocator statistics, not complete process ownership. In
    particular, direct VM mappings are outside their scope. max_size_in_use
    is the summed zone high-water mark of touched memory, not a simultaneous
    process-wide peak. Neither field is a measurement of compressed pages.
    """
    if sys.platform != 'darwin':
        raise RuntimeError('This directed review uses Darwin allocator statistics')
    class Statistics(ctypes.Structure):
        _fields_ = [('blocks_in_use', ctypes.c_uint),
                    ('size_in_use', ctypes.c_size_t),
                    ('max_size_in_use', ctypes.c_size_t),
                    ('size_allocated', ctypes.c_size_t)]
    library = ctypes.CDLL(None)
    statistics = library.malloc_zone_statistics
    statistics.argtypes = [ctypes.c_void_p, ctypes.POINTER(Statistics)]
    statistics.restype = None
    def read():
        result = Statistics()
        statistics(None, ctypes.byref(result))
        return {name: getattr(result, name) for name, _ in Statistics._fields_}
    return read


def worker(job, manifest, output):
    from dtcc_qes import _qes, wind
    from aij import runner, sampling
    from aij.runspec import RunSpec
    assert hashlib.sha256(Path(_qes.__file__).read_bytes()).hexdigest() == manifest['arms'][job['arm']]['native_sha256']
    phases = []
    field_hashes = {};field_bytes = {}
    read_allocator = allocator_reader()
    def observe(name):
        phases.append(dict(name=name, peak_rss_bytes=runner._peak_rss(),
                           native_resources=_qes._resource_usage(),
                           allocator=read_allocator()))
    def fingerprint(name, array):
        field_hashes[name] = dict(shape=list(array.shape), dtype=str(array.dtype),
            sha256=hashlib.sha256(memoryview(array).cast('B')).hexdigest())
        field_bytes[name] = array.nbytes
    original_class = _qes.WindRunner
    class Runner:
        def __init__(self): self.native = original_class()
        def __getattr__(self, name): return getattr(self.native, name)
        def prepare(self, *args, **kwargs):
            result = self.native.prepare(*args, **kwargs);observe('native_prepare');return result
        def solve(self, *args, **kwargs):
            result = self.native.solve(*args, **kwargs);observe('native_solve_and_transfer');return result
    _qes.WindRunner = Runner
    original_run = wind.run
    def run(*args, **kwargs):
        observe('before_wind_run')
        result = original_run(*args, **kwargs)
        observe('after_wind_run')
        for name in ('velocity', 'cell_flags', 'x', 'y', 'z', 'z_faces'):
            fingerprint(name, getattr(result, name))
        for name in ('stress', 'tke', 'co_eps', 'mixing_length', 'computed', 'capped', 'stress_valid'):
            fingerprint('turbulence/' + name, getattr(result.turbulence, name))
        observe('after_full_field_hashing')
        return result
    wind.run = run
    original_probe = sampling.probe_sample
    def probe(*args, **kwargs):
        result = original_probe(*args, **kwargs);observe('after_probes');return result
    sampling.probe_sample = probe
    original_planes = runner._isolated_fields
    def planes(*args, **kwargs):
        result = original_planes(*args, **kwargs);observe('after_isolated_planes');return result
    runner._isolated_fields = planes
    _qes._reset_resource_peaks();observe('initial')
    started = time.perf_counter()
    record, arrays = runner.run(RunSpec.from_dict(job['spec']))
    observe('after_workflow')
    report = dict(job=job, native=str(_qes.__file__), phases=phases,
        field_hashes=field_hashes, field_bytes=field_bytes,
        seconds=time.perf_counter()-started, peak_rss_bytes=record['peak_rss_bytes'],
        diagnostics=record['diagnostics'])
    output.write_text(json.dumps(runner._clean(report), indent=2) + '\n')


def execute(folder):
    import numpy as np
    manifest = json.loads((WORK / 'full-comparison/manifest.json').read_text())
    full = json.loads((WORK / 'full-comparison/report.json').read_text())
    assert full['regression_passed']
    folder.mkdir(exist_ok=False)
    specs = {j['spec']['case']: j['spec'] for j in manifest['jobs']
             if j['arm'] == 'main' and j['spec']['resolution'] == 1. and j['spec']['case'] in ('A', 'B')}
    jobs = [dict(id=f'{case}-{repeat}-{arm}', case=case, repeat=repeat, arm=arm, spec=specs[case])
            for repeat in range(3) for case in ('A', 'B')
            for arm in (('candidate', 'main') if repeat % 2 == 0 else ('main', 'candidate'))]
    assert len(jobs) == 12
    (folder / 'protocol.json').write_text(json.dumps(dict(workers=12, jobs=jobs,
        purpose='Review >10% RSS ratios; no physics change or broad rerun',
        phases='Initial, native prepare, native solve/transfer, public call, full-field hashing, probes, planes, final',
        criterion='Compare median peak RSS, full field hashes, returned array bytes and scoped native ownership; investigate any persistent >10% increase',
        native_accounting_limit='Tracked wind grid, Poisson and workspace only; excludes turbulence, Python output and allocator retention',
        allocator_accounting='malloc_zone_statistics(NULL): sum over Darwin malloc zones; direct VM mappings excluded; summed zone high-water marks are not a simultaneous process peak',
        allocator_definition='/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/malloc/malloc.h:532-537,612-613',
        hashing_effect='All returned fields are read without copying after native execution; this can alter page residency, so before/after observations are separate',
        source_driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2) + '\n')
    rows = []
    for job in jobs:
        arm = manifest['arms'][job['arm']]
        env = dict(os.environ, PYTHONPATH=f"{arm['package']}:{arm['source']}/validation",
                   OMP_NUM_THREADS='4', OMP_DYNAMIC='FALSE', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        output = folder / (job['id'] + '.json')
        (folder / (job['id'] + '-before-vm-stat.txt')).write_text(
            subprocess.check_output(['vm_stat'], text=True))
        with (folder / (job['id'] + '.log')).open('x') as log:
            subprocess.run([sys.executable, __file__, '--output', str(output), '--worker', json.dumps(job)],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True)
        (folder / (job['id'] + '-after-vm-stat.txt')).write_text(
            subprocess.check_output(['vm_stat'], text=True))
        row = json.loads(output.read_text());rows.append(row)
        print(job['id'], round(row['peak_rss_bytes']/2**30, 3), 'GiB', flush=True)
    report = {'workers': 12, 'cases': {}}
    for case in ('A', 'B'):
        selected = [r for r in rows if r['job']['case'] == case]
        median = {arm: float(np.median([r['peak_rss_bytes'] for r in selected if r['job']['arm'] == arm])) for arm in ('main', 'candidate')}
        phase_names = [p['name'] for p in selected[0]['phases']]
        assert len(set(phase_names)) == len(phase_names)
        assert all([p['name'] for p in r['phases']] == phase_names for r in selected)
        phases = {}
        for name in phase_names:
            matching = {arm: [next(p for p in r['phases'] if p['name'] == name)
                for r in selected if r['job']['arm'] == arm] for arm in ('main', 'candidate')}
            all_phases = matching['main'] + matching['candidate']
            allocator = {arm: {key: float(np.median([p['allocator'][key] for p in ps]))
                for key in ps[0]['allocator']} for arm, ps in matching.items()}
            phases[name] = dict(
                native_resources_identical=all(p['native_resources'] == all_phases[0]['native_resources'] for p in all_phases),
                median_peak_rss_bytes={arm: float(np.median([p['peak_rss_bytes'] for p in ps])) for arm, ps in matching.items()},
                median_allocator=allocator,
                allocator_candidate_minus_main={key: allocator['candidate'][key]-allocator['main'][key] for key in allocator['main']})
        report['cases'][case] = dict(median_peak_rss_bytes=median, ratio=median['candidate']/median['main'],
            fields_identical=all(r['field_hashes'] == selected[0]['field_hashes'] for r in selected),
            returned_bytes_identical=all(r['field_bytes'] == selected[0]['field_bytes'] for r in selected),
            rss_values={arm: [r['peak_rss_bytes'] for r in selected if r['job']['arm'] == arm] for arm in ('main','candidate')},
            phases=phases)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker')
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker), json.loads((WORK / 'full-comparison/manifest.json').read_text()), args.output)
    else:
        execute(args.output)
