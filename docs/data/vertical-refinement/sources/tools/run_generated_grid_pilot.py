"""Bounded C2c pilot: actual generated z at fixed 0.5 m x/y.

Freeze the public preview, source snapshots, references and acceptance contract
before solving. Historical studies and production kernels remain unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time

import numpy as np

from run_auto_grid_controls import HEIGHTS, POINTS, make_city, rectangles
from run_horizontal_sensitivity import array, comparison, digest, values
from run_joint_grid_verification import (BACKENDS, EXTRA_POINTS, atomic_json, execute,
    fingerprint, gate, input_text, local_checks, read, resource_estimate)

OUTPUT = Path('docs/data/generated-grid-pilot')
PROTOCOL = Path('docs/generated-grid-pilot.md')


def tasks():
    # Larger case first; only one worker per backend, at most two overall.
    return [dict(id=f'generated/{extent}/270/0.5', family='generated',
                 direction=270, resolution=.5, extent=extent, precision='float64')
            for extent in (240, 160)]


def plans():
    from dtcc_qes import wind
    city = make_city(rectangles('tower'))
    previews = {}
    for task in tasks():
        e = task['extent']; origin = (80-e)/2
        start = time.perf_counter()
        preview = wind.preview_grid(city, resolution=.5,
            bounds=(origin, origin, 0, origin+e, origin+e, 64),
            vertical_grid=wind.VerticalGrid.auto(pedestrian_height=1.5), max_cells=40000000)
        seconds = time.perf_counter()-start
        metadata = preview.domain['vertical_grid']
        layers = np.diff(metadata['planned_faces'])
        np.testing.assert_array_equal(layers.astype(np.float32), preview.solver_dz.astype(np.float32))
        previews[str(e)] = dict(metadata=metadata, shape=list(preview.shape),
            cell_count=preview.cell_count, preview_seconds=seconds,
            layers_input=layers.tolist(), expected_faces=preview.z_faces.tolist())
    if previews['160']['layers_input'] != previews['240']['layers_input']:
        raise ValueError('Lateral control must preserve every generated vertical operand')
    return {'generated': previews['160']}, previews


def reference_data(hashes=None):
    docs = {}
    paths = [Path('docs/data/joint-grid-verification')/b/'raw.json.gz' for b in BACKENDS]
    paths += [Path('docs/data/joint-grid-verification')/b/'summary.json' for b in BACKENDS]
    paths += [Path('docs/data/joint-grid-verification')/b/'manifest.json' for b in BACKENDS]
    actual = {str(p): digest(p) for p in paths}
    if hashes is not None and actual != hashes:
        raise ValueError('Historical reference fingerprints changed')
    for backend in BACKENDS:
        doc = read(paths[list(BACKENDS).index(backend)])
        expected = {f'joint/{e}/uniform-0.5/270/0.5' for e in (160,240)}
        runs = [r for r in doc['runs'] if r['task']['id'] in expected]
        if len(runs) != 2 or {r['task']['id'] for r in runs} != expected:
            raise ValueError('Uniform reference matrix incomplete')
        for run in runs:
            if (not gate(run)['accepted'] or run['backend'] != BACKENDS[backend]
                    or run['precision'] != 'float64' or run['start'] != 'zero'
                    or run['disabled_mask'] != 0):
                raise ValueError('Uniform reference scope or solve gate mismatch')
            np.testing.assert_array_equal(run['z_faces'], np.arange(129)*.5)
        docs[backend] = doc
    return docs, actual


def frozen_indices(reference, height, region):
    frozen = reference['metadata']['frozen_critical_indices']
    # Keep BOTH originally frozen critical sets when crossing vertical families.
    return sorted(set(frozen[f'{f}/270/{height}/{region}'][i]
        for f in ('auto','uniform-0.5') for i in range(len(frozen[f'{f}/270/{height}/{region}']))))


def compare_pair(a, b, reference, label):
    rows = []
    accepted = gate(a)['accepted'] and gate(b)['accepted']
    for height in HEIGHTS:
        for region in ('all','away4m'):
            row = dict(comparison=label, height=height, region=region, matched_accuracy=accepted)
            if accepted:
                row.update(comparison(a,b,height,frozen_indices(reference,height,region),region))
                row['regional_within_budget'] = bool(row['within_budget'] and row['solid_fluid_transitions']==0)
                # These are full-region checks, not members of the setback region.
                if region == 'all':
                    row['mandatory_local_checks'] = local_checks(a,b,height)
                    row['combined_within_budget'] = bool(row['regional_within_budget'] and
                        all(p['within_budget'] for p in row['mandatory_local_checks']))
            else:
                row['withheld_reason'] = 'Failed common residual/stability gate'
            rows.append(row)
    return rows


def collect(root, manifest):
    result = {}
    for backend in BACKENDS:
        runs, attempts = [], []
        for task in tasks():
            path = root/backend/'cases'/(task['id']+'.json.gz')
            if not path.exists(): continue
            record = read(path)
            if record['study_identity'] != fingerprint(manifest):
                raise ValueError('Case identity mismatch')
            if record['run'] is not None:
                if record['run']['task'] != task or record['accepted'] != gate(record['run'])['accepted']:
                    raise ValueError('Case task or acceptance mismatch')
                runs.append(record['run'])
            attempts.extend(record['attempts'])
        result[backend] = dict(runs=runs,attempts=attempts)
    return result


def summarize(documents, references):
    result = dict(backends={},cross_backend=[],complete=True,vertical_pilot_pass=False,
        comfort_qualified=False,scope='Fixed-x/y vertical discretization only; historical horizontal failures retained')
    for backend, doc in documents.items():
        available = {r['task']['extent']:r for r in doc['runs']}
        complete = len(doc['runs'])==2 and set(available)=={160,240}
        if len(available)!=len(doc['runs']): raise ValueError('Duplicate pilot cases')
        result['complete'] &= complete
        refs = {r['task']['extent']:r for r in references[backend]['runs']
                if r['task']['family']=='uniform-0.5' and r['direction']==270}
        rows = []
        for extent, run in available.items():
            rows.extend(compare_pair(run,refs[extent],references[backend],f'vertical_at_{extent}'))
        if complete:
            rows.extend(compare_pair(available[160],available[240],references[backend],'generated_extent_160_to_240'))
        costs = []
        for extent, run in available.items():
            ref=refs[extent]
            costs.append(dict(extent=extent,**gate(run),cells=run['cells'],
                reference_cells=ref['cells'],cell_reduction=1-run['cells']/ref['cells'],
                roof_errors=run['roof_errors'],reference_roof_errors=ref['roof_errors'],
                peak_rss_bytes=run['peak_rss_bytes'],reference_peak_rss_bytes=ref['peak_rss_bytes'],
                certification_solve_seconds=sum(c['solve_seconds'] for c in run['checkpoints']),
                final_solve_seconds=run['checkpoints'][-1]['solve_seconds'],
                final_sweeps=run['checkpoints'][-1]['iterations'],
                reference_final_solve_seconds=ref['checkpoints'][-1]['solve_seconds'],
                reference_final_sweeps=ref['checkpoints'][-1]['iterations'],
                runtime_ratio_claim=False))
        full=[r for r in rows if r['region']=='all']
        result['backends'][backend]=dict(complete=complete,runs=costs,comparisons=rows,
            pilot_pass=bool(complete and len(full)==6 and all(r.get('combined_within_budget',False) for r in full)))
    aa={r['task']['extent']:r for r in documents['serial']['runs']}
    bb={r['task']['extent']:r for r in documents['openmp']['runs']}
    for extent in sorted(aa.keys() & bb.keys()):
        a,b=aa[extent],bb[extent]
        for attr in ('initial_planes','profile_planes','sample_x','sample_y','z_faces','roof_errors'):
            if a[attr]!=b[attr]: raise ValueError('CPU initial/support disagreement')
        if not (gate(a)['accepted'] and gate(b)['accepted']): continue
        for height in HEIGHTS:
            av,bv=[array(values(r,height)) for r in (a,b)]
            am,bm=[np.isfinite(v).all(axis=1) for v in (av,bv)]
            np.testing.assert_array_equal(am,bm)
            delta=np.linalg.norm(av[am]-bv[bm],axis=1)/5
            result['cross_backend'].append(dict(extent=extent,height=height,
                max_vector_difference_over_Uref=float(delta.max()),
                p95_vector_difference_over_Uref=float(np.percentile(delta,95))))
    decisions=[[(r['comparison'],r['height'],r['region'],r['matched_accuracy'],
                 r.get('regional_within_budget'),r.get('combined_within_budget'))
                for r in result['backends'][b]['comparisons']] for b in BACKENDS]
    result['cpu_decisions_equal']=decisions[0]==decisions[1]
    result['cpu_fields_within_stability_budget']=bool(len(result['cross_backend'])==4 and all(
        r['max_vector_difference_over_Uref']<=1e-3 and r['p95_vector_difference_over_Uref']<=5e-4
        for r in result['cross_backend']))
    result['vertical_pilot_pass']=bool(result['complete'] and result['cpu_decisions_equal'] and
        result['cpu_fields_within_stability_budget'] and all(r['pilot_pass'] for r in result['backends'].values()))
    return result


def freeze(root):
    if (root/'manifest.json').exists(): raise ValueError('Manifest already exists; use --resume')
    references, hashes = reference_data()
    configs, previews = plans()
    sources = [Path(__file__).relative_to(Path.cwd()) if Path(__file__).is_absolute() else Path(__file__),
        Path('tests/test_generated_grid_pilot.py'),Path('CMakeLists.txt')]
    sources += [Path('tools')/name for name in ('run_joint_grid_verification.py',
        'run_precision_verification.py','run_horizontal_sensitivity.py','run_auto_grid_controls.py',
        'run_vertical_grid_study.py','vertical_grid_study.cpp','vertical_grid_diagnostics.cpp','vertical_grid_diagnostics.h')]
    sources += sorted(Path('src/cpp').glob('*.*'))+sorted(Path('src/dtcc_qes').glob('*.py'))+[Path('src/dtcc_qes/_qes_revision.txt')]
    binaries={}
    for backend in BACKENDS:
        old=read(Path('docs/data/joint-grid-verification')/backend/'manifest.json')['metadata']
        executable=Path(old['executable'])
        if digest(executable)!=old['executable_sha256']: raise ValueError('Historical worker changed')
        for source,sha in old['source_sha256'].items():
            if digest(source)!=sha: raise ValueError(f'Historical worker source changed: {source}')
        binaries[backend]=dict(path=str(executable),sha256=digest(executable))
    estimates={t['id']:resource_estimate(t,configs) for t in tasks()}
    manifest=dict(schema='generated-grid-pilot-v1',utc=datetime.now(timezone.utc).isoformat(),
        configurations=configs,previews=previews,tasks=tasks(),binaries=binaries,
        source_sha256={str(p):digest(p) for p in sources},references_sha256=hashes,
        protocol_sha256=digest(PROTOCOL),resources=estimates,cell_target=20000000,allocation_ceiling=40000000,
        initial_n={'serial':{'160':4000,'240':8000},'openmp':{'160':8000,'240':8000}},max_n=16000,
        maximum_workers=2,workers_per_backend=1,points=POINTS.tolist(),heights=list(HEIGHTS),
        extra_points=EXTRA_POINTS,platform=platform.platform(),numpy=np.__version__,
        scope='One generated policy; tower/270; fixed x/y=.5; no tuning or comfort qualification')
    root.mkdir(parents=True,exist_ok=True)
    for source in sources:
        target=root/'sources'/source; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
    shutil.copyfile(PROTOCOL,root/'protocol.md')
    atomic_json(root/'manifest.json',manifest)
    return manifest,references


def verify_frozen(root, manifest, execution=False):
    if digest(root/'protocol.md')!=manifest['protocol_sha256']: raise ValueError('Protocol changed')
    for name,sha in manifest['source_sha256'].items():
        if digest(root/'sources'/name)!=sha: raise ValueError('Source snapshot changed')
        if execution and digest(name)!=sha: raise ValueError('Active source changed; choose a new study directory')
    if execution:
        for binary in manifest['binaries'].values():
            if digest(binary['path'])!=binary['sha256']: raise ValueError('Worker changed')


def write_summary(root, manifest, references):
    doc=collect(root,manifest)
    atomic_json(root/'raw.json.gz',doc)
    result=summarize(doc,references)
    atomic_json(root/'summary.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--summarize',action='store_true')
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args(); root=args.output
    if args.resume or args.summarize:
        manifest=read(root/'manifest.json'); verify_frozen(root,manifest,execution=not args.summarize)
        references,_=reference_data(manifest['references_sha256'])
    else:
        manifest,references=freeze(root)
    write_summary(root,manifest,references)
    if args.summarize or args.freeze_only: return
    def backend_work(backend):
        existing={r['task']['id'] for r in collect(root,manifest)[backend]['runs']}
        for task in tasks():
            if task['id'] in existing: continue
            execute(task,manifest['configurations'],Path(manifest['binaries'][backend]['path']),BACKENDS[backend],
                manifest['initial_n'][backend][str(task['extent'])],manifest['max_n'],
                manifest['allocation_ceiling'],root/backend,fingerprint(manifest))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(backend_work,b) for b in BACKENDS]
        for future in as_completed(futures):
            future.result(); write_summary(root,manifest,references)
    result=write_summary(root,manifest,references)
    print('COMPLETE',result['complete'],'VERTICAL PILOT PASS',result['vertical_pilot_pass'],flush=True)


if __name__=='__main__':
    main()
