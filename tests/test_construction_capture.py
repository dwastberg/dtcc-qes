"""Read-only construction/stage capture must preserve the native answer and lifecycle."""
import numpy as np
import pytest

from dtcc_qes import _qes,wind
from fixtures.condition_state import configuration,prepare


def inputs():
    c=_qes.WindCondition();c.direction=270
    options=_qes.SolverOptions();options.precision='float64';options.max_iterations=12;options.tolerance=1e-12
    monitor=wind.MonitorSpec((0,100,0,80),heights=(),receptors=(wind.Receptor('p',11,21,3),),
        global_mass=True,turbulence=True,history_limit=20)
    control=wind.Solver(max_solve_seconds=10,checkpoint_interval=3,monitor=monitor)._native((0,0,0),None)
    return c,options,control


@pytest.mark.parametrize('stretched',[False,True])
def test_trace_preserves_all_fields_and_captures_native_tensor_and_face_values(stretched):
    runner=prepare(configuration(stretched),0);c,options,control=inputs()
    expected=runner.solve(c,options,control=control)
    cells=[[5,10,1],[5,10,2],[5,11,1]]
    actual=runner._solve_trace(c,options,control=control,cells=cells,tensor_cells=cells)
    for key in ('velocity','cell_flags'):
        np.testing.assert_array_equal(actual[key],expected[key])
    for key in ('stress','tke','co_eps','mixing_length','state','stress_valid'):
        np.testing.assert_array_equal(actual['turbulence'][key],expected['turbulence'][key])
    assert actual['diagnostics']==expected['diagnostics']
    trace=actual['trace'];i,j,k=np.array(cells).T
    np.testing.assert_array_equal(trace['tensors'][2],actual['turbulence']['stress'][k,j,i])
    assert np.all(trace['tensor_found'])
    assert trace['tensor_stages']==['pre_anisotropy','post_anisotropy','post_bound']
    frame=trace['frames'][-1];assert frame['stage']=='projection' and frame['building']==-1
    centred=np.float32(.5)*(frame['faces'][:,::2]+frame['faces'][:,1::2])
    np.testing.assert_array_equal(centred,actual['velocity'][k,j,i])
    assert {f['building'] for f in trace['frames'] if f['building']>=0}=={0,1,2}
    assert trace['properties'].shape==(3,14)
    assert trace['orientations'].shape==(3,5)
    np.testing.assert_allclose(np.sum(trace['orientations'][:,:2]**2,axis=1),1.,atol=4e-16)
    properties=trace['properties'];g=properties[:,:9].reshape(-1,3,3)
    s=.5*(g+g.transpose(0,2,1))
    nu=properties[:,9]**2*np.sqrt(2*np.sum(s*s,axis=(1,2)))
    np.testing.assert_allclose(properties[:,10],nu,rtol=2e-6)
    assert np.all(properties[:,11]<=properties[:,12]+1e-6)
    # A later solve neither retains an observer nor borrows returned trace storage.
    before=trace['tensors'].copy();c.direction=225
    runner.solve(c,options,control=control)
    np.testing.assert_array_equal(trace['tensors'],before)
    c.direction=270
    repeated=runner.solve(c,options,control=control)
    np.testing.assert_array_equal(repeated['turbulence']['stress'],expected['turbulence']['stress'])


@pytest.mark.parametrize('change',[
    dict(cells=[[-1,0,0]]),dict(cells=[[50,0,0]]),dict(tensor_cells=[[1,1,20]]),
    dict(cells=[[1,1,1],[1,1,1]]),dict(maximum_frames=0),dict(maximum_frames=1025),
    dict(cells=[],tensor_cells=[]),dict(cells=[[1,1,1]],maximum_frames=1)])
def test_invalid_or_exhausted_capture_does_not_poison_reused_runner(change):
    runner=prepare(configuration(),0);c,options,control=inputs()
    expected=runner.solve(c,options,control=control)
    args=dict(cells=[[5,10,1]],tensor_cells=[[5,10,1]])|change
    with pytest.raises(ValueError):runner._solve_trace(c,options,control=control,**args)
    actual=runner.solve(c,options,control=control)
    np.testing.assert_array_equal(actual['velocity'],expected['velocity'])
    np.testing.assert_array_equal(actual['turbulence']['stress'],expected['turbulence']['stress'])


def test_trace_rejects_adaptive_or_disabled_turbulence_without_solver_work():
    c,options,control=inputs();runner=prepare(configuration(),0)
    changed={**control,'mode':'adaptive','policy':'pedestrian-v1','checkpoint_interval':25}
    with pytest.raises(ValueError,match='Read-only trace requires'):
        runner._solve_trace(c,options,control=changed,tensor_cells=[[5,10,1]])
    runner=prepare(configuration())
    with pytest.raises(ValueError,match='Read-only trace requires'):
        runner._solve_trace(c,options,control=control,tensor_cells=[[5,10,1]])


def test_canyon_branch_observer_preserves_fields_and_detaches_after_limit_failure():
    runner=prepare(configuration(),0);c,options,control=inputs()
    expected=runner.solve(c,options,control=control)
    actual=runner._solve_trace(c,options,control=control,cells=[[5,10,1]],tensor_cells=[[5,10,1]],canyon_buildings=[0,1,2])
    np.testing.assert_array_equal(actual['velocity'],expected['velocity'])
    np.testing.assert_array_equal(actual['turbulence']['stress'],expected['turbulence']['stress'])
    assert 'incident' in actual['trace']['canyon_events']
    assert actual['trace']['canyon_values'].shape[1]==16
    with pytest.raises(ValueError,match='decision trace limit'):
        runner._solve_trace(c,options,control=control,cells=[[5,10,1]],canyon_buildings=[0],maximum_decisions=1)
    repeated=runner.solve(c,options,control=control)
    np.testing.assert_array_equal(repeated['velocity'],expected['velocity'])
    for bad in ([-1],[3],[0,0]):
        with pytest.raises(ValueError,match='canyon trace actor'):
            runner._solve_trace(c,options,control=control,cells=[[5,10,1]],canyon_buildings=bad)


def test_stage_only_capture_has_the_same_values_with_a_smaller_frame_budget():
    runner = prepare(configuration(), 0)
    condition, options, control = inputs()
    args = dict(control=control, cells=[[5, 10, 1]], tensor_cells=[[5, 10, 1]])
    full = runner._solve_trace(condition, options, **args)
    stages = [frame for frame in full['trace']['frames'] if frame['building'] == -1]
    assert len(stages) < len(full['trace']['frames'])
    compact = runner._solve_trace(condition, options, **args,
                                 building_frames=False, maximum_frames=len(stages))
    assert len(compact['trace']['frames']) == len(stages)
    for expected, actual in zip(stages, compact['trace']['frames'], strict=True):
        assert actual['stage'] == expected['stage']
        assert actual['building'] == -1
        np.testing.assert_array_equal(actual['faces'], expected['faces'])
        np.testing.assert_array_equal(actual['flags'], expected['flags'])
    np.testing.assert_array_equal(compact['velocity'], full['velocity'])
    np.testing.assert_array_equal(compact['trace']['tensors'], full['trace']['tensors'])
    with pytest.raises(ValueError, match='frame limit'):
        runner._solve_trace(condition, options, **args,
                           building_frames=False, maximum_frames=len(stages) - 1)
    repeated = runner.solve(condition, options, control=control)
    np.testing.assert_array_equal(repeated['velocity'], full['velocity'])
