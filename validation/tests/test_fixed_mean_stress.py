import numpy as np

from replay_fixed_mean_stress import sample_tensors,score


def capture():
    trace=dict(tensor_cells=np.array([[0,0,0],[1,0,0]]),tensor_found=np.ones((3,2),bool))
    samples=dict(x=np.array([0.,2.]),y=np.array([0.,2.]),z=np.array([0.,2.]),origin=np.zeros(3))
    raw=np.array([[-1,0,0,2,0,2],[3,0,0,2,0,2]],np.float32)
    return trace,samples,raw


def test_positive_interpolant_cannot_hide_indefinite_positive_weight_source():
    trace,samples,raw=capture()
    r=sample_tensors(raw,trace,samples,[[1,0,0],[2,0,0]])
    np.testing.assert_array_equal(r['covered'],[True,True])
    np.testing.assert_array_equal(r['interpolant_valid'],[True,True])
    np.testing.assert_array_equal(r['valid'],[False,True])
    np.testing.assert_array_equal(r['invalid_source_weight'],[.5,0])


def test_missing_or_uncomputed_positive_support_stays_unavailable():
    trace,samples,raw=capture();trace['tensor_found'][2,0]=False
    r=sample_tensors(raw,trace,samples,[[1,0,0]])
    assert not r['covered'][0] and np.isnan(r['stress']).all()
    trace['tensor_cells']=trace['tensor_cells'][1:];trace['tensor_found']=trace['tensor_found'][:,1:]
    assert not sample_tensors(raw[1:],trace,samples,[[1,0,0]])['covered'][0]


def test_fixed_population_score_refuses_to_improve_by_losing_an_observation():
    r=score([1,np.nan,0],[1,3,0],[True,True,False])
    assert r['count']==2 and not r['complete'] and 'rmse' not in r
    np.testing.assert_array_equal(r['missing_indices'],[1])
    assert score([1,3,999],[1,3,0],[True,True,False])['rmse']==0
