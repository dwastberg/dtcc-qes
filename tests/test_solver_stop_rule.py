"""Opt-in SOR relaxation and stop rules (SOLVER_STOP_RULE.md, stage 1).

Stage 1 must leave every default bit-identical: the options are absent from
serialized specs while they hold their defaults, and the native default path
selects exactly the frozen relaxation of each mode.
"""
from dataclasses import replace
import json

import numpy as np
import pytest

from dtcc_qes import wind, _qes
from fixtures.cases import ONE_BUILDING
from fixtures.cities import city_case
from fixtures.condition_state import configuration, prepare
from fixtures.specs import pedestrian_solver


def _legacy_options(iterations, precision="float32", relaxation=None):
    options = _qes.SolverOptions()
    options.max_iterations, options.precision = iterations, precision
    if relaxation is not None:
        options.relaxation = relaxation
    return options


# --- Python specification -------------------------------------------------

def test_default_solver_spec_omits_relaxation():
    assert "relaxation" not in wind.Solver().to_dict()


def test_relaxation_round_trips_and_old_payloads_load():
    solver = wind.Solver(relaxation=1.9)
    payload = json.loads(json.dumps(solver.to_dict()))
    assert payload["relaxation"] == 1.9
    assert wind.Solver.from_dict(payload) == solver
    old = wind.Solver().to_dict()
    assert wind.Solver.from_dict(old).relaxation is None


@pytest.mark.parametrize("value", [0, 2, -1.0, 2.5, float("nan"), float("inf"), True, "1.9"])
def test_invalid_relaxation_rejected(value):
    with pytest.raises(ValueError, match="relaxation"):
        wind.Solver(relaxation=value)


def test_relaxation_rejected_for_adaptive_policy():
    with pytest.raises(ValueError, match="relaxation"):
        replace(pedestrian_solver(), relaxation=1.9)


def test_dataset_payload_accepts_relaxation():
    from dtcc_qes.datasets import QESWindArgs
    from fixtures.datasets import request
    args = QESWindArgs(**request(solver=wind.Solver(relaxation=1.85).to_dict()))
    assert args.solver["relaxation"] == 1.85
    assert "relaxation" not in QESWindArgs(**request()).solver


def test_relaxation_allowed_for_bounded_solver():
    bounded = wind.Solver(max_solve_seconds=5, monitor=wind.MonitorSpec((0, 10, 0, 10)), relaxation=1.85)
    assert bounded.mode == "bounded" and bounded.relaxation == 1.85


# --- Native option --------------------------------------------------------

def test_native_relaxation_defaults_to_zero():
    assert _qes.SolverOptions().relaxation == 0


@pytest.mark.parametrize("precision", ["float32", "float64"])
def test_explicit_legacy_relaxation_is_bitwise_default(precision):
    runner = prepare(configuration())
    condition = _qes.WindCondition()
    default = runner.solve(condition, _legacy_options(8, precision))
    explicit = runner.solve(condition, _legacy_options(8, precision, 1.78))
    np.testing.assert_array_equal(explicit["velocity"], default["velocity"])
    assert explicit["diagnostics"] == default["diagnostics"]


def test_custom_relaxation_changes_the_iterate():
    runner = prepare(configuration())
    condition = _qes.WindCondition()
    default = runner.solve(condition, _legacy_options(8))
    custom = runner.solve(condition, _legacy_options(8, relaxation=1.9))
    assert not np.array_equal(custom["velocity"], default["velocity"])


def test_custom_relaxation_converges_to_the_same_field():
    runner = prepare(configuration())
    condition = _qes.WindCondition()
    fields = []
    for relaxation in (1.78, 1.9):
        options = _legacy_options(6000, "float64", relaxation)
        options.tolerance = 1e-13
        fields.append(runner.solve(condition, options)["velocity"])
    np.testing.assert_allclose(fields[1], fields[0], rtol=0, atol=1e-6 * condition.speed)


@pytest.mark.parametrize("value", [-0.5, 2.0, float("nan")])
def test_native_invalid_relaxation_rejected(value):
    runner = prepare(configuration())
    with pytest.raises(ValueError, match="[Rr]elaxation"):
        runner.solve(_qes.WindCondition(), _legacy_options(2, relaxation=value))
    assert runner.solve(_qes.WindCondition(), _legacy_options(2))["diagnostics"]["iterations"] == 2


def test_native_adaptive_control_rejects_relaxation():
    runner = prepare(configuration())
    control = replace(pedestrian_solver(), max_iterations=2)._native((0, 0, 0), None)
    with pytest.raises(ValueError, match="relaxation"):
        runner.solve(_qes.WindCondition(), _legacy_options(2, relaxation=1.85), control=control)


def test_method_label_follows_relaxation():
    assert _qes._sor_method_id(0) == _qes.legacy_method_id
    assert _qes._sor_method_id(1.78) == _qes.legacy_method_id
    assert _qes._sor_method_id(1.9) == _qes.pedestrian_method_id
    assert _qes._sor_method_id(1.85) == "s5c-rb-sor-float-omega-v1-omega-1.85"
    assert _qes._sor_method_id(1.925) == "s5c-rb-sor-float-omega-v1-omega-1.925"


# --- Public path ----------------------------------------------------------

def _public(solver):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    return wind.run(city, **condition, **grid, solver=solver)


def test_public_relaxation_reaches_native_and_is_reported():
    default = _public(wind.Solver(max_iterations=8))
    same = _public(wind.Solver(max_iterations=8, relaxation=1.78))
    custom = _public(wind.Solver(max_iterations=8, relaxation=1.85))
    np.testing.assert_array_equal(same.velocity, default.velocity)
    assert not np.array_equal(custom.velocity, default.velocity)
    assert default.qualification["solver"]["method"] == _qes.legacy_method_id
    assert custom.qualification["solver"]["method"] == "s5c-rb-sor-float-omega-v1-omega-1.85"
    assert "relaxation" not in default.solver["spec"]
    assert custom.solver["spec"]["relaxation"] == 1.85


def test_bounded_record_reports_custom_method():
    monitor = wind.MonitorSpec((0, 60, 0, 60))
    result = _public(wind.Solver(max_solve_seconds=10, monitor=monitor, max_iterations=4, relaxation=1.85))
    assert result.solver["record"]["method"] == "s5c-rb-sor-float-omega-v1-omega-1.85"
    assert result.qualification["solver"]["method"] == "s5c-rb-sor-float-omega-v1-omega-1.85"
