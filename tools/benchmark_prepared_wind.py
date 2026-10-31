"""Finite S8a fresh/reused direction study; each series runs in a fresh process.

Run with OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE. Outputs are streamed one condition
at a time. Full field/sample fingerprints, diagnostics and control decisions
are compared; elapsed times are deliberately excluded from equality.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = [270, 0, 90, 180, 315, 45, 135, 225]


def comparable(value):
    """Exclude only wall-clock checkpoint stamps, including nested histories."""
    if isinstance(value, dict):
        return {k:comparable(v) for k,v in value.items() if k != 'elapsed_seconds'}
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


def worthwhile(series):
    return all(r['parity'] for r in series.values()) and all(
        series[f'{mode}-4']['saving_fraction'] >= -.05 and
        (series[f'{mode}-8']['saving_fraction'] >= .1 or series[f'{mode}-8']['saving_seconds'] >= .1)
        for mode in ('legacy','adaptive'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def city():
    import numpy as np
    from dtcc_core.model import Building, City, Surface, GeometryType
    value = City()
    for j in range(4):
        for i in range(5):
            x, y = 36 + 20*i, 30 + 22*j
            b = Building(id=f'{i}-{j}')
            b.measured_height = 10 + 4*((i+j) % 4)
            b.add_geometry(Surface(vertices=np.array(
                [[x,y,0],[x,y+14,0],[x+12,y+14,0],[x+12,y,0],[x,y,0]], float)), GeometryType.LOD0)
            value.add_building(b)
    return value


def worker(args):
    import numpy as np
    from dtcc_qes import wind, _qes
    source = city()
    phases = dict(geometry=0., domain=0., native_prepare=0., native_solve_and_transfer=0., sampling=0., output=0.)
    counts = dict(geometry=0, domain=0, native_prepare=0, native_solve_and_transfer=0)
    def timed(name, fn):
        def call(*a, **kw):
            start = time.perf_counter()
            try: return fn(*a, **kw)
            finally:
                phases[name] += time.perf_counter()-start
                counts[name] += 1
        return call
    wind.extract_city = timed('geometry', wind.extract_city)
    wind.prepare_domain = timed('domain', wind.prepare_domain)
    original_runner = _qes.WindRunner
    class Runner:
        def __init__(self):
            self.native = original_runner()
            self.prepare = timed('native_prepare', self.native.prepare)
            self.solve = timed('native_solve_and_transfer', self.native.solve)
    _qes.WindRunner = Runner
    # Measurement-only prototype using the existing complete wind.run result
    # path. No public abstraction is adopted until the predeclared gate passes.
    if args.kind == 'prototype':
        original_prepare = wind._prepare_city
        cached = []
        def prepare(*a, **kw):
            if not cached: cached.append(original_prepare(*a, **kw))
            return cached[0]
        wind._prepare_city = prepare
        runner = Runner()
        first_prepare = runner.prepare
        ready = []
        def native_prepare(*a, **kw):
            if not ready:
                first_prepare(*a, **kw)
                ready.append(True)
        runner.prepare = native_prepare
        _qes.WindRunner = lambda: runner
    control = None
    if args.mode == 'adaptive':
        control = wind.SolverControl(5, wind.MonitorSpec((20,130,20,145), receptors=tuple(
            wind.Receptor(f'p{i}-h{h}', x, y, h)
            for i,(x,y) in enumerate([(32,37),(52,59),(72,81),(92,103),(112,125)])
            for h in (1.5,1.75))), mode='adaptive')
    options = dict(bounds=(0,0,0,160,160,64))
    solve_options = dict(max_iterations=600 if control else 500, solver_control=control)
    records = []
    if args.memory:
        import tracemalloc
        tracemalloc.start()
    start = time.perf_counter()
    api_prepare = time.perf_counter()-start
    for direction in DIRECTIONS[:args.count]:
        result = wind.run(source, 5, direction, **options, **solve_options)
        sample_start = time.perf_counter()
        samples = [result.sample(h, method='linear') for h in (1.5,1.75)]
        phases['sampling'] += time.perf_counter()-sample_start
        arrays = {k:getattr(result,k) for k in ('velocity','cell_flags','x','y','z','z_faces')}
        for i, sample in enumerate(samples):
            arrays[f'sample{i}'] = sample.velocity
            arrays[f'valid{i}'] = sample.valid
        output_start = time.perf_counter()
        temporary = args.output.with_suffix('.npz')
        np.savez(temporary, **arrays)
        with temporary.open('rb') as stream: os.fsync(stream.fileno())
        phases['output'] += time.perf_counter()-output_start
        temporary.unlink()
        c = result.control
        records.append(dict(direction=direction, fields={k:dict(dtype=str(v.dtype),shape=list(v.shape),sha256=digest(v.tobytes())) for k,v in arrays.items()},
            diagnostics=asdict(result.diagnostics),
            control=None if c is None else {k:c[k] for k in ('accepted','accuracy_status','termination_reason','method','policy','assessment','assessment_history','checkpoint_history','counters','effective_monitor') if k in c},
            output_bytes=sum(v.nbytes for v in arrays.values())))
        del result, samples, arrays
    elapsed = time.perf_counter()-start
    allocation = None
    if args.memory:
        current, peak = tracemalloc.get_traced_memory()
        allocation = dict(traced_current_bytes=current,traced_peak_bytes=peak,
            live_traced_blocks=sum(stat.count for stat in tracemalloc.take_snapshot().statistics('filename')),
            scope='Python/NumPy traced allocations; native model/workspace excluded. Separate untimed worker.')
        tracemalloc.stop()
    # Measurement-only hooks in an explicitly separate, instrumented build.
    profile = _qes._s8a_profile() if hasattr(_qes,'_s8a_profile') else None
    write(args.output, dict(kind=args.kind,mode=args.mode,count=args.count,elapsed_seconds=elapsed,
        api_prepare_seconds=api_prepare,phases=phases,counts=counts,records=records,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform=='darwin' else 1024),
        native_module_sha256=digest(Path(_qes.__file__).read_bytes()),policy_revision=_qes.solver_policy_revision,
        allocation=allocation,native_profile=profile))


def study(args):
    args.output.mkdir(parents=True,exist_ok=False)
    protocol = dict(directions=DIRECTIONS,repetitions=3,modes=['legacy','adaptive'],counts=[4,8],
        primary_gate='8-direction median saving >=10% OR >=0.10 seconds, with neither 4-direction mode slower by >5%; exact fields, diagnostics and control decisions required.',
        worker_timeout_seconds=30,worker_limit=24,threads=4,dynamic=False,
        case='20 rectangular buildings, staggered heights 10..22m, passages, 160x160x64m at 2m; Uref=5m/s at 10m, z0=0.1m',
        end_to_end='City supplied in memory; include preparation once per series, all solves, owned outputs, linear 1.5/1.75m sampling and one uncompressed full-field NPZ with fsync per direction. Stream/discard outputs. Imports and city construction excluded.',
        attribution='Geometry extraction, Python domain planning, native preparation (including boundary coefficients/operator), native solve plus output transfer, sampling, output; native operator subphase requires a separately instrumented diagnostic build.',
        kind=args.kind)
    write(args.output/'protocol.json',protocol)
    all_results = {}
    for mode in protocol['modes']:
        for count in protocol['counts']:
            rows = {k:[] for k in ('fresh',args.kind)}
            for rep in range(3):
                for kind in (('fresh',args.kind) if rep%2==0 else (args.kind,'fresh')):
                    output=args.output/f'{mode}-{count}-{rep}-{kind}.json'
                    cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--kind',kind,'--mode',mode,'--count',str(count),'--output',str(output)]
                    result=subprocess.run(cmd,capture_output=True,text=True,timeout=30,env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
                    output.with_suffix('.log').write_text(result.stdout+result.stderr)
                    result.check_returncode()
                    rows[kind].append(json.loads(output.read_text()))
            expected=rows['fresh'][0]['records']
            parity=all(comparable(row['records'])==comparable(expected) for group in rows.values() for row in group)
            medians={k:statistics.median(r['elapsed_seconds'] for r in group) for k,group in rows.items()}
            all_results[f'{mode}-{count}']=dict(parity=parity,median_seconds=medians,saving_seconds=medians['fresh']-medians[args.kind],saving_fraction=1-medians[args.kind]/medians['fresh'],
                median_phases={k:{phase:statistics.median(r['phases'][phase] for r in group) for phase in group[0]['phases']} for k,group in rows.items()},
                maximum_peak_rss_bytes={k:max(r['peak_rss_bytes'] for r in group) for k,group in rows.items()})
            print(mode,count,json.dumps(all_results[f'{mode}-{count}']),flush=True)
    write(args.output/'summary.json',dict(worthwhile=worthwhile(all_results),series=all_results))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--kind',choices=['fresh','prototype'],default='prototype')
    ap.add_argument('--mode',choices=['legacy','adaptive'],default='legacy')
    ap.add_argument('--count',type=int,choices=[4,8],default=4)
    ap.add_argument('--worker',action='store_true')
    ap.add_argument('--memory',action='store_true',help='Trace allocations in a separate untimed worker')
    args=ap.parse_args()
    worker(args) if args.worker else study(args)
