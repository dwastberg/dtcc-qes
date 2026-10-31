"""Audit every saved vertical-refinement checkpoint without native executables."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def validate_saved(saved,task,sweeps,manifest,study,backend):
    request=dict(study_identity=study.fingerprint(manifest),task=task,sweeps=sweeps,
        input_sha256=hashlib.sha256(study.input_text(task,manifest['configurations']).encode()).hexdigest())
    if saved['request']!=request or saved['run_sha256']!=study.fingerprint(saved['run']):
        raise ValueError('Checkpoint identity/content mismatch')
    from run_joint_grid_verification import validate_checkpoint
    run=saved['run']
    validate_checkpoint(run,task,manifest['configurations'],study.BACKENDS[backend],sweeps)
    if run['threads'] != (2 if backend=='openmp' else 1):
        raise ValueError('Native thread count differs from the declared backend')
    expected=[r['error'] for r in manifest['configurations'][task['family']]['metadata']['roof_representation']]
    import numpy as np
    np.testing.assert_allclose(run['roof_errors'],expected,rtol=0,atol=2e-8)
    initial={p['height']:p for p in run['initial_planes']}
    for plane in run['checkpoints'][0]['planes']:
        if plane['flags']!=initial[plane['height']]['flags']:
            raise ValueError('Occupancy changed during solve')
    for h in study.HEIGHTS:
        for point in study.LOCATIONS:
            for stage in ('profile','initial','final'):
                study.audit_point(run,h,point,stage)
    return run


def origin_tail(backend,task,sweeps):
    return Path(backend)/'checkpoints'/task['id']/f'{sweeps:06d}.json.gz'


def audit(root):
    sys.path.insert(0,str((root/'sources/tools').resolve()))
    import run_vertical_refinement as study
    from run_joint_grid_verification import assemble
    manifest=study.read(root/'manifest.json');study.verify_frozen(root,manifest)
    if manifest['task_matrix']!={b:study.tasks(b) for b in study.BACKENDS}:
        raise ValueError('Task matrix differs from frozen analysis')
    refs,_=study.reference_data(manifest['references_sha256'])
    docs=study.collect(root,manifest)
    if docs!=study.read(root/'raw.json.gz'):raise ValueError('Raw archive differs from case records')
    summary=study.summarize(docs,refs,manifest['configurations'])
    if summary!=study.read(root/'summary.json'):raise ValueError('Summary does not reproduce')
    costs={};states={};all_accepted=True
    for backend,doc in docs.items():
        work=[];cached={}
        for task in study.tasks(backend):
            state=None
            for path in sorted((root/backend/'checkpoints'/task['id']).glob('*.json.gz')):
                saved=study.read(path);sweeps=saved['request']['sweeps']
                if path.name!=f'{sweeps:06d}.json.gz':raise ValueError('Checkpoint filename mismatch')
                run=validate_saved(saved,task,sweeps,manifest,study,backend)
                current={k:run[k] for k in ('initial_planes','profile_planes','z_faces','sample_x','sample_y','roof_errors','horizontal_bounds')}
                if state is not None and state!=current:raise ValueError('Initial/support fields differ across zero starts')
                state=current;states[backend,task['family']]=state
                tail=origin_tail(backend,task,sweeps);cached[tail]=run
                c=run['checkpoints'][0]
                work.append(dict(task=task['id'],sweeps=sweeps,path=str(tail),sha256=study.digest(path),
                    physical_cells=run['cells'],peak_rss_bytes=run['peak_rss_bytes'],
                    preparation_seconds=run['prep_seconds'],solve_seconds=c['solve_seconds'],
                    residual_seconds=c['residual_seconds'],sampling_seconds=c['sampling_seconds']))
        ids=[(r['task']['id'],r['checkpoints'][0]['iterations']) for r in doc['attempts']]
        if len(ids)!=len(set(ids)) or any(study.gate(r)['accepted'] for r in doc['attempts']):
            raise ValueError('Invalid rejected-trial history')
        for run in doc['runs']+doc['attempts']:
            selected=[]
            if len(run['checkpoint_origins'])!=len(run['checkpoints']):raise ValueError('Missing checkpoint origin')
            for c,origin in zip(run['checkpoints'],run['checkpoint_origins']):
                tail=origin_tail(backend,run['task'],c['iterations'])
                if Path(origin['path']).parts[-len(tail.parts):]!=tail.parts:
                    raise ValueError('Selected checkpoint path scope mismatch')
                if study.digest(root/tail)!=origin['sha256']:raise ValueError('Selected checkpoint fingerprint mismatch')
                selected.append(cached[tail])
            if assemble(run['task'],selected,run['checkpoint_origins'])!=run:
                raise ValueError('Run differs from checkpoint assembly')
        all_accepted &= all(study.gate(r)['accepted'] for r in doc['runs'])
        terminal_failures=sum(not study.gate(r)['accepted'] for r in doc['runs'])
        costs[backend]=dict(unique_checkpoints=len(work),
            rejected_intermediate_triples=len(doc['attempts']),terminal_failed_cases=terminal_failures,
            rejected_budget_triples=len(doc['attempts'])+terminal_failures,
            executed_preparation_seconds=sum(c['preparation_seconds'] for c in work),
            executed_solve_seconds=sum(c['solve_seconds'] for c in work),
            executed_residual_seconds=sum(c['residual_seconds'] for c in work),
            executed_sampling_seconds=sum(c['sampling_seconds'] for c in work),
            executed_cell_sweeps=sum(c['physical_cells']*c['sweeps'] for c in work),
            peak_rss_bytes=max((c['peak_rss_bytes'] for c in work),default=0),checkpoints=work)
    if all((b,'aligned-1.75') in states for b in study.BACKENDS):
        if states['serial','aligned-1.75']!=states['openmp','aligned-1.75']:
            raise ValueError('CPU alignment control initial/support disagreement')
    result=dict(complete=summary['complete'],all_solve_accepted=bool(summary['complete'] and all_accepted),
        sensitivity_budget_pass=summary['sensitivity_budget_pass'],alignment_budget_pass=summary['alignment_budget_pass'],
        control_cpu_agrees=summary['control_cpu_agrees'],comfort_qualified=False,preset_selected=False,
        requires_worker_executable=False,backends=costs,
        summary_sha256=study.digest(root/'summary.json'),manifest_sha256=study.digest(root/'manifest.json'),
        audit_source_sha256=study.digest(__file__))
    study.atomic_json(root/'audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='backends'},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('docs/data/vertical-refinement'))
    audit(parser.parse_args().output)
