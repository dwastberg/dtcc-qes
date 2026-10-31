"""Bounded float32 API comparison of generated and uniform vertical grids.

Freeze before execution; retain every case, including timeouts. Saved-data audit
needs NumPy and frozen analysis sources, without an installed QES extension.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
from time import perf_counter

import numpy as np

from run_auto_grid_controls import HEIGHTS, make_city, rectangles
from run_horizontal_sensitivity import array, audit_point, comparison, digest, values
from run_joint_grid_verification import atomic_json, fingerprint, read
from run_precision_verification import gate

OUTPUT = Path('docs/data/practical-vertical-grid')
MANDATORY = [[27, 21], [21, 23], [51, 35], [15, 47], [15, 29]]
SOURCES = ['run_practical_vertical_grid.py', 'run_auto_grid_controls.py',
    'run_horizontal_sensitivity.py', 'run_joint_grid_verification.py',
    'run_precision_verification.py', 'run_vertical_grid_study.py']
TARGETS = dict(p95_abs_delta_K=.01, p95_vector_error_over_Uref=.01,
               critical_relative=.02, critical_low_K_absolute=.005, low_K_threshold=.1)


def tasks():
    return [dict(id=f'{family}-{iterations}', family=family, iterations=iterations)
            for iterations in (1000, 2000) for family in ('generated', 'uniform')]


def numeric_check(actual, reference, targets=TARGETS):
    if actual is None or reference is None:
        return dict(valid=False, within_budget=False)
    delta = abs(actual-reference)
    appreciable = reference >= targets['low_K_threshold']
    return dict(valid=True, K=actual, reference_K=reference, abs_delta_K=delta,
        relative_error=delta/reference if appreciable else None,
        within_budget=bool(delta <= (targets['critical_relative']*reference
                          if appreciable else targets['critical_low_K_absolute'])))


def error_metrics(actual, reference, critical, targets=TARGETS):
    a, b = array(actual), array(reference)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3:
        raise ValueError('Mismatched velocity support')
    am, bm = np.isfinite(a).all(axis=1), np.isfinite(b).all(axis=1)
    valid = am & bm
    if not valid.any():
        raise ValueError('No common valid support')
    ak, bk = np.linalg.norm(a, axis=1)/5, np.linalg.norm(b, axis=1)/5
    speed = np.abs(ak[valid]-bk[valid])
    vector = np.linalg.norm(a[valid]-b[valid], axis=1)/5
    # Include both pair-local peaks as well as the previously frozen locations.
    peak_a = int(np.argmax(np.where(am, ak, -np.inf)))
    peak_b = int(np.argmax(np.where(bm, bk, -np.inf)))
    ids = sorted(set(critical) | {peak_a, peak_b})
    checks = [dict(index=i, **numeric_check(float(ak[i]) if am[i] else None,
                                           float(bk[i]) if bm[i] else None, targets)) for i in ids]
    return dict(common_fluid_points=int(valid.sum()), validity_changes=int((am != bm).sum()),
        p95_abs_delta_K=float(np.percentile(speed, 95)), max_abs_delta_K=float(speed.max()),
        p95_vector_error_over_Uref=float(np.percentile(vector, 95)),
        max_vector_error_over_Uref=float(vector.max()), critical_checks=checks,
        candidate_lattice_budget_met=bool(not np.any(am != bm)
            and np.percentile(speed, 95) <= targets['p95_abs_delta_K']
            and np.percentile(vector, 95) <= targets['p95_vector_error_over_Uref']
            and all(c['within_budget'] for c in checks)))


def reference_set():
    paths = dict(generated=Path('docs/data/generated-grid-pilot/raw.json.gz'),
                 uniform=Path('docs/data/joint-grid-verification/openmp/raw.json.gz'))
    generated, joint = [read(paths[k]) for k in ('generated', 'uniform')]
    runs = dict(generated=next(r for r in generated['serial']['runs'] if r['task']['extent']==160),
        uniform=next(r for r in joint['runs'] if r['task']['extent']==160
                     and r['direction']==270 and r['task']['family']=='uniform-0.5'))
    for r in runs.values():
        if not gate(r)['accepted'] or r['start']!='zero' or r['precision']!='float64':
            raise ValueError('Unqualified same-grid reference')
    frozen=joint['metadata']['frozen_critical_indices']
    critical = {str(h): sorted(set(frozen[f'auto/270/{h}/all']) |
                              set(frozen[f'uniform-0.5/270/{h}/all'])) for h in HEIGHTS}
    return dict(runs=runs, critical_indices=critical,
        origins={k:dict(path=str(p), sha256=digest(p), selected_run_sha256=fingerprint(runs[k]))
                 for k,p in paths.items()})


def freeze(root):
    from dtcc_qes import _qes
    if root.exists():
        raise ValueError('Use a new output directory; existing evidence is read-only')
    if not _qes.openmp_enabled or _qes.build_type != 'Release':
        raise ValueError('Require a Release OpenMP extension')
    refs=reference_set()
    root.mkdir(parents=True)
    atomic_json(root/'references.json.gz', refs)
    sources = [Path('tools')/p for p in SOURCES]
    sources += sorted(Path('src/cpp').glob('*.*'))+sorted(Path('src/dtcc_qes').glob('*.py'))
    sources += [Path('src/dtcc_qes/_qes_revision.txt'), Path('CMakeLists.txt'),
                Path('tests/test_practical_vertical_grid.py')]
    for source in sources:
        dest=root/'sources'/source
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
    protocol = dict(schema='practical-vertical-grid-v1', utc=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(), python=sys.version, numpy=np.__version__, cpu_count=os.cpu_count(),
        threads=4, precision='float32', tolerance=1e-5, tasks=tasks(),
        per_worker_seconds=30, total_matrix_seconds=140, automatic_retry=False,
        resolution=.5, bounds=[-40,-40,0,120,120,64], Uref=5, direction=270, reference_height=10,
        roughness_length=.1, heights=list(HEIGHTS), mandatory_points=MANDATORY,
        allocation_guard=40000000, cell_target=20000000, targets=TARGETS,
        geometry=rectangles('tower'), reference_extract_sha256=digest(root/'references.json.gz'),
        source_sha256={str(p):digest(p) for p in sources}, extension_sha256=digest(_qes.__file__),
        qes_revision=_qes.qes_revision, legacy_reference_gate_unchanged=True,
        scope='Fixed x/y, one tower/wind, candidate iterative-error budgets on the common lattice. '
              'No calibrated production mass threshold, physical comfort qualification or preset selection.',
        timing_scope='API includes preparation, solve, diagnostics, full-volume output; '
                     'imports, City creation, reference reads and sampling excluded. Worker cap includes all.',
        initial_field_qualification='Single-sensor profile is horizontally uniform; reference sensor at '
                     'world (5,5), public position retained in metadata; initial equality not directly measured.')
    atomic_json(root/'protocol.json',protocol)
    return protocol


def verify(root, execution=False):
    protocol=read(root/'protocol.json')
    for name,sha in protocol['source_sha256'].items():
        if digest(root/'sources'/name)!=sha or (execution and digest(name)!=sha):
            raise ValueError(f'Source identity changed: {name}')
    if digest(root/'references.json.gz') != protocol['reference_extract_sha256']:
        raise ValueError('Reference extract changed')
    refs=read(root/'references.json.gz')
    for family,r in refs['runs'].items():
        if fingerprint(r)!=refs['origins'][family]['selected_run_sha256'] or not gate(r)['accepted']:
            raise ValueError('Reference content or gate changed')
    if execution:
        from dtcc_qes import _qes
        if digest(_qes.__file__)!=protocol['extension_sha256']:
            raise ValueError('Native extension changed')
    return protocol,refs


def worker(root, task):
    from dtcc_qes import wind, _qes
    protocol,refs=verify(root,execution=True)
    reference=refs['runs'][task['family']]
    city=make_city(protocol['geometry'])
    spec=(wind.VerticalGrid.auto() if task['family']=='generated' else
          wind.VerticalGrid.from_faces(np.arange(129)*.5))
    start=perf_counter()
    result=wind.run(city,5,270,resolution=.5,bounds=protocol['bounds'],vertical_grid=spec,
        max_cells=protocol['allocation_guard'],solver_precision='float32',
        tolerance=protocol['tolerance'],max_iterations=task['iterations'])
    api_seconds=perf_counter()-start
    np.testing.assert_array_equal(result.z_faces,np.asarray(reference['z_faces'],np.float32))
    x,y=result.x.astype(float)+result.origin[0],result.y.astype(float)+result.origin[1]
    sx,sy=np.asarray(reference['sample_x']),np.asarray(reference['sample_y'])
    ix,iy=np.searchsorted(x,sx),np.searchsorted(y,sy)
    np.testing.assert_array_equal(x[ix],sx); np.testing.assert_array_equal(y[iy],sy)
    planes=[]
    for h in HEIGHTS:
        sample=result.sample(h,method='linear')
        velocity=sample.velocity[iy[:,None],ix[None,:]].reshape(-1,3)
        valid=sample.valid[iy[:,None],ix[None,:]].ravel()
        planes.append(dict(height=h,velocity=[v.tolist() if ok else None for v,ok in zip(velocity,valid)]))
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(task=task,protocol_sha256=digest(root/'protocol.json'),api_seconds=api_seconds,
        peak_process_rss_bytes=int(rss if sys.platform=='darwin' else rss*1024),
        precision=result.diagnostics.precision,backend=_qes.cpu_backend,openmp_enabled=_qes.openmp_enabled,
        requested_threads=os.environ.get('OMP_NUM_THREADS'),actual_threads_measured=False,
        cells=int(np.prod(result.velocity.shape[:3])),shape=list(result.velocity.shape[:3]),
        sample_x=sx.tolist(),sample_y=sy.tolist(),z_faces=result.z_faces.tolist(),
        checkpoints=[dict(planes=planes)],metadata=result.metadata,diagnostics=asdict(result.diagnostics))


def analyze_case(run, reference, critical, targets):
    rows=[]
    for h in HEIGHTS:
        row=error_metrics(values(run,h),values(reference,h),critical[str(h)],targets)
        checks=[]
        for point in MANDATORY:
            a,b=[audit_point(r,h,point,'final') for r in (run,reference)]
            checks.append(dict(point=point,**numeric_check(a['K'] if a['valid'] else None,
                                                 b['K'] if b['valid'] else None,targets)))
        rows.append(dict(height=h,**row,mandatory_checks=checks,
            candidate_error_budget_met=bool(row['candidate_lattice_budget_met']
                                           and all(c['within_budget'] for c in checks))))
    diagnostics=run['diagnostics']
    scale=23.7/5
    return dict(task=run['task'],api_seconds=run['api_seconds'],cells=run['cells'],
        peak_process_rss_bytes=run['peak_process_rss_bytes'],diagnostics=diagnostics,comparisons=rows,
        candidate_error_budget_met=all(r['candidate_error_budget_met'] for r in rows),
        reference_residual_bounds_met_at_this_iterate=bool(
            diagnostics['max_divergence'] is not None and diagnostics['rms_divergence'] is not None
            and diagnostics['max_divergence']*scale <= 1e-3
            and diagnostics['rms_divergence']*scale <= 1e-4),
        strict_reference_certified=False,comfort_qualified=False)


def vertical_pair(a,b,critical):
    rows=[]
    for h in HEIGHTS:
        row=comparison(a,b,h,critical[str(h)])
        checks=[]
        targets=dict(TARGETS,critical_relative=.05,critical_low_K_absolute=.05)
        for point in MANDATORY:
            aa,bb=[audit_point(r,h,point,'final') for r in (a,b)]
            checks.append(dict(point=point,**numeric_check(aa['K'] if aa['valid'] else None,
                                                     bb['K'] if bb['valid'] else None,targets)))
        rows.append(dict(**row,mandatory_checks=checks,expanded_spatial_budget_met=bool(
            row['within_budget'] and row['solid_fluid_transitions']==0
            and all(c['within_budget'] for c in checks))))
    return rows


def summarize(root,protocol,refs,executions):
    rows=[]; completed={}
    for execution in executions:
        if execution['status']!='completed':
            rows.append(execution); continue
        path=root/'cases'/(execution['task']['id']+'.json.gz')
        if digest(path)!=execution['record_sha256']:
            raise ValueError('Case content changed')
        run=read(path)
        if run['task']!=execution['task'] or run['protocol_sha256']!=digest(root/'protocol.json'):
            raise ValueError('Case identity changed')
        ref=refs['runs'][run['task']['family']]
        np.testing.assert_array_equal(run['z_faces'],np.asarray(ref['z_faces'],np.float32))
        for axis in ('sample_x','sample_y'):
            if run[axis]!=ref[axis]: raise ValueError('Sampling coordinates changed')
        rows.append(execution | analyze_case(run,ref,refs['critical_indices'],protocol['targets']))
        completed[run['task']['id']]=run
    pairs=[]
    for n in (1000,2000):
        if all(f'{f}-{n}' in completed for f in ('generated','uniform')):
            a,b=[completed[f'{f}-{n}'] for f in ('generated','uniform')]
            pairs.append(dict(iterations=n,comparisons=vertical_pair(a,b,refs['critical_indices']),
                observed_uniform_to_generated_api_ratio=b['api_seconds']/a['api_seconds'],
                timing_repeats=1,universal_speedup_claim=False))
    return dict(scope=protocol['scope'],complete=len(executions)==len(tasks()),runs=rows,
        same_budget_vertical_pairs=pairs,
        accepted_reference_vertical_pair=vertical_pair(refs['runs']['generated'],refs['runs']['uniform'],
                                                     refs['critical_indices']),
        cell_reduction=1-refs['runs']['generated']['cells']/refs['runs']['uniform']['cells'],
        automatic_preset_selected=False,comfort_qualified=False,
        next_decision='Review runtime, iterative errors and retained spatial failures before broader C2 or B2.')


def audit(root):
    protocol,refs=verify(root)
    executions=read(root/'executions.json')
    if [e['task'] for e in executions]!=protocol['tasks']:
        raise ValueError('Execution matrix differs from frozen protocol')
    summary=summarize(root,protocol,refs,executions)
    if summary!=read(root/'summary.json'):
        raise ValueError('Summary does not reproduce')
    return dict(integrity_pass=True,requires_native_extension=False,
        protocol_sha256=digest(root/'protocol.json'),summary_sha256=digest(root/'summary.json'),
        completed_cases=sum(e['status']=='completed' for e in executions),
        timed_out_cases=sum(e['status']=='timeout' for e in executions),
        automatic_preset_selected=False,comfort_qualified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--worker')
    parser.add_argument('--audit',action='store_true')
    args=parser.parse_args(); root=args.output
    if args.audit:
        print(json.dumps(audit(root),indent=2)); return
    if args.worker:
        task=next(t for t in tasks() if t['id']==args.worker)
        atomic_json(root/'cases'/(task['id']+'.json.gz'),worker(root,task)); return
    protocol=freeze(root); executions=[]; start=perf_counter()
    for task in protocol['tasks']:
        remaining=protocol['total_matrix_seconds']-(perf_counter()-start)
        if remaining <= 0:
            executions.append(dict(task=task,status='skipped_total_budget')); continue
        command=[str(Path(sys.executable).absolute()),str(Path(__file__).absolute()),
                 '--output',str(root.absolute()),'--worker',task['id']]
        case_start=perf_counter()
        with (root/(task['id']+'.log')).open('w') as log:
            try:
                subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,
                    timeout=min(protocol['per_worker_seconds'],remaining),
                    env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
                record=root/'cases'/(task['id']+'.json.gz')
                row=dict(task=task,status='completed',record_sha256=digest(record))
            except subprocess.TimeoutExpired:
                row=dict(task=task,status='timeout')
            except subprocess.CalledProcessError as e:
                row=dict(task=task,status='failed',exit_code=e.returncode)
        row['process_seconds']=perf_counter()-case_start
        executions.append(row); atomic_json(root/'executions.json',executions)
        print(row,flush=True)
    atomic_json(root/'executions.json',executions)
    _,refs=verify(root)
    atomic_json(root/'summary.json',summarize(root,protocol,refs,executions))
    atomic_json(root/'audit.json',audit(root))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    main()
