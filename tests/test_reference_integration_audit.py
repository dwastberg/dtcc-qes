"""The impact auditor must reject changes outside the numerical correction."""
import json
import numpy as np
import pytest
from pathlib import Path
from fixtures.support import load_tool

compare_impact = load_tool("qualify_reference_integration",
    Path(__file__).parents[1]/"tools/qualify_reference_integration.py").compare_impact


def archives(tmp_path, left, right):
    a,b=tmp_path/'a.npz',tmp_path/'b.npz'
    np.savez(a,_policy_revision=np.array('main'),**left)
    np.savez(b,_policy_revision=np.array('candidate'),**right)
    return a,b


def test_reference_dependent_values_can_change_without_relaxing_mean_parity(tmp_path):
    key='public/case/turbulence/tke'
    a,b=archives(tmp_path,{key:np.array([1.])},{key:np.array([2.])})
    assert compare_impact(a,b)['passed']
    a,b=archives(tmp_path,{'public/case/velocity':np.array([1.])},
                 {'public/case/velocity':np.array([2.])})
    assert not compare_impact(a,b)['passed']


@pytest.mark.parametrize('name', ['reference_height','roughness_length','displacement_height'])
def test_morphometric_changes_are_rejected(tmp_path,name):
    key='native/case/turbulence/scalars'
    a,b=archives(tmp_path,{key:json.dumps({name:1.,'reference_speed':1.})},
                 {key:json.dumps({name:2.,'reference_speed':2.})})
    assert not compare_impact(a,b)['passed']


def test_computed_population_and_finite_support_cannot_change(tmp_path):
    key='native/case/turbulence/state'
    a,b=archives(tmp_path,{key:np.array([0,1],np.uint8)},{key:np.array([1,1],np.uint8)})
    assert not compare_impact(a,b)['passed']
    key='native/case/turbulence/stress'
    a,b=archives(tmp_path,{key:np.array([1.,np.nan])},{key:np.array([1.,0.])})
    assert not compare_impact(a,b)['passed']
