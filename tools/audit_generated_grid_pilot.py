"""Reproduce the generated-grid pilot using archived data and frozen sources."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def validate_saved(saved, task, sweeps, manifest, study, backend):
    request=dict(study_identity=study.fingerprint(manifest), task=task, sweeps=sweeps,
        input_sha256=hashlib.sha256(study.input_text(task,manifest['configurations']).encode()).hexdigest())
    if saved['request']!=request or saved['run_sha256']!=study.fingerprint(saved['run']):
        raise ValueError('Checkpoint identity/content mismatch')
    from run_joint_grid_verification import validate_checkpoint
    validate_checkpoint(saved['run'],task,manifest['configurations'],study.BACKENDS[backend],sweeps)
    run=saved['run']
    initial={p['height']:p for p in run['initial_planes']}
    for plane in run['checkpoints'][0]['planes']:
        if plane['flags']!=initial[plane['height']]['flags']:
            raise ValueError('Occupancy flags changed during solve')
    return run


def audit(root):
    sys.path.insert(0,str((root/'sources/tools').resolve()))
    import run_generated_grid_pilot as study
    from run_joint_grid_verification import assemble
    manifest=study.read(root/'manifest.json')
    study.verify_frozen(root,manifest)
    references,_=study.reference_data(manifest['references_sha256'])
    documents=study.collect(root,manifest)
    if documents!=study.read(root/'raw.json.gz'):
        raise ValueError('Raw archive differs from atomic case records')
    summary=study.summarize(documents,references)
    if summary!=study.read(root/'summary.json'):
        raise ValueError('Summary does not reproduce from frozen analysis')
    costs={}
    states={}
    for backend,doc in documents.items():
        cached={}; work=[]
        for task in study.tasks():
            state=None
            for path in sorted((root/backend/'checkpoints'/task['id']).glob('*.json.gz')):
                saved=study.read(path); sweeps=saved['request']['sweeps']
                if path.name!=f'{sweeps:06d}.json.gz': raise ValueError('Checkpoint filename mismatch')
                run=validate_saved(saved,task,sweeps,manifest,study,backend)
                current={k:run[k] for k in ('initial_planes','profile_planes','z_faces',
                                            'sample_x','sample_y','roof_errors','horizontal_bounds')}
                if state is not None and state!=current: raise ValueError('Initialization differs across zero starts')
                state=current
                states[backend,task['extent']]=state
                cached[path.resolve()]=run
                c=run['checkpoints'][0]
                work.append(dict(task=task['id'],sweeps=sweeps,physical_cells=run['cells'],
                    preparation_seconds=run['prep_seconds'],solve_seconds=c['solve_seconds'],
                    residual_seconds=c['residual_seconds'],sampling_seconds=c['sampling_seconds'],
                    peak_rss_bytes=run['peak_rss_bytes'],path=str(path),sha256=study.digest(path)))
        trial_ids=[(r['task']['id'],r['checkpoints'][0]['iterations']) for r in doc['attempts']]
        if len(trial_ids)!=len(set(trial_ids)) or any(study.gate(r)['accepted'] for r in doc['attempts']):
            raise ValueError('Duplicate rejected trial or accepted trial labelled rejected')
        for run in doc['runs']+doc['attempts']:
            checkpoint_docs=[]
            for origin in run['checkpoint_origins']:
                path=Path(origin['path'])
                if study.digest(path)!=origin['sha256']: raise ValueError('Selected checkpoint hash mismatch')
                checkpoint_docs.append(cached[path.resolve()])
            if assemble(run['task'],checkpoint_docs,run['checkpoint_origins'])!=run:
                raise ValueError('Run differs from independent checkpoint assembly')
        costs[backend]=dict(unique_checkpoints=len(work),rejected_budget_triples=len(doc['attempts']),
            executed_solve_seconds=sum(c['solve_seconds'] for c in work),
            executed_preparation_seconds=sum(c['preparation_seconds'] for c in work),
            executed_residual_seconds=sum(c['residual_seconds'] for c in work),
            executed_sampling_seconds=sum(c['sampling_seconds'] for c in work),
            executed_cell_sweeps=sum(c['physical_cells']*c['sweeps'] for c in work),
            peak_rss_bytes=max((c['peak_rss_bytes'] for c in work),default=0),checkpoints=work)
    for extent in (160,240):
        if all((b,extent) in states for b in study.BACKENDS):
            if states['serial',extent]!=states['openmp',extent]: raise ValueError('CPU initialization/flags differ')
    result=dict(complete=summary['complete'],vertical_pilot_pass=summary['vertical_pilot_pass'],
        comfort_qualified=False,requires_worker_executable=False,backends=costs,
        summary_sha256=study.digest(root/'summary.json'),manifest_sha256=study.digest(root/'manifest.json'),
        audit_source_sha256=study.digest(__file__),cpu_decisions_equal=summary['cpu_decisions_equal'],
        cpu_fields_within_stability_budget=summary['cpu_fields_within_stability_budget'])
    study.atomic_json(root/'audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='backends'},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('docs/data/generated-grid-pilot'))
    audit(parser.parse_args().output)
