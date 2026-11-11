from dataclasses import FrozenInstanceError, replace
import json
import tracemalloc
import numpy as np
import pytest
from fixtures.turbulence import synthetic, solve


def test_completed_with_bad_sampling_is_not_physical_validation():
    result = synthetic()
    result.turbulence.stress[1,0,0] = [1,2,0,1,0,1]
    sample = result.sample_points([[.5,.5,1.5],[-100,0,1]], 'linear', diagnostics=True)
    before = sample.velocity.copy()
    payload = result.quality_report(sample).to_dict()
    assert payload['solver']['execution'] == 'completed'
    assert payload['sample']['requested'] == 2
    assert payload['sample']['invalid'] > 0
    assert payload['sample']['reason_counts_overlap']
    assert payload['sample']['reasons']
    assert payload['physical_validation'] == 'not_established_by_this_report'
    np.testing.assert_array_equal(sample.velocity,before)
    json.dumps(payload,allow_nan=False)


def test_snapshot_is_deeply_independent():
    source = solve()
    report = source.quality_report()
    before = report.to_dict()
    source.metadata['turbulence']['cap']['computed_cells'] = -7
    source.turbulence.stress[:] = np.nan
    assert report.to_dict() == before
    changed = report.to_dict(); changed['solver']['exclusions'].append('edited')
    assert report.to_dict() == before
    with pytest.raises(FrozenInstanceError):
        report._json = '{}'
    assert 'physical accuracy' in report.summary()


def test_unknown_nonfinite_and_no_support_are_explicit():
    source = replace(synthetic(), metadata={}, diagnostics=replace(synthetic().diagnostics,
        max_divergence=np.nan, rms_divergence=np.inf))
    sample = source.sample_points([[1,1,1]])
    data = source.quality_report(sample).to_dict()
    assert data['turbulence'] is None
    assert data['sample']['unsupported'] is None
    assert data['divergence']['max'] is None
    assert data['unavailable_reasons']['divergence.max'] == 'nonfinite_recorded_value'
    assert data['unavailable_reasons']['sample.unsupported'] == 'sampling_diagnostics_not_requested'
    assert data['divergence']['highest_physical_layer']['status'] == 'unavailable'
    json.dumps(data,allow_nan=False)


def test_report_does_not_read_fields_or_allocate_by_grid_size():
    class Forbidden:
        def __getattribute__(self, name):
            raise AssertionError('Field accessed: '+name)
    source = replace(synthetic(),velocity=Forbidden(),cell_flags=Forbidden(),turbulence=Forbidden())
    tracemalloc.start()
    data = source.quality_report().to_dict()
    _, peak = tracemalloc.get_traced_memory();tracemalloc.stop()
    assert peak < 1024**2
    assert data['schema_version'] == 1


def test_solve_time_calm_and_counts():
    source = solve(speed=0)
    data = source.quality_report().to_dict()
    assert data['turbulence']['computed'] > 0
    assert data['turbulence']['invalid'] == 0
    assert data['turbulence']['reference_speed'] == 0
    assert data['divergence']['top_band']['status'] == 'assessed'
