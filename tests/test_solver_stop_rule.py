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


# --- Native stop rules (stage 1, P1b) ---------------------------------------

def _stop_options(iterations, stop, tolerance=1e-3, precision="float32"):
    options = _legacy_options(iterations, precision)
    options.stop_rule, options.velocity_tolerance = stop, tolerance
    return options


def _bounded_control():
    return wind.Solver(max_solve_seconds=10, monitor=wind.MonitorSpec((0, 100, 0, 80), history_limit=4))._native((0, 0, 0), None)


def test_native_stop_rule_defaults():
    options = _qes.SolverOptions()
    assert options.stop_rule == "multiplier_change" and options.velocity_tolerance == 1e-3


def test_default_rule_reports_no_estimate():
    result = prepare(configuration()).solve(_qes.WindCondition(), _legacy_options(30))
    assert "stop_estimate" not in result


@pytest.mark.parametrize("precision", ["float32", "float64"])
def test_velocity_rule_stops_on_its_estimate(precision):
    result = prepare(configuration()).solve(_qes.WindCondition(), _stop_options(5000, "velocity", precision=precision))
    estimate, diagnostics = result["stop_estimate"], result["diagnostics"]
    assert estimate["rule"] == "velocity" and estimate["termination"] == "velocity_estimate"
    assert diagnostics["converged"] and diagnostics["iterations"] < 5000
    assert estimate["iterations"][-1] == diagnostics["iterations"] == 25 * estimate["checks"]
    assert estimate["estimate"][-1] <= 1e-3 and estimate["estimate"][-2] <= 1e-3
    assert estimate["reference_speed"] == 5.0 and estimate["interval"] == 25 and estimate["tolerance"] == 1e-3
    assert estimate["contraction"][0] is None and estimate["estimate"][0] is None
    assert estimate["safety_factor"] == 2 and estimate["contraction_limit"] == 0.99 and estimate["floor_factor"] == 6
    assert estimate["first_counted_check"] == 4 and estimate["checks"] >= 5
    json.dumps(estimate, allow_nan=False)


def test_fixed_rule_runs_its_work_without_changing_the_iterate():
    runner = prepare(configuration())
    reference_options = _legacy_options(100)
    reference_options.tolerance = 1.2e-7
    reference = runner.solve(_qes.WindCondition(), reference_options)
    fixed = runner.solve(_qes.WindCondition(), _stop_options(100, "fixed"))
    np.testing.assert_array_equal(fixed["velocity"], reference["velocity"])
    estimate = fixed["stop_estimate"]
    assert fixed["diagnostics"]["iterations"] == 100 and estimate["termination"] == "fixed_work"
    assert estimate["iterations"] == [25, 50, 75, 100]


def test_bounded_control_records_the_stop_reason():
    runner = prepare(configuration())
    velocity = runner.solve(_qes.WindCondition(), _stop_options(5000, "velocity"), control=_bounded_control())
    assert velocity["control"]["termination_reason"] == "velocity_estimate"
    assert velocity["diagnostics"]["iterations"] < 5000
    fixed = runner.solve(_qes.WindCondition(), _stop_options(60, "fixed"), control=_bounded_control())
    assert fixed["control"]["termination_reason"] == "fixed_work" and fixed["diagnostics"]["iterations"] == 60


def test_calm_wind_rejects_the_velocity_rule_and_fixes_work_without_estimate():
    runner = prepare(configuration())
    calm = _qes.WindCondition()
    calm.speed = 0
    with pytest.raises(ValueError, match="calm"):
        runner.solve(calm, _stop_options(50, "velocity"))
    fixed = runner.solve(calm, _stop_options(50, "fixed"))
    assert fixed["diagnostics"]["iterations"] == 50 and "stop_estimate" not in fixed


@pytest.mark.parametrize("stop,tolerance", [("invented", 1e-3), ("velocity", 0.0), ("velocity", float("nan")),
                                            ("fixed", -1.0)])
def test_native_invalid_stop_settings_rejected(stop, tolerance):
    runner = prepare(configuration())
    with pytest.raises(ValueError, match="[Ss]top|tolerance"):
        runner.solve(_qes.WindCondition(), _stop_options(10, stop, tolerance))
    assert runner.solve(_qes.WindCondition(), _legacy_options(2))["diagnostics"]["iterations"] == 2


@pytest.mark.parametrize("stop", ["velocity", "fixed"])
def test_native_adaptive_control_rejects_stop_rules(stop):
    runner = prepare(configuration())
    control = replace(pedestrian_solver(), max_iterations=2)._native((0, 0, 0), None)
    with pytest.raises(ValueError, match="stop"):
        runner.solve(_qes.WindCondition(), _stop_options(2, stop), control=control)


# --- Public stop rules (stage 1, P1c) ---------------------------------------

def test_default_solver_spec_omits_stop_fields():
    payload = wind.Solver().to_dict()
    assert "stop" not in payload and "velocity_tolerance" not in payload


def test_stop_fields_round_trip():
    solver = wind.Solver(stop="velocity", velocity_tolerance=3e-4, relaxation=1.9)
    payload = json.loads(json.dumps(solver.to_dict()))
    assert payload["stop"] == "velocity" and payload["velocity_tolerance"] == 3e-4
    assert wind.Solver.from_dict(payload) == solver
    assert "velocity_tolerance" not in wind.Solver(stop="fixed").to_dict()


