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


def city():
    value=City(transform=Transform(srs='EPSG:3006'))
    for i,(x,y,h) in enumerate([(22,22,7.9),(42,22,7.9),(22,42,7.9),(42,42,23.7)]):
        b=Building(id=str(i));b.measured_height=b.estimated_height=h
        b.add_geometry(Surface(vertices=np.array([[x,y,0],[x,y+12,0],[x+12,y+12,0],[x+12,y,0],[x,y,0]],float)),GeometryType.LOD0)
        value.add_building(b)
    return value


def settings(**kwargs):
    monitor=wind.MonitorSpec((0,80,0,80),receptors=tuple(wind.Receptor(f'h{h}',27,21,h) for h in [1.5,1.75]),history_limit=8)
    return wind.SolverControl(5,monitor,mode='adaptive',**kwargs)


def run(**kwargs):
    return wind.run(city(),5,270,bounds=(0,0,0,160,160,64),max_iterations=600,solver_control=settings(),**kwargs)


def qualified_build():
    # Toolchain alone cannot qualify a build after native source changes.
    return _qes.solver_policy_build_supported


def test_policy_serialization_and_validation():
    c=settings();assert c.policy=='pedestrian-v1'
    assert wind.SolverControl.from_dict(json.loads(json.dumps(asdict(c))))==c
    with pytest.raises(ValueError,match='policy'):replace(c,policy='invented')
    with pytest.raises(ValueError,match='cadence'):replace(c,checkpoint_interval=1)
    with pytest.raises(ValueError,match='no acceptance'):replace(c,mode='bounded')
    with pytest.raises(ValueError,match='history'):replace(c,monitor=replace(c.monitor,history_limit=4))


def test_accepted_legacy_false_suppresses_nonconvergence_warning(caplog):
    r=run()
    if not qualified_build():
        assert not r.control['accepted'] and r.control['assessment_reason']=='unqualified_build';return
    assert r.control['accepted'] and r.control['accuracy_status']=='accepted'
    assert r.control['method'].endswith('1.90') and r.control['assessment_scope']=='pedestrian_roi_and_required_receptors'
    assert not r.diagnostics.converged
    assert 'did not converge' not in caplog.text and 'unaccepted' not in caplog.text
    assert r.control['assessment']['iteration']==r.diagnostics.iterations
    assert r.control['assessment']['accepted'] and len(r.control['assessment_history'])<=8
    assert r.control['timings']['solve_seconds']<5
    assert r.velocity.flags.owndata and r.cell_flags.flags.owndata
    json.dumps(r.metadata,allow_nan=False)


def test_unaccepted_warns_even_when_legacy_tolerance_passes(caplog):
    r=wind.run(city(),5,270,bounds=(0,0,0,160,160,64),max_iterations=1,tolerance=100,solver_control=settings())
    assert r.diagnostics.converged and not r.control['accepted']
    assert 'unaccepted' in caplog.text
    with pytest.raises(wind.UnacceptedResultError) as e:
        wind.run(city(),5,270,bounds=(0,0,0,160,160,64),max_iterations=1,solver_control=settings(),raise_on_unaccepted=True)
    assert e.value.control['termination_reason']=='iteration_limit'
    with pytest.raises(ValueError,match='raise_on_unaccepted'):run(raise_on_nonconvergence=True)
    with pytest.raises(ValueError,match='adaptive'):wind.run(city(),5,270,raise_on_unaccepted=True)


def test_calm_rejected_and_invalid_required_point_not_accepted():
    with pytest.raises(ValueError,match='calm'):wind.run(city(),0,270,solver_control=settings())
    c=settings();bad=replace(c.monitor,receptors=c.monitor.receptors+(wind.Receptor('solid',27,27,1.5),))
    r=wind.run(city(),5,270,bounds=(0,0,0,160,160,64),max_iterations=600,solver_control=replace(c,monitor=bad))
    assert not r.control['accepted']
    if qualified_build():assert r.control['termination_reason']=='invalid_support' and r.diagnostics.iterations==1


@pytest.mark.parametrize('change,reason',[(dict(solver_precision='float64'),'unqualified_precision'),
                                        (dict(turbulence=True),'turbulence_outside_assessment_scope')])
def test_unqualified_outputs_do_not_inherit_pedestrian_acceptance(change,reason):
    r=wind.run(city(),5,270,bounds=(0,0,0,160,160,64),max_iterations=3,solver_control=settings(),**change)
    assert not r.control['accepted'] and r.control['accuracy_status']=='not_assessed'
    if qualified_build():assert r.control['assessment_reason']==reason
    assert r.control['method'].endswith('1.78')


def test_adaptive_monitor_and_history_limits_enforced():
    c=settings()
    with pytest.raises(ValueError,match='memory'):
        wind.run(city(),5,270,bounds=(0,0,0,160,160,64),solver_control=replace(c,monitor=replace(c.monitor,memory_limit_bytes=1)))


def test_dataset_identity_normalizes_version_and_reports_scope(monkeypatch):
    value=city();monkeypatch.setattr(datasets,'city',lambda **kwargs:value)
    # Dataset selection adds its mandatory three-cell halo on each side.
    args=dict(bounds=[6,6,0,154,154,64],horizontal_padding=0.,min_building_detail=.1,max_iterations=600,tolerance=1e-5,
              solver_control=asdict(settings()),product='field')
    omitted=json.loads(json.dumps(args));omitted['solver_control'].pop('policy')
    normalized=QESWindArgs(**omitted)
    assert normalized.solver_control==args['solver_control']
    assert normalized.wind_options()['solver_control'].policy=='pedestrian-v1'
    assert normalized.solver_policy_revision==_qes.solver_policy_revision
    with pytest.raises(ValueError,match='implementation changed'):QESWindArgs(**args,solver_policy_revision='old')
    result=datasets.qes_wind(**args)
    health=result.dataset_context.health;record=health['solver_control']
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
c=wind.SolverControl(1e-12,wind.MonitorSpec((0,24,0,24)),mode='adaptive')
def f(i):
    try:wind.run(City(),5,270,bounds=(0,0,0,24,24,16),solver_control=c)
    except wind.BudgetExhaustedError as e:
        assert e.record['termination_reason']=='time_limit' and not e.record['accepted'];return
    raise AssertionError('No zero-work error')
with ThreadPoolExecutor(2) as p:list(p.map(f,range(4)))
'''
    subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,check=True,timeout=20,
                   env=os.environ|{'OMP_NUM_THREADS':'2','OMP_DYNAMIC':'FALSE'})
