"""Protect the bounded triple contract and comparison withholding."""
import copy
import sys
from pathlib import Path
import pytest
from test_vertical_refinement import documents

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import run_finest_reference as study
sys.path.pop(0)


def test_regular_triple_mode_supports_160k_without_single_checkpoint_guard():
    m=dict(task=dict(direction=270),binary=dict(path='worker'),allocation_ceiling=40000000)
    command=study.command(m)
    assert command[4]=='40000' and '--checkpoint' not in command
    assert study.SWEEPS==[40000,80000,160000]


def test_failed_early_residual_withholds_all_finest_comparisons():
    docs,refs,_=documents();old={r['task']['family']:r for r in docs['openmp']['runs']}
    run=copy.deepcopy(old['split-4'])
    run['checkpoints'][0]['max_divergence']=1
    result=study.summarize(run,refs,old)
    assert not result['solve']['accepted']
    rows=[r for r in result['comparisons'] if r['comparison'] in ('base_to_4','2_to_4','alignment_to_4')]
    assert len(rows)==12 and all(not r['matched_accuracy'] and 'p95_abs_delta_K' not in r for r in rows)
    assert not result['vertical_sensitivity_budget_pass']


def test_accepted_reference_keeps_earlier_local_failure_and_never_selects_preset():
    docs,refs,_=documents();old={r['task']['family']:r for r in docs['openmp']['runs']}
    index=list(study.prior.POINTS).index(15)+len(study.prior.POINTS)*list(study.prior.POINTS).index(47)
    for c in refs['openmp']['base']['checkpoints']:c['planes'][0]['velocity'][index]=[4,0,0]
    result=study.summarize(old['split-4'],refs,old)
    assert result['solve']['accepted'] and not result['vertical_sensitivity_budget_pass']
    assert not result['preset_selected'] and not result['comfort_qualified']
    assert len(result['comparisons'])==20


@pytest.mark.parametrize('budgets',[[40000,80000],[40000,80000,80000],[16000,32000,64000]])
def test_missing_duplicate_or_old_checkpoints_rejected_before_acceptance(budgets):
    run=dict(task={},threads=2,checkpoints=[dict(iterations=n) for n in budgets])
    with pytest.raises(ValueError,match='three distinct'):
        study.validate(run,dict(task={}))
