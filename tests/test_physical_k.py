from dataclasses import replace
import numpy as np
import pytest
from dtcc_qes import wind
from dtcc_qes._statistics import _physical_k, _stress_validity
from fixtures.turbulence import synthetic, uniform_synthetic, solve
from fixtures.cases import FLAT


def test_rotated_covariance_calm_and_invalid_inputs():
    rng = np.random.default_rng(702)
    rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    tensor = rotation @ np.diag([1., 4., 9.]) @ rotation.T
    packed = tensor[(0,0,0,1,1,2),(0,1,2,1,2,2)]
    raw = np.array([packed, [0]*6, [1,2,0,1,0,1], [1,0,0,np.nan,0,1]])
    before = raw.copy()
    energy = _physical_k(raw, np.ones(4, bool))
    np.testing.assert_allclose(energy[:2], [7, 0])
    assert np.isnan(energy[2:]).all()
    np.testing.assert_array_equal(raw, before)
    np.testing.assert_array_equal(energy, _physical_k(raw, np.ones(4,bool), validity=_stress_validity(raw)))


def test_coverage_and_current_state():
    source = synthetic()
    np.testing.assert_array_equal(source.physical_k, 3.5)
    source.turbulence.stress_valid[:] = False
    assert np.isfinite(source.physical_k).all()
    source.turbulence.stress[1,0,0] = [1,2,0,1,0,1]
    source.turbulence.computed[1,1,1] = False
    source.cell_flags[1,1,2] = 0
    source.cell_flags[1,1,3] = 2
    assert np.isnan(source.physical_k[1,0,0])
    assert np.isnan(source.physical_k[1,1,1:4]).all()
    source.turbulence.stress[:] = [0]*6
    source.velocity[:] = 0
    assert (source.physical_k[np.isfinite(source.physical_k)] == 0).all()


def test_tolerance_edge_and_shape_validation():
    raw = np.array([[-np.finfo(np.float32).eps,0,0,1,0,2]])
    assert np.isfinite(_physical_k(raw, [True])).all()
    raw[0,0] = -1e-3
    assert np.isnan(_physical_k(raw, [True])).all()
    with pytest.raises(ValueError, match='matching'):
        _physical_k(raw, [True, True])


@pytest.mark.parametrize('point_sample', [False, True])
def test_contributor_evidence_and_calm_sample(point_sample):
    source = synthetic()
    source.velocity[:] = 0
    source.turbulence.stress[1,0,0] = [1,2,0,1,0,1]
    source.turbulence.stress[2,0,0] = [3,-2,0,3,0,3]
    midpoint = float((source.z[1] + source.z[2]) / 2)
    if point_sample:
        sample = source.sample_points([[source.x[0],source.y[0],midpoint],
                                       [source.x[1],source.y[1],midpoint]], 'linear')
    else:
        sample = source.sample(midpoint, 'linear')
    assert _stress_validity(sample.stress)[0].all()
    assert np.isnan(sample.physical_k.flat[0])
    assert np.isfinite(sample.physical_k).any()
    sample.stress[:] = [1,2,0,1,0,1]
    assert np.isnan(sample.physical_k).all()
    sample.stress[:] = [4,0,0,2,0,1]
    sample.stress_valid[:] = True
    assert np.isnan(sample.physical_k.flat[0])


def test_export_order_provenance_and_roundtrip():
    source = uniform_synthetic()
    default = {f.name:f for f in source.to_dtcc().fields}
    grid = source.to_dtcc(include_physical_k=True)
    restored = type(grid)()
    restored.from_proto(grid.to_proto())
    fields = {f.name:f for f in restored.fields}
    assert set(fields) == set(default) | {'physical_k'}
    for name in default:
        np.testing.assert_array_equal(fields[name].values, default[name].values)
    field = fields['physical_k']
    assert field.unit == 'm^2/s^2'
    assert 'Half the final covariance trace' in field.description
    assert 'numerics_version=' in field.description
    nz, ny, nx = source.cell_flags.shape
    np.testing.assert_array_equal(field.values, [source.physical_k[z,y,x]
        for y in range(ny) for x in range(nx) for z in range(nz)])


def test_missing_turbulence():
    source = replace(uniform_synthetic(), turbulence=None)
    for obj in (source, source.sample(1.5), source.sample_points([[1,1,1]])):
        with pytest.raises(ValueError, match='no turbulence'):
            _ = obj.physical_k
    with pytest.raises(ValueError, match='no turbulence'):
        source.to_dtcc(include_physical_k=True)
