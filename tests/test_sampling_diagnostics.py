"""Support evidence must explain failures without changing the sampled answer."""
from dataclasses import replace
import json

import numpy as np
import pytest

from dtcc_qes import wind
from fixtures.sampling import manufactured


def turbulent():
    r=manufactured();shape=r.cell_flags.shape
    stress=np.zeros((*shape,6),np.float32);stress[...,[0,3,5]]=2
    return replace(r,turbulence=wind.TurbulenceFields(stress,np.ones(shape),np.ones(shape),np.ones(shape),
        np.ones(shape,bool),np.zeros(shape,bool),np.ones(shape,bool),1,5,10,.1,0))


@pytest.mark.parametrize('method',['linear','nearest'])
@pytest.mark.parametrize('frame',['local','global'])
def test_diagnostics_preserve_values_masks_and_owned_coordinates(method,frame):
    r=turbulent();r.cell_flags[1,1,1]=0;r.turbulence.stress[3,1,1]=[1,2,0,1,0,1]
    points=np.array([[1,1,.5],[2.5,2.5,1.75],[0,0,0],[10,10,2.]])
    if frame=='global':points+=r.origin
    ordinary=r.sample_points(points,method,frame=frame)
    detailed=r.sample_points(points,method,frame=frame,diagnostics=True,include_contributors=True)
    for key in ('velocity','valid','stress','stress_valid','sampled_points','streamwise_std'):
        np.testing.assert_array_equal(getattr(ordinary,key),getattr(detailed,key))
    assert ordinary.support is None
    d=detailed.support.contributors;weights=d['weights'];active=weights>0
    np.testing.assert_allclose(weights.sum(axis=1),np.isfinite(detailed.sampled_points).all(axis=1))
    assert np.all(d['indices'][~active]==-1)
    np.testing.assert_allclose(np.sum(d['points'][1,active[1]]*weights[1,active[1],None],axis=0),detailed.sampled_points[1])
    json.dumps(detailed.support.to_dict(),allow_nan=False)
    r.turbulence.stress[:]=0
    np.testing.assert_array_equal(detailed.support.contributors['weights'],weights)


def test_independent_reasons_can_coexist_and_interpolant_does_not_hide_source_failure():
    r=turbulent();r.turbulence.stress[:,:,0]=[1,2,0,1,0,1]
    r.turbulence.stress[:,:,1]=[3,-2,0,3,0,3]
    s=r.sample_points([[1,1,1.5]],'linear',diagnostics=True)
    assert s.support.geometric[0] and s.support.computed[0]
    assert s.support.interpolant_valid[0] and not s.support.contributors_valid[0]
    assert s.support.reasons==(('invalid_contributor_covariance',),)
    r.cell_flags[1,0,0]=2;r.velocity[1,0,0]=np.nan;r.turbulence.computed[1,0,0]=False
    s=r.sample_points([[1,1,1.5]],'linear',diagnostics=True)
    assert set(s.support.reasons[0])=={'positive_solid_weight','nonfinite_velocity',
        'uncomputed_contributor','invalid_contributor_covariance'}
    assert s.support.solid_weight[0]>0


def test_exact_centres_ignore_solid_neighbours_and_report_nonuniform_positive_weights():
    r=turbulent();r.cell_flags[3,1,2]=0
    points=[[1.5,1.5,1.75],[2.5,1.5,2.25]]
    s=r.sample_points(points,'linear',diagnostics=True,include_contributors=True)
    assert s.support.geometric.tolist()==[True,False]
    assert s.support.solid_weight[1]==pytest.approx(1/3)
    assert np.count_nonzero(s.support.contributors['weights'][0])==1
    s.support.geometric[:]=False
    assert r.sample_points(points[:1],'linear',diagnostics=True).support.geometric[0]


def test_unsupported_points_do_not_invent_uncomputed_or_covariance_reasons():
    r=turbulent();s=r.sample_points([[.1,1,1.],[10,1,1]],'linear',diagnostics=True)
    assert s.support.reasons==(('outside_center_range',),('outside_domain',))
    assert not s.support.computed.any() and np.isnan(s.support.solid_weight).all()
    empty=r.sample_points(np.empty((0,3)),diagnostics=True,include_contributors=True)
    assert empty.support.contributors['indices'].shape==(0,8,3)
    no_turbulence=replace(r,turbulence=None).sample_points([[1,1,1]],diagnostics=True)
    assert no_turbulence.support.computed is None
    with pytest.raises(ValueError,match='requires diagnostics'):
        r.sample_points([[1,1,1]],include_contributors=True)
