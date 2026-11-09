import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from replay_reference_sampling import manufactured_checks,sample,source_cells

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def manufactured():
    import os
    executable=Path(os.environ.get('DTCC_QES_REFERENCE_PROBE', ROOT/'build/reference-sampling/native/reference_sampling_probe'))
    if not executable.exists():pytest.skip('Build the native reference-sampling investigation probe')
    p=subprocess.run([str(executable),'--manufactured'],text=True,capture_output=True,timeout=60,check=True)
    return json.loads(p.stdout)


def test_native_manufactured_affine_vector_and_support_oracles(manufactured):
    r=manufactured_checks(manufactured)
    assert r['cases']==48
    assert all(r['guards'].values())
    assert max(v['candidate_max_error'] for v in r['errors']['affine'].values())<1e-6


def test_curved_point_error_decreases_at_second_order(manufactured):
    rows=manufactured_checks(manufactured)['errors']['curved']
    errors=[rows[str(h)]['candidate_max_error'] for h in (.035,.0175,.00875,.004375)]
    np.testing.assert_allclose(np.array(errors[:-1])/errors[1:],4,rtol=.005)


def test_micrometre_face_motion_does_not_create_a_candidate_velocity_jump(manufactured):
    rows=[r for r in manufactured['cases'] if r['spacing']==.0175 and r['field']=='affine']
    assert np.ptp([r['legacy_float_mean'] for r in rows])>.03
    assert np.ptp([r['interpolation']['double_mean'] for r in rows])<1e-6


def test_constant_horizontal_mean_is_stable_with_wide_accumulation(manufactured):
    rows=manufactured['constant_reductions']
    assert rows[-1]['columns']==45056
    assert abs(rows[-1]['float_mean']-rows[-1]['oracle'])>1e-4
    assert max(abs(r['double_mean']-r['oracle']) for r in rows)<2e-12


def test_morphometric_targets_expose_count_sensitive_float_accumulation(manufactured):
    a,b=manufactured['morphometric_references']
    assert a!=b and abs(a-.21)<2e-7 and abs(b-.21)<2e-7


def fixtures():
    def row(cell,tensor):return dict(cell=cell,actual_stress=tensor,replays=[tensor]*4)
    raw=dict(sources=[row([0,0,0],[1,0,0,1,0,1]),row([1,0,0],[-1,0,0,1,0,1])])
    record=dict(support=dict(contributors=dict(indices=[[[0,0,0],[1,0,0],[-1,-1,-1]]],weights=[[1,0,0]])))
    return raw,record


def test_zero_weight_source_is_not_used_or_requested():
    raw,record=fixtures()
    assert source_cells(record)==[(0,0,0)]
    _,values=sample(raw,record,0)
    assert values[0][1]
    np.testing.assert_array_equal(values[0][0],[1,0,0,1,0,1])


def test_valid_interpolant_does_not_rescue_invalid_positive_weight_source():
    raw,record=fixtures();record['support']['contributors']['weights']=[[.8,.2,0]]
    _,values=sample(raw,record,0)
    assert not values[0][1]
    assert values[0][0][0]>0
