"""S6 selection fails closed on support, numerical or held-out failures."""

from fixtures.support import load_tool
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
m=load_tool('method_study', TOOLS/'run_solver_method_study.py');pass


def inputs():
    a=np.zeros((6,4));a[:,3]=1
    cp=dict(iteration=25,elapsed_seconds=.1,mass=dict(maximum=1e-6,rms=1e-7,top_maximum=.1),
            residual=dict(relative_maximum=1e-5,relative_rms=1e-6,maximum=.001,rms=.0001),maximum_change=.1)
    return cp,a


def test_every_height_receptor_and_numerical_gate_is_required():
    cp,a=inputs();ref=a.copy()
    assert m.assess(cp,a,ref,2)['passed']
    for i in range(len(a)):
        b=a.copy();b[i,0]=.006
        assert not m.assess(cp,b,ref,2)['passed']
    for key,field in [('mass','maximum'),('mass','rms'),('residual','relative_maximum'),('residual','relative_rms')]:
        c={**cp,key:dict(cp[key])};c[key][field]=1
        assert not m.assess(c,a,ref,2)['passed']
    a[-1,3]=0
    assert not m.assess(cp,a,ref,2)['passed']


def test_nonfinite_valid_evidence_rejected():
    cp,a=inputs();ref=a.copy();a[0,0]=float('nan')
    with pytest.raises(ValueError,match='Nonfinite'):m.assess(cp,a,ref,2)
    cp['residual']['relative_rms']=float('nan')
    assert not m.assess(cp,ref,ref,2)['passed']


def test_three_late_stable_checkpoints_and_same_initial_required(tmp_path):
    cp,a=inputs();samples=np.repeat(a[None],5,axis=0)
    np.savez_compressed(tmp_path/'reference.npz',samples=samples)
    np.savez_compressed(tmp_path/'row.npz',samples=samples)
    checkpoints=[dict(cp,iteration=i*25,elapsed_seconds=.1*i) for i in range(5)]
    row=dict(status='completed',request=dict(id='row'),result=dict(initial_hashes=['same'],plane_points=2,checkpoints=checkpoints))
    ref=dict(request=dict(id='reference'),result=dict(initial_hashes=['same']))
    assert m.evaluate(row,tmp_path,ref)['first_target_iteration']==75
    # One late failure invalidates an apparently early success.
    samples[-1,4,0]=1
    np.savez_compressed(tmp_path/'row.npz',samples=samples)
    assert not m.evaluate(row,tmp_path,ref)['qualified']
    np.savez_compressed(tmp_path/'row.npz',samples=samples[:2])
    row['result']['checkpoints']=checkpoints[:2]
    assert not m.evaluate(row,tmp_path,ref)['qualified']
    row['result']['initial_hashes']=['different']
    assert not m.evaluate(row,tmp_path,ref)['qualified']


def confirmation():
    rows=[];assessments={};cases=['tower','passages','held']
    for case in cases:
        for rep in range(3):
            for omega,cost in [(1.78,1.),(1.95,.7)]:
                ident=str(len(rows));rows.append(dict(request=dict(id=ident,purpose='confirmation',case=case,rep=rep,omega=omega)))
                assessments[ident]=dict(qualified=True,total_cost_seconds=cost)
    for case in cases:
        for omega in [1.78,1.95]:
            ident=str(len(rows));rows.append(dict(request=dict(id=ident,purpose='precision',case=case,omega=omega)))
            assessments[ident]=dict(qualified=True,total_cost_seconds=.7)
    return rows,assessments,cases


def test_method_requires_all_cases_pairs_references_and_precisions():
    rows,a,cases=confirmation()
    assert m.decision(rows,a,1.95,cases,True)['factor']==1.95
    assert m.decision(rows,a,1.95,cases,False)['factor']==1.78
    # A held-out regression cannot be hidden by a favorable aggregate.
    a['13']['total_cost_seconds']=1.1;a['15']['total_cost_seconds']=1.1
    assert m.decision(rows,a,1.95,cases,True)['factor']==1.78
    rows,a,cases=confirmation();a['23']['qualified']=False
    assert m.decision(rows,a,1.95,cases,True)['factor']==1.78
    rows,a,cases=confirmation();a['1']['qualified']=False
    assert m.decision(rows,a,1.95,cases,True)['factor']==1.78


def test_screen_selects_cost_to_target_and_rejects_unqualified_fast_factor():
    rows=[];a={}
    for case in ['tower','passages']:
        for omega,cost in [(1.78,1.),(1.85,.8),(1.9,.5),(1.95,.4)]:
            ident=str(len(rows));rows.append(dict(request=dict(id=ident,purpose='screen',case=case,omega=omega)))
            a[ident]=dict(qualified=omega!=1.95,total_cost_seconds=cost)
    assert m.screen_choice(rows,a,['tower','passages'])==1.9
    a['6']['qualified']=False
    assert m.screen_choice(rows,a,['tower','passages'])==1.85


def test_audit_rejects_changed_evidence_before_replaying(tmp_path):
    (tmp_path/'input.json').write_text('{}')
    (tmp_path/'manifest.json').write_text('{"files":{"input.json":"wrong"}}')
    with pytest.raises(ValueError,match='Changed evidence'):m.audit(tmp_path)


def test_publication_rejects_recursive_destination(tmp_path):
    with pytest.raises(ValueError,match='outside the working study'):m.publish(tmp_path,tmp_path/'evidence')


def test_completed_method_evidence_replays():
    import complete_solver_s6
    import json
    folder=TOOLS.parent/'docs/data/solver-control-s6'
    replay=complete_solver_s6.verify(folder)
    assert replay['main_workers']==43 and replay['early_workers']==8
    assert len(replay['default_full_history_exact'])==2
    assert replay['method']=='s5c-rb-sor-float-omega-v1-omega-1.90'
    assert replay==json.loads((folder/'verification.json').read_text())


def test_transient_guard_does_not_hide_growth_or_failed_workers(tmp_path):
    import complete_solver_s6
    import json
    directory=tmp_path/'transients';directory.mkdir()
    cp,a=inputs()
    row=dict(status='completed',request=dict(omega=1.9),result=dict(checkpoints=[cp]))
    (directory/'results.json').write_text(json.dumps(dict(rows=[row])))
    assert complete_solver_s6.transient_summary(tmp_path)[0]['passed']
    row['result']['checkpoints'].append(dict(cp,residual=dict(cp['residual'],maximum=11*cp['residual']['maximum'])))
    (directory/'results.json').write_text(json.dumps(dict(rows=[row])))
    assert not complete_solver_s6.transient_summary(tmp_path)[0]['passed']
    row['result']['checkpoints'][-1]['residual']['maximum']=float('nan')
    (directory/'results.json').write_text(json.dumps(dict(rows=[row])))
    assert not complete_solver_s6.transient_summary(tmp_path)[0]['passed']
    row['status']='failed'
    (directory/'results.json').write_text(json.dumps(dict(rows=[row])))
    assert not complete_solver_s6.transient_summary(tmp_path)[0]['passed']
