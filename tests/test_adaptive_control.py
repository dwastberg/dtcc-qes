"""Qualified pedestrian acceptance remains distinct from legacy convergence."""
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from dtcc_qes import wind,_qes
from dtcc_core.model import Building,City,Surface,GeometryType,Transform
from dtcc_core import datasets
from dtcc_qes.datasets import QESWindArgs
pytestmark = pytest.mark.usefixtures('dtcc_logger')


from fixtures.geometry import tower_city as city


from fixtures.specs import pedestrian_solver as settings


def run(solver=None):
    return wind.run(city(), bounds=(0,0,0,160,160,64), solver=solver or replace(settings(), max_iterations=600), speed=5, direction=270)


def qualified_build():
    # Toolchain alone cannot qualify a build after native source changes.
    return _qes.solver_policy_build_supported


def test_policy_serialization_and_validation():
    c=settings();assert c.policy=='pedestrian-v1'
    assert wind.Solver.from_dict(json.loads(json.dumps(c.to_dict())))==c
    with pytest.raises(ValueError,match='policy'):replace(c,policy='invented')
    with pytest.raises(ValueError,match='cadence'):replace(c,checkpoint_interval=1)
    assert replace(c,policy=None).mode == 'bounded'
    with pytest.raises(ValueError,match='history'):replace(c,monitor=replace(c.monitor,history_limit=4))


def test_accepted_legacy_false_suppresses_nonconvergence_warning(caplog):
    r=run()
    if not qualified_build():
        assert not r.solver["record"]['accepted'] and r.solver["record"]['assessment_reason']=='unqualified_build';return
    assert r.solver["record"]['accepted'] and r.solver["record"]['accuracy_status']=='accepted'
    assert r.solver["record"]['method'].endswith('1.90') and r.solver["record"]['assessment_scope']=='pedestrian_roi_and_required_receptors'
    assert not r.diagnostics.converged
    assert 'did not converge' not in caplog.text and 'unaccepted' not in caplog.text
    assert r.solver["record"]['assessment']['iteration']==r.diagnostics.iterations
    assert r.solver["record"]['assessment']['accepted'] and len(r.solver["record"]['assessment_history'])<=8
    assert r.solver["record"]['timings']['solve_seconds']<5
    assert r.velocity.flags.owndata and r.cell_flags.flags.owndata
    json.dumps(r.metadata,allow_nan=False)


def test_unaccepted_warns_even_when_legacy_tolerance_passes(caplog):
    r=wind.run(city(), bounds=(0,0,0,160,160,64), solver=replace(settings(), max_iterations=1, tolerance=100), speed=5, direction=270)
    assert r.diagnostics.converged and not r.solver["record"]['accepted']
    assert 'unaccepted' in caplog.text
    with pytest.raises(wind.UnacceptedResultError) as e:
        wind.run(city(), bounds=(0,0,0,160,160,64), solver=replace(settings(), max_iterations=1, raise_on_failure=True), speed=5, direction=270)
    assert e.value.record['termination_reason']=='iteration_limit'
    if qualified_build():
        assert run(solver=replace(settings(), max_iterations=600, raise_on_failure=True)).solver['record']['accepted']


def test_calm_rejected_and_invalid_required_point_not_accepted():
    with pytest.raises(ValueError,match='calm'):wind.run(city(), solver=settings(), speed=0, direction=270)
    c=settings();bad=replace(c.monitor,receptors=c.monitor.receptors+(wind.Receptor('solid',27,27,1.5),))
    r=wind.run(city(), bounds=(0,0,0,160,160,64), solver=replace(replace(c,monitor=bad), max_iterations=600), speed=5, direction=270)
    assert not r.solver["record"]['accepted']
    if qualified_build():assert r.solver["record"]['termination_reason']=='invalid_support' and r.diagnostics.iterations==1


@pytest.mark.parametrize('change,reason',[(dict(precision='float64'),'unqualified_precision'),
                                        (dict(turbulence=wind.Turbulence()),'turbulence_outside_assessment_scope')])
def test_unqualified_outputs_do_not_inherit_pedestrian_acceptance(change,reason):
    r=wind.run(city(), bounds=(0,0,0,160,160,64), **{k:v for k,v in change.items() if k != 'precision'}, solver=replace(settings(), max_iterations=3, precision=change.get('precision','float32')), speed=5, direction=270)
    assert not r.solver["record"]['accepted'] and r.solver["record"]['accuracy_status']=='not_assessed'
    if qualified_build():assert r.solver["record"]['assessment_reason']==reason
    assert r.solver["record"]['method'].endswith('1.78')


def test_adaptive_monitor_and_history_limits_enforced():
    c=settings()
    with pytest.raises(ValueError,match='memory'):
        wind.run(city(), bounds=(0,0,0,160,160,64), solver=replace(c,monitor=replace(c.monitor,memory_limit_bytes=1)), speed=5, direction=270)


def test_dataset_identity_normalizes_version_and_reports_scope(monkeypatch):
    value=city();monkeypatch.setattr(datasets,'city',lambda **kwargs:value)
    # Dataset selection adds its mandatory three-cell halo on each side.
    args=dict(bounds=[6,6,0,154,154,64],horizontal_padding=0.,min_building_detail=.1,solver=replace(settings(), max_iterations=600).to_dict(),product='field')
    omitted=json.loads(json.dumps(args));omitted['solver'].pop('checkpoint_interval')
    normalized=QESWindArgs(**omitted)
    assert normalized.solver==args['solver']
    assert normalized.wind_options()['solver'].policy=='pedestrian-v1'
    assert normalized.solver_policy_revision==_qes.solver_policy_revision
    with pytest.raises(ValueError,match='implementation changed'):QESWindArgs(**args,solver_policy_revision='old')
    result=datasets.qes_wind(**args)
    health=result.dataset_context.health;record=health['solver']['record']
    if qualified_build():
        assert record['accepted'] and health['numerically_accepted'] and not health['converged']
        assert not any('did not converge' in w for w in result.dataset_context.warnings)
    assert not health['execution_deterministic']
    assert any('full-volume' in w for w in result.dataset_context.warnings) if record['accepted'] else True
    json.dumps(result.dataset_context.model_dump(mode='json'),allow_nan=False)


def test_threads_budget_errors_and_owned_outputs_do_not_deadlock():
    script=r'''
from concurrent.futures import ThreadPoolExecutor
from dtcc_qes import wind
from dtcc_core.model import City
c=wind.Solver(max_solve_seconds=1e-12, monitor=wind.MonitorSpec((0,24,0,24)), policy="pedestrian-v1")
def f(i):
    try:wind.run(City(), bounds=(0,0,0,24,24,16), solver=c, speed=5, direction=270)
    except wind.BudgetExhaustedError as e:
        assert e.record['termination_reason']=='time_limit' and not e.record['accepted'];return
    raise AssertionError('No zero-work error')
with ThreadPoolExecutor(2) as p:list(p.map(f,range(4)))
'''
    subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,check=True,timeout=20,
                   env=os.environ|{'OMP_NUM_THREADS':'2','OMP_DYNAMIC':'FALSE'})
