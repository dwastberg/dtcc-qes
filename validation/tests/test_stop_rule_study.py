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


def test_replay_applies_the_rule_of_the_record_or_a_new_one():
    # Estimates pass from the third check; the old rule (no first_counted_check) stops at the fourth.
    record = dict(iterations=[25, 50, 75, 100, 125, 150], estimate=[None, None, 1e-4, 1e-4, 1e-4, 1e-4],
                  change=[1.0] * 6, floor=[1e-6] * 6, floor_factor=4)
    assert stop_rule.replay(record, 1e-3) == (100, "velocity_estimate")
    assert stop_rule.replay(dict(record, first_counted_check=4, floor_factor=6), 1e-3) == (125, "velocity_estimate")
    assert stop_rule.replay(record, 1e-3, first_counted_check=4) == (125, "velocity_estimate")
    # The floor scales with the factor: a change of 1.25x the recorded (factor 4) floor passes at factor 6.
    floor = dict(record, estimate=[None] * 6, change=[1.25e-6] * 6)
    assert stop_rule.replay(floor, 1e-3) == (None, None)
    assert stop_rule.replay(floor, 1e-3, floor_factor=6, first_counted_check=4) == (125, "precision_floor")


def test_candidate_campaign_uses_grid_relaxation():
    specs = campaigns.campaign("stop_rule_candidate")
    assert len(specs) == 14 and all(s.relaxation == "grid" and s.stop == "velocity" for s in specs)
    assert all(s.max_iterations == 20000 and s.velocity_tolerance == 1e-3 for s in specs)
    assert specs[0].name.endswith("wgrid-velocity1e-03")
    assert RunSpec.from_dict(json.loads(json.dumps(specs[0].to_dict()))) == specs[0]
    assert runner.inputs(campaigns.case_d(0.0, resolution=8.0, relaxation="grid"))["run"]["solver"].relaxation == "grid"


def test_default_runspec_keeps_the_multiplier_rule():
    from dtcc_qes import wind
    spec = campaigns.fixed_work(campaigns.case_d(0.0, resolution=2.0))
    solver = runner.inputs(spec)["run"]["solver"]
    assert (solver.stop, solver.relaxation, solver.max_iterations) == ("multiplier_change", None, 2000)
    # The candidate settings are exactly the stage 2 defaults of wind.Solver().
    default = wind.Solver()
    assert {name: getattr(default, name) for name in stop_rule.CANDIDATE} == stop_rule.CANDIDATE


def test_g6_campaign_pairs_each_baseline_run_with_the_default():
    specs = campaigns.campaign("stop_rule_g6")
    fixed = [s for s in specs if s.stop == "multiplier_change"]
    default = [s for s in specs if s.stop == "velocity"]
    assert len(fixed) == len(default) == 35 + 2 and {s.case for s in fixed} == {"A", "B", "D", "E"}
    assert all(s.resolution == 2.0 for s in specs) and len({s.key for s in specs}) == len(specs)
    assert [replace(s, **{k: getattr(f, k) for k in stop_rule.CANDIDATE}) for s, f in zip(default, fixed)] == fixed
