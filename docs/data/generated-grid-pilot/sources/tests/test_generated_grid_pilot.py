"""Keep the bounded vertical pilot honest about local failures and scope."""
import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from test_joint_grid_verification import manufactured

_tools=Path(__file__).parents[1]/'tools'
_spec=importlib.util.spec_from_file_location('generated_pilot',_tools/'run_generated_grid_pilot.py')
study=importlib.util.module_from_spec(_spec)
sys.path.insert(0,str(_tools))
try:
    _spec.loader.exec_module(study)
finally:
    sys.path.pop(0)


def documents():
    frozen={f'{f}/270/{h}/{r}':[0 if f=='auto' else 1]
            for f in ('auto','uniform-0.5') for h in study.HEIGHTS for r in ('all','away4m')}
    docs={}; refs={}
    for backend in study.BACKENDS:
        runs=[]; reference=[]
        for task in study.tasks():
            run=manufactured(task)
            run.update(cells=92,peak_rss_bytes=100,roof_errors=[.1])
            for c in run['checkpoints']: c['solve_seconds']=1
            runs.append(run)
            other=copy.deepcopy(run)
            other['task']=task|dict(family='uniform-0.5',id=f"joint/{task['extent']}/uniform-0.5/270/0.5")
            other['cells']=128
            reference.append(other)
        docs[backend]=dict(runs=runs,attempts=[])
        refs[backend]=dict(runs=reference,metadata=dict(frozen_critical_indices=frozen))
    return docs,refs


def test_vertical_pass_never_qualifies_comfort_and_needs_both_extents_and_backends():
    docs,refs=documents()
    result=study.summarize(docs,refs)
    assert result['complete'] and result['vertical_pilot_pass']
    assert not result['comfort_qualified']
    docs['serial']['runs'].pop()
    result=study.summarize(docs,refs)
    assert not result['complete'] and not result['vertical_pilot_pass']


def test_original_critical_sets_are_both_preserved():
    _,refs=documents()
    assert study.frozen_indices(refs['serial'],1.5,'all')==[0,1]


def test_near_wall_failure_remains_mandatory_but_is_not_an_away_region_point():
    docs,refs=documents()
    index=list(study.POINTS).index(27)+len(study.POINTS)*list(study.POINTS).index(21)
    for doc in docs.values():
        for c in doc['runs'][0]['checkpoints']:
            c['planes'][0]['velocity'][index]=[4,0,0]
    result=study.summarize(docs,refs)
    rows=result['backends']['serial']['comparisons']
    full=next(r for r in rows if r['comparison']=='vertical_at_240' and r['height']==1.5 and r['region']=='all')
    away=next(r for r in rows if r['comparison']=='vertical_at_240' and r['height']==1.5 and r['region']=='away4m')
    assert full['regional_within_budget'] and not full['combined_within_budget']
    assert away['regional_within_budget'] and 'mandatory_local_checks' not in away
    assert not result['vertical_pilot_pass']


def test_failed_residual_withholds_vertical_and_lateral_comparisons():
    docs,refs=documents()
    docs['serial']['runs'][0]['checkpoints'][0]['max_divergence']=1
    result=study.summarize(docs,refs)
    assert not result['vertical_pilot_pass']
    rows=result['backends']['serial']['comparisons']
    affected=[r for r in rows if r['comparison']!='vertical_at_160']
    assert all(not r['matched_accuracy'] and 'p95_abs_delta_K' not in r for r in affected)


def test_actual_policy_changes_with_resolution_and_lateral_operands_stay_fixed():
    configs,previews=study.plans()
    p=previews['160']; q=previews['240']
    assert len(p['layers_input'])==92
    assert p['layers_input']==q['layers_input']
    assert q['cell_count']==21196800>20000000
    assert p['metadata']['pedestrian_sampling']['centre_indices']==[3,3]
    assert p['metadata']['effective_settings']['upper_layer_cap']==2
    np.testing.assert_array_equal(configs['generated']['expected_faces'],p['expected_faces'])


def test_source_snapshot_tampering_is_rejected_without_binaries(tmp_path):
    p=tmp_path/'protocol.md'; p.write_text('protocol')
    source=tmp_path/'sources/a.py'; source.parent.mkdir(); source.write_text('original')
    manifest=dict(protocol_sha256=study.digest(p),source_sha256={'a.py':study.digest(source)})
    study.verify_frozen(tmp_path,manifest)
    source.write_text('changed')
    with pytest.raises(ValueError,match='snapshot'):
        study.verify_frozen(tmp_path,manifest)
