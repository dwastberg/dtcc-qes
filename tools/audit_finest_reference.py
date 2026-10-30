"""Audit the frozen reference attempt and its explicit runtime-review stop."""
import argparse
import importlib.util
from pathlib import Path
import sys


def stopped_summary(interrupted, stopped):
    if interrupted['completed_checkpoint_results'] or stopped['saved_checkpoint_results']:
        raise ValueError('Stopped archive unexpectedly declares completed checkpoints')
    return dict(complete=False,stopped=True,archive_integrity_pass=True,accepted=None,
        reference_usable=False,comfort_qualified=False,preset_selected=False,
        completed_executions=0,interrupted_executions=1,user_stopped_executions=1,
        total_execution_attempts=2,executed_sweeps_known=False,
        observed_cpu_seconds_lower_bound=interrupted['last_observed_cpu_seconds']+stopped['last_observed_cpu_seconds'],
        executed_cell_sweeps_range=[0,interrupted['executed_cell_sweeps_upper_bound']+stopped['executed_cell_sweeps_upper_bound']],
        disposition='Stopped for fast-approximation runtime review; no numerical acceptance decision')


def audit(root):
    root=Path(root);sys.path.insert(0,str((root/'sources/tools').resolve()))
    spec=importlib.util.spec_from_file_location('frozen_finest_reference',root/'sources/tools/run_finest_reference.py')
    study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)
    manifest=study.prior.read(root/'manifest.json');study.verify(root,manifest);study.references(manifest)
    for name in ('planning-timings.json','runtime-review.json'):
        doc=study.prior.read(root/name)
        for path,sha in doc['source_sha256'].items():
            if study.prior.digest(path)!=sha:raise ValueError(f'Benchmark source changed: {path}')
    planning=study.prior.read(root/'planning-timings.json')['measurements']['historical_native_preparation']
    if study.prior.digest(planning['source'])!=planning['source_sha256']:
        raise ValueError('Historical preparation source changed')
    runtime=study.prior.read(root/'runtime-review.json')
    if runtime['per_case_wall_limit_seconds']!=30 or len(runtime['runs'])!=2:
        raise ValueError('Bounded normal-API matrix mismatch')
    if {r['precision'] for r in runtime['runs']}!={'float32','float64'}:
        raise ValueError('Missing or duplicate precision timing')
    for row in runtime['runs']:
        saved=study.prior.read(root/'runtime-cases'/(row['precision']+'.json'))
        if any(row[k]!=v for k,v in saved.items()):raise ValueError('Runtime record differs from worker output')
        if row['status']=='completed' and (row['diagnostics']['iterations']>500 or row['requested_max_iterations']!=500):
            raise ValueError('Runtime iteration cap exceeded')
        if not Path(row['log']).exists():raise ValueError('Missing runtime worker log')
    status=study.prior.read(root/'status.json')
    if status['state']!='stopped_for_runtime_review':raise ValueError('Unexpected stage disposition')
    if any((root/name).exists() for name in ('execution.json.gz','reference.png','figure.json')):
        raise ValueError('Stopped archive unexpectedly contains completed reference products')
    interrupted=study.prior.read(root/'interruption.json');stopped=study.prior.read(root/'runtime-review-stop.json')
    result=stopped_summary(interrupted,stopped)
    if study.prior.read(root/'summary.json')!=result:raise ValueError('Stopped summary differs')
    names=('manifest.json','summary.json','status.json','interruption.json','runtime-review-stop.json',
           'retry-supervision.json','planning-timings.json','runtime-review.json')
    paths=[root/name for name in names]+sorted((root/'runtime-cases').glob('*'))
    costs=result | dict(exact_total_work_known=False,
        scope='CPU lower bound and broad work bounds include both incomplete attempts; no zero-cost assumption',
        inputs_sha256={str(p):study.prior.digest(p) for p in paths})
    study.prior.atomic_json(root/'costs.json',costs)
    result=result | dict(requires_worker_executable=False,manifest_sha256=study.prior.digest(root/'manifest.json'),
        costs_sha256=study.prior.digest(root/'costs.json'),audit_source_sha256=study.prior.digest(__file__))
    study.prior.atomic_json(root/'audit.json',result)
    print(result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('docs/data/finest-reference'))
    audit(parser.parse_args().output)
