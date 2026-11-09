"""Production reference support and component interpolation contracts."""
import numpy as np
import pytest
from dtcc_core.model import City
from dtcc_qes import wind


def test_reference_metadata_matches_independent_physical_column_reduction():
    profile = wind.MeasuredProfile.from_components(
        [.5, 1.5, 3.5, 8., 20.], [1., 2., 4., 7., 10.], [2., 1., -1., -2., 0.],
        reference_height=8., roughness_length=.021, below='log', above='constant')
    result = wind.run(City(), profile, resolution=2., bounds=(0,0,0,16,16,24),
        turbulence=wind.Turbulence())
    reference = result.metadata['turbulence']['reference']
    support = reference['sampling']
    lo, hi = support['lower_index'], support['upper_index']
    assert result.z[lo] == support['lower_height']
    assert result.z[hi] == support['upper_height']
    assert support['lower_weight']+support['upper_weight'] == 1
    assert support['lower_height'] <= reference['height'] <= support['upper_height']
    vectors = (support['lower_weight']*result.velocity[lo].astype(float)
               +support['upper_weight']*result.velocity[hi].astype(float))
    oracle = np.linalg.norm(vectors, axis=-1).mean()
    assert support['valid_columns'] == len(result.x)*len(result.y)
    assert support['excluded_columns'] == 0
    assert support['mean_speed_float64'] == pytest.approx(oracle, abs=2e-14)
    assert result.turbulence.reference_speed == float(np.float32(oracle))


@pytest.mark.parametrize('operation', ['preview_grid', 'run'])
def test_below_first_centre_reference_is_rejected_during_domain_planning(operation):
    with pytest.raises(ValueError, match='below the first physical cell centre; refine the first layer'):
        getattr(wind, operation)(City(), wind.LogProfile(3.,270.,roughness_length=.001),
            resolution=2., bounds=(0,0,0,16,16,24), turbulence=wind.Turbulence())
