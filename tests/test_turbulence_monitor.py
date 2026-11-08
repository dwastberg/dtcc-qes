"""Checkpoint turbulence must preserve solver trajectory and canonical sampling."""
from dataclasses import replace

import numpy as np
import pytest

from dtcc_qes import wind
from fixtures.cities import city_case
from fixtures.cases import ONE_BUILDING


@pytest.mark.parametrize('precision', ['float32', 'float64'])
@pytest.mark.parametrize('direction', [270., 225.])
def test_turbulence_monitor_matches_final_fields_without_changing_solve(precision, direction):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    condition['profile'] = replace(condition['profile'], direction=direction)
    points = np.array([[11., 17., 1.5], [44.5, 30.5, 1.75], [35., 30., 2.], [0., 0., 2.]])
    monitor = wind.MonitorSpec(region=(4., 70., 4., 50.), heights=(),
        receptors=tuple(wind.Receptor(str(i), *p, required=False) for i, p in enumerate(points)),
        global_mass=True, turbulence=True)
    settings = dict(tolerance=1.2e-7 if precision=='float32' else 1e-12, max_iterations=75, precision=precision)
    plain = wind.run(city, **condition, **grid, turbulence=wind.Turbulence(), solver=wind.Solver(**settings))
    observed = wind.run(city, **condition, **grid, turbulence=wind.Turbulence(),
        solver=wind.Solver(**settings, max_solve_seconds=60, checkpoint_interval=25, monitor=monitor))
    np.testing.assert_array_equal(plain.velocity, observed.velocity)
    np.testing.assert_array_equal(plain.turbulence.stress, observed.turbulence.stress)
    np.testing.assert_array_equal(plain.turbulence.tke, observed.turbulence.tke)
    assert plain.diagnostics == observed.diagnostics
    history = observed.solver['record']['checkpoint_history']
    assert [h['iteration'] for h in history] == [0,25,50,75]
    sample = observed.sample_points(points, 'linear')
    for i, record in enumerate(history[-1]['receptors']):
        turb = record['turbulence']
        assert turb['computed'] == np.isfinite(sample.stress[i]).all()
        assert turb['valid'] == bool(sample.stress_valid[i])
        if turb['computed']:
            np.testing.assert_allclose(turb['stress'], sample.stress[i], rtol=1e-6, atol=1e-7)
            assert np.isfinite(turb['gradient']).all()
            assert turb['uncapped_tke'] >= turb['tke'] - 1e-6
    for checkpoint in history:
        mass = checkpoint['mass'][0]
        for band in ('interior', 'top_band'):
            flux = mass[band]
            assert flux['net_cell_flux'] == pytest.approx(flux['boundary_flux'], abs=1e-9)


def test_monitor_rejects_turbulence_request_without_model():
    city,condition,grid,_ = city_case(ONE_BUILDING)
    monitor=wind.MonitorSpec(region=(4.,70.,4.,50.),turbulence=True)
    with pytest.raises(ValueError,match='requires enabled turbulence'):
        wind.run(city, **condition, **grid, solver=wind.Solver(max_solve_seconds=60, monitor=monitor))