@pytest.mark.parametrize("change", [dict(stop="invented"), dict(stop=None), dict(velocity_tolerance=0),
                                    dict(velocity_tolerance=float("nan")), dict(velocity_tolerance=True)])
def test_invalid_stop_fields_rejected(change):
    with pytest.raises(ValueError, match="stop|velocity_tolerance"):
        wind.Solver(**change)


@pytest.mark.parametrize("change", [dict(stop="velocity"), dict(stop="fixed"), dict(velocity_tolerance=1e-4)])
def test_stop_fields_rejected_for_adaptive_policy(change):
    with pytest.raises(ValueError, match="stop|velocity_tolerance"):
        replace(pedestrian_solver(), **change)


def test_dataset_payload_accepts_stop_fields():
    from dtcc_qes.datasets import QESWindArgs
    from fixtures.datasets import request
    args = QESWindArgs(**request(solver=wind.Solver(stop="velocity", velocity_tolerance=1e-4).to_dict()))
    assert args.solver["stop"] == "velocity" and args.solver["velocity_tolerance"] == 1e-4


def test_public_velocity_rule_reports_its_estimate(caplog):
    result = _public(wind.Solver(stop="velocity", max_iterations=5000))
    estimate = result.solver["stop_estimate"]
    assert result.diagnostics.converged and result.diagnostics.iterations < 5000
    assert estimate["termination"] == "velocity_estimate" and estimate["tolerance"] == 1e-3
    solver = result.qualification["solver"]
    assert solver["termination_reason"] == "velocity_estimate" and solver["execution"] == "completed"
    assert solver["stop_rule"] == "velocity"
    assert "did not converge" not in caplog.text
    json.dumps(result.metadata, allow_nan=False)


def test_public_velocity_rule_at_its_cap_is_unconverged():
    solver = wind.Solver(stop="velocity", velocity_tolerance=1e-9, max_iterations=30)
    result = _public(solver)
    assert not result.diagnostics.converged
    assert result.qualification["solver"]["termination_reason"] == "iteration_limit"
    with pytest.raises(wind.ConvergenceError, match="remaining-velocity estimate"):
        _public(replace(solver, raise_on_failure=True))


def test_public_fixed_rule_is_not_a_convergence_failure(caplog):
    result = _public(wind.Solver(stop="fixed", max_iterations=60, raise_on_failure=True))
    assert result.diagnostics.iterations == 60
    assert result.qualification["solver"]["termination_reason"] == "fixed_work"
    assert result.qualification["solver"]["execution"] == "completed"
    assert len(result.solver["stop_estimate"]["iterations"]) == 2
    assert "did not converge" not in caplog.text


def test_public_default_rule_keeps_its_records():
    result = _public(wind.Solver(max_iterations=8))
    assert "stop_estimate" not in result.solver
    assert "stop_rule" not in result.qualification["solver"]
    assert result.qualification["solver"]["termination_reason"] == "iteration_limit"


def test_bounded_public_velocity_rule():
    monitor = wind.MonitorSpec((0, 60, 0, 60))
    result = _public(wind.Solver(max_solve_seconds=10, monitor=monitor, stop="velocity", max_iterations=5000))
    assert result.solver["record"]["termination_reason"] == "velocity_estimate"
    assert result.qualification["solver"]["termination_reason"] == "velocity_estimate"
    assert result.diagnostics.converged


# --- Grid-dependent relaxation (decision D7) --------------------------------

@pytest.mark.parametrize("cells, omega", [(250, 1.936), (290, 1.945), (500, 1.968), (580, 1.972),
                                          (64, 1.78), (10, 1.78), (800, 1.98), (5000, 1.98)])
def test_grid_relaxation_rule(cells, omega):
    assert _qes._grid_relaxation(cells) == pytest.approx(omega, abs=5e-7)


def test_grid_relaxation_spec_and_validation():
    solver = wind.Solver(relaxation="grid", stop="velocity")
    assert solver.relaxation == "grid" and solver.to_dict()["relaxation"] == "grid"
    assert wind.Solver.from_dict(json.loads(json.dumps(solver.to_dict()))) == solver
    with pytest.raises(ValueError, match="relaxation"):
        wind.Solver(relaxation="auto")
    with pytest.raises(ValueError, match="relaxation"):
        replace(pedestrian_solver(), relaxation="grid")
    with pytest.raises(ValueError, match="relaxation"):
        options = _legacy_options(8, relaxation=1.9)
        options.grid_relaxation = True
        prepare(configuration()).solve(_qes.WindCondition(), options)


def test_public_grid_relaxation_resolves_from_the_domain():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    result = wind.run(city, **condition, **grid, solver=wind.Solver(max_iterations=8, relaxation="grid"))
    cells = min(result.velocity.shape[1:3])
    omega = result.solver["relaxation"]
    assert omega == pytest.approx(_qes._grid_relaxation(cells), abs=0)
    assert result.qualification["solver"]["method"] == _qes._sor_method_id(omega)
    explicit = wind.run(city, **condition, **grid, solver=wind.Solver(max_iterations=8, relaxation=float(omega)))
    np.testing.assert_array_equal(result.velocity, explicit.velocity)
    assert "relaxation" not in explicit.solver
    assert "relaxation" not in wind.run(city, **condition, **grid, solver=wind.Solver(max_iterations=8)).solver
