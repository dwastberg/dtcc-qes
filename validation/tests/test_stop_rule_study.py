"""SOLVER_STOP_RULE.md P2-P3: harness fields, study matrix and offline stop replay."""

import json
from dataclasses import replace

import pytest

from aij import campaigns, runner, stop_rule
from aij.runspec import RunSpec


def test_default_solver_fields_keep_run_keys():
    base = campaigns.case_d(0.0, resolution=2.0, turbulence=False)
    explicit = campaigns.case_d(0.0, resolution=2.0, turbulence=False, relaxation=None,
                                stop="multiplier_change", velocity_tolerance=1e-3)
    assert explicit.key == base.key == "3af75ea91b3dfde2"
    assert not {"relaxation", "stop", "velocity_tolerance"} & set(base.to_dict())


def test_solver_fields_change_key_and_name():
    base = campaigns.case_d(0.0, resolution=2.0, turbulence=False)
    study = replace(base, relaxation=1.9, stop="fixed")
    assert study.key != base.key
    assert study.name.endswith("w1.9-fixed")
    assert RunSpec.from_dict(json.loads(json.dumps(study.to_dict()))) == study
    tolerance = replace(base, stop="velocity", velocity_tolerance=3e-4)
    assert tolerance.name.endswith("velocity3e-04")


def test_solver_fields_reach_the_solver():
    spec = campaigns.case_d(0.0, resolution=8.0, relaxation=1.9, stop="velocity", velocity_tolerance=3e-4)
    solver = runner.inputs(spec)["run"]["solver"]
    assert (solver.relaxation, solver.stop, solver.velocity_tolerance) == (1.9, "velocity", 3e-4)


def test_study_matrix():
    specs = campaigns.campaign("stop_rule_study")
    runs = [s for s in specs if s.precision == "float32"]
    references = [s for s in specs if s.precision == "float64"]
    assert len(runs) == 7 * 2 * len(stop_rule.OMEGAS) and len(references) == 7 * 2
    assert {s.relaxation for s in runs} == set(stop_rule.OMEGAS)
    assert all(s.stop == "fixed" and s.monitor and not s.turbulence for s in runs)
    assert all(s.max_iterations == stop_rule.BUDGETS[s.resolution] for s in runs)
    assert all(s.stop == "fixed" and not s.monitor and s.relaxation == stop_rule.REFERENCE_RELAXATION
               for s in references)
    assert {s.resolution for s in specs} == {2.0, 1.0}
    assert set(campaigns.campaign("stop_rule_2m")) | set(campaigns.campaign("stop_rule_1m")) == set(specs)
    assert len({s.key for s in specs}) == len(specs)


@pytest.fixture(scope="module")
def fixed_and_velocity():
    base = campaigns.case_d(0.0, resolution=8.0, turbulence=False, relaxation=1.9, max_iterations=600)
    fixed = runner.run(replace(base, stop="fixed", monitor=True))[0]
    velocity = runner.run(replace(base, stop="velocity", velocity_tolerance=1e-3))[0]
    return fixed, velocity


def test_record_holds_the_estimate_history(fixed_and_velocity):
    fixed, _ = fixed_and_velocity
    estimate = fixed["stop_estimate"]
    assert estimate["rule"] == "fixed" and estimate["iterations"][:3] == [25, 50, 75]
    assert estimate["iterations"][-1] == 600 == fixed["history"]["iterations"][-1]
    assert fixed["qualification"]["solver"]["termination_reason"] == "fixed_work"


def test_offline_replay_matches_the_native_rule(fixed_and_velocity):
    fixed, velocity = fixed_and_velocity
    stop = stop_rule.replay(fixed["stop_estimate"], 1e-3)
    assert velocity["stop_estimate"]["termination"] == "velocity_estimate"
    assert stop == (velocity["diagnostics"]["iterations"], "velocity_estimate")
    assert stop_rule.replay(fixed["stop_estimate"], 1e-30)[1] in ("precision_floor", None)
