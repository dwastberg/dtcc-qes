"""A prepared geometry must reproduce a fresh condition, including after failure."""
import numpy as np
import pytest

from dtcc_qes import _qes


from fixtures.condition_state import assert_same, configuration, prepare, solve

@pytest.mark.parametrize('precision', ['float32', 'float64'])
@pytest.mark.parametrize('stretched', [False, True])
@pytest.mark.parametrize('method', [None, 0, 1])
def test_reused_directions_and_precision_changes_match_fresh(precision, stretched, method):
    config = configuration(stretched)
    reused = prepare(config, method)
    for direction, arithmetic in [(270, precision), (45, precision), (33, precision),
                                  (300, 'float64' if precision == 'float32' else 'float32'),
                                  (33, precision), (225, precision), (45, precision), (270, precision)]:
        assert_same(solve(reused, direction, arithmetic), solve(prepare(config, method), direction, arithmetic))


@pytest.mark.parametrize('field,value', [('rooftop_flag', 1), ('rooftop_flag', 2),
                                         ('street_canyon_flag', 1), ('sidewall_flag', 1)])
def test_wake_dependencies_rejected_before_geometry_and_preserve_preparation(field, value):
    config = configuration(rooftop_flag=0, street_canyon_flag=0, sidewall_flag=0, wake_flag=0)
    runner = prepare(config)
    expected = solve(runner, 33)
    grid, model, arrays = configuration(rooftop_flag=0, street_canyon_flag=0, sidewall_flag=0, wake_flag=0)
    setattr(model, field, value)
    arrays['heights'][:] = np.nan  # Dependency error must precede geometry construction.
    with pytest.raises(ValueError, match='wake_flag must be nonzero'):
        runner.prepare(grid, model, **arrays)
    assert_same(solve(runner, 33), expected)


@pytest.mark.parametrize('cavity', [0, 1, 2, 3])
def test_wake_free_independent_cavity_is_supported(cavity):
    config = configuration(rooftop_flag=0, street_canyon_flag=0, sidewall_flag=0, wake_flag=0,
                           upwind_cavity_flag=cavity)
    reused = prepare(config)
    solve(reused, 270)
    assert_same(solve(reused, 45), solve(prepare(config), 45))


@pytest.mark.parametrize('precision', ['float32', 'float64'])
def test_failed_condition_resets_rooftop_decision_on_retry(precision):
    config = configuration()
    reused = prepare(config)
    solve(reused, 270, precision)
    with pytest.raises(ValueError, match='Initial wind arrays'):
        solve(reused, 270, precision, speed=1e38)
    assert_same(solve(reused, 45, precision), solve(prepare(config), 45, precision))


@pytest.mark.parametrize('precision', ['float32', 'float64'])
def test_numerical_failure_discards_workspace_and_allows_retry(precision):
    config = configuration(rooftop_flag=0, upwind_cavity_flag=0, street_canyon_flag=0,
                           sidewall_flag=0, wake_flag=0)
    reused = prepare(config)
    solve(reused, 270, precision)
    # Finite input drives the float32 iterate into overflow. This enters the
    # real numerical-failure path without adding a production injection hook.
    with pytest.raises(RuntimeError, match='Non-finite Lagrange multiplier change'):
        solve(reused, 270, speed=4e37, iterations=500)
    assert_same(solve(reused, 45, precision), solve(prepare(config), 45, precision))
