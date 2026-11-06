"""Regression gates must catch lost probes, changed planes and slower answers."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
import numpy as np
import pytest
from rerun_regression import accuracy,performance,equal_values,claim_attempt


def fixture_record():
    return dict(spec=dict(case='D'),grid=dict(shape=[2,3,4]),profile=dict(speed=5.),
        probes=dict(ids=[1,2],K=[1.,None],method=['linear','none']),
        diagnostics=dict(iterations=2000,converged=False),
        provenance=dict(city_digest='fixed-city',xls_sha256='fixed-measurements'))


@pytest.mark.parametrize('mutation',['probe_value','coverage','method','plane','city','iterations'])
def test_accuracy_requires_identical_coverage_fields_and_inputs(tmp_path,mutation):
    import copy
    parent=fixture_record();current=copy.deepcopy(parent)
    a=tmp_path/'a.npz';b=tmp_path/'b.npz'
    np.savez(a,velocity=np.ones((2,3)),valid=np.array([True,False]))
    np.savez(b,velocity=np.ones((2,3)),valid=np.array([True,False]))
    assert accuracy(current,parent,a,b)['passed']
    if mutation=='probe_value':current['probes']['K'][0]+=.001
    elif mutation=='coverage':current['probes']['K'][1]=0.
    elif mutation=='method':current['probes']['method'][0]='nearest_fluid'
    elif mutation=='plane':np.savez(a,velocity=np.zeros((2,3)),valid=np.array([True,False]))
    elif mutation=='city':current['provenance']['city_digest']='changed'
    else:current['diagnostics']['iterations']=1000
    assert not accuracy(current,parent,a,b)['passed']


def timing_pairs():
    return [dict(key=str(i),repetition=r,case='D' if i<3 else 'E',parent_seconds=10.,current_seconds=10.,
        current_rss=1_000_000_000,parent_rss=1_000_000_000) for i in range(35) for r in range(3)]


@pytest.mark.parametrize('mutation',['time','memory','missing','missing_case','deadline'])
def test_performance_cannot_hide_slow_condition_memory_or_missing_repetitions(mutation):
    rows=timing_pairs();assert performance(rows)['passed']
    if mutation=='time':
        for r in rows[:3]:r['current_seconds']*=1.06
    elif mutation=='memory':rows[0]['current_rss']=2.1*2**30
    elif mutation=='missing':rows.pop()
    elif mutation=='missing_case':rows=rows[3:]
    else:rows[0]['current_seconds']=21.
    assert not performance(rows)['passed']


def test_numeric_nulls_and_string_methods_compare_without_losing_nan_semantics():
    assert equal_values([1.,None],[1.,None])
    assert not equal_values([1.,None],[1.,0.])
    assert not equal_values(['linear'],['nearest_fluid'])


def test_incomplete_or_live_attempt_cannot_be_overwritten(tmp_path):
    folder=tmp_path/'attempt';claim_attempt(folder)
    evidence=folder/'stderr.log';evidence.write_text('partial evidence')
    with pytest.raises(RuntimeError,match='incomplete/live'):
        claim_attempt(folder)
    assert evidence.read_text()=='partial evidence'
