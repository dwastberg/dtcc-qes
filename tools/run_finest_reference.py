"""One predeclared 40k/80k/160k zero-start finest-grid certification."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

import numpy as np
import run_vertical_refinement as prior
from run_joint_grid_verification import validate_checkpoint

OUTPUT = Path('docs/data/finest-reference')
PROTOCOL = Path('docs/finest-reference.md')
PARENT = Path('docs/data/vertical-refinement')
SWEEPS = [40000, 80000, 160000]


def command(manifest):
    task = manifest['task']
    return [manifest['binary']['path'], 'tower', '--horizontal', str(task['direction']),
            str(SWEEPS[0]), '--float64', '--max-cells', str(manifest['allocation_ceiling'])]


def references(manifest):
    for path, sha in manifest['references_sha256'].items():
        if prior.digest(path) != sha: raise ValueError(f'Reference changed: {path}')
    docs = prior.read(PARENT/'raw.json.gz')
    refs, _ = prior.reference_data()
    old = {r['task']['family']: r for r in docs['openmp']['runs']}
    if set(old) != set(prior.FAMILIES): raise ValueError('Missing parent case')
    if prior.gate(old['split-4'])['accepted']: raise ValueError('Expected historical failed finest certification')
    for family in ('split-2', 'aligned-1.75'):
        if not prior.gate(old[family])['accepted']: raise ValueError('Unaccepted comparison reference')
    return refs, old


def validate(run, manifest):
    if run['task'] != manifest['task'] or run['threads'] != 2:
        raise ValueError('Task/thread scope mismatch')
    if [c['iterations'] for c in run['checkpoints']] != SWEEPS:
        raise ValueError('Require exactly three distinct predeclared zero-start budgets')
    configs = manifest['configurations']
    for checkpoint in run['checkpoints']:
        single = run | {'checkpoints': [checkpoint]}
        # finest-reference-v1 is a frozen pre-S2 execution/allocation contract.
        validate_checkpoint(single, manifest['task'], configs, prior.BACKENDS['openmp'], checkpoint['iterations'],
                            workspace_layout="legacy")
        for plane in checkpoint['planes']:
            initial = next(p for p in run['initial_planes'] if p['height'] == plane['height'])
            if plane['flags'] != initial['flags']: raise ValueError('Occupancy changed during solve')
        for height in prior.HEIGHTS:
            for point in prior.LOCATIONS:
                for stage in ('profile', 'initial', 'final'):
                    prior.audit_point(single, height, point, stage)
    expected = [r['error'] for r in configs['split-4']['metadata']['roof_representation']]
    np.testing.assert_allclose(run['roof_errors'], expected, rtol=0, atol=2e-8)
    prior.gate(run)


def summarize(run, refs, old):
    # Keep historical failures; only replace the uncertified finest in new comparisons.
    available = {'base': refs['openmp']['base'], **old, 'split-4': run}
    pairs = [('base','split-2','base_to_2'), ('split-2','split-4','2_to_4'),
             ('base','split-4','base_to_4'), ('aligned-1.75','base','alignment_to_base'),
             ('aligned-1.75','split-4','alignment_to_4')]
    rows = [row for a,b,label in pairs for row in prior.compare_pair(
        available[a], available[b], refs['openmp']['joint'], label)]
    full = [r for r in rows if r['region']=='all']
    return dict(complete=True, solve=prior.gate(run), comparisons=rows,
        vertical_sensitivity_budget_pass=all(r.get('combined_within_budget',False) for r in full
            if r['comparison'] in ('base_to_2','2_to_4','base_to_4')),
        alignment_budget_pass=all(r.get('combined_within_budget',False) for r in full
            if r['comparison'].startswith('alignment_')),
        comfort_qualified=False, preset_selected=False,
        scope='One fixed-x/y tower/wind; preserves historical failures, no convergence-order assumption')


def verify(root, manifest, execution=False):
    prior.verify_frozen(root, manifest)
    if manifest['sweeps'] != SWEEPS: raise ValueError('Frozen sweep contract mismatch')
    if manifest['command'] != command(manifest): raise ValueError('Worker mode mismatch')
    text = prior.input_text(manifest['task'], manifest['configurations'])
    if hashlib.sha256(text.encode()).hexdigest() != manifest['input_sha256']:
        raise ValueError('Input identity mismatch')
    if (root/'input.txt').read_text() != text: raise ValueError('Saved stdin differs')
    if execution:
        for path, sha in manifest['source_sha256'].items():
            if prior.digest(path) != sha: raise ValueError(f'Active source changed: {path}')
        if prior.digest(manifest['binary']['path']) != manifest['binary']['sha256']:
            raise ValueError('Worker changed')


def freeze(root):
    if (root/'manifest.json').exists(): raise ValueError('Manifest exists; use --resume')
    old = prior.read(PARENT/'manifest.json')
    prior.verify_frozen(PARENT, old, execution=True)
    task = next(t for t in old['task_matrix']['openmp'] if t['family']=='split-4')
    paths = set(old['references_sha256']) | {str(PARENT/name) for name in
        ('manifest.json','raw.json.gz','summary.json','audit.json','initialization.json')}
    sources = set(old['source_sha256']) | {'tools/run_vertical_refinement.py',
        'tools/run_finest_reference.py','tests/test_finest_reference.py'}
    text = prior.input_text(task, old['configurations'])
    manifest = dict(schema='finest-reference-v1', utc=datetime.now(timezone.utc).isoformat(),
        task=task, configurations=old['configurations'], sweeps=SWEEPS,
        binary=old['binaries']['openmp'], source_sha256={p:prior.digest(p) for p in sorted(sources)},
        references_sha256={p:prior.digest(p) for p in sorted(paths)},
        input_sha256=hashlib.sha256(text.encode()).hexdigest(), protocol_sha256=prior.digest(PROTOCOL),
        allocation_ceiling=40000000, cell_target=20000000, workers=1, threads=2,
        resource=old['resources']['split-4'], platform=platform.platform(), numpy=np.__version__,
        hardware_memory_bytes=os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE'),
        timing_scope='Single shared-host execution; elapsed timings do not establish speedups')
    manifest['command'] = command(manifest)
    if manifest['resource']['physical_cells'] > manifest['allocation_ceiling']:
        raise ValueError('Allocation guard exceeded')
    references(manifest)
    root.mkdir(parents=True, exist_ok=True)
    for name in sources:
        dest=root/'sources'/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(name,dest)
    shutil.copyfile(PROTOCOL,root/'protocol.md')
    (root/'input.txt').write_text(text)
    prior.atomic_json(root/'manifest.json',manifest)
    return manifest


def audit(root):
    manifest=prior.read(root/'manifest.json');verify(root,manifest)
    refs,old=references(manifest)
    saved=prior.read(root/'execution.json.gz')
    if saved['study_identity'] != prior.fingerprint(manifest) or saved['run_sha256'] != prior.fingerprint(saved['run']):
        raise ValueError('Execution identity/content mismatch')
    if saved['command'] != manifest['command']: raise ValueError('Executed command mismatch')
    run=saved['run'];validate(run,manifest)
    # Same native operands and initial state as the previous zero-start finest runs.
    for key in ('initial_planes','profile_planes','sample_x','sample_y','z_faces','roof_errors','horizontal_bounds'):
        if run[key] != old['split-4'][key]: raise ValueError(f'Historical finest state differs: {key}')
    result=summarize(run,refs,old)
    if result != prior.read(root/'summary.json'): raise ValueError('Summary does not reproduce')
    result=dict(complete=True, accepted=result['solve']['accepted'],
        vertical_sensitivity_budget_pass=result['vertical_sensitivity_budget_pass'],
        alignment_budget_pass=result['alignment_budget_pass'],comfort_qualified=False,preset_selected=False,
        requires_worker_executable=False, unique_executions=1, unique_zero_start_checkpoints=3,
        executed_cell_sweeps=run['cells']*sum(SWEEPS), peak_rss_bytes=run['peak_rss_bytes'],
        preparation_seconds=run['prep_seconds'], solve_seconds=sum(c['solve_seconds'] for c in run['checkpoints']),
        elapsed_seconds=saved['elapsed_seconds'],
        manifest_sha256=prior.digest(root/'manifest.json'),execution_sha256=prior.digest(root/'execution.json.gz'),
        summary_sha256=prior.digest(root/'summary.json'))
    prior.atomic_json(root/'audit.json',result)
    print(json.dumps(result,indent=2),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();root=args.output
    manifest=prior.read(root/'manifest.json') if args.resume else freeze(root)
    verify(root,manifest,execution=True);refs,old=references(manifest)
    if args.freeze_only:return
    path=root/'execution.json.gz'
    if not path.exists():
        started=datetime.now(timezone.utc).isoformat();t=time.monotonic()
        print('START', started, 'sweeps', SWEEPS, 'cells',manifest['resource']['physical_cells'],flush=True)
        proc=subprocess.run(command(manifest),input=(root/'input.txt').read_text(),text=True,
            capture_output=True,check=True,timeout=86400)
        if proc.stderr:raise ValueError(proc.stderr)
        run=json.loads(proc.stdout) | {'task':manifest['task']};validate(run,manifest)
        prior.atomic_json(path,dict(study_identity=prior.fingerprint(manifest),command=command(manifest),
            start_utc=started,end_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-t,
            run_sha256=prior.fingerprint(run),run=run))
    saved=prior.read(path);prior.atomic_json(root/'summary.json',summarize(saved['run'],refs,old));audit(root)


if __name__=='__main__':main()
