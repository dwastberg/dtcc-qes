"""Unified solver configuration, failure precedence and authoritative evidence."""
from copy import deepcopy
from dataclasses import fields, replace
import json

import numpy as np
import pytest
from dtcc_core.model import City

from dtcc_qes import _qes, wind
from dtcc_qes.datasets import QESWindArgs, _SolverPayload


MONITOR = wind.MonitorSpec((0,24,0,24), history_limit=8)


@pytest.mark.parametrize("kwargs,mode", [({}, "legacy"),
    ({"max_solve_seconds":60., "monitor":MONITOR}, "bounded"),
    ({"max_solve_seconds":60., "monitor":MONITOR, "policy":"pedestrian-v1"}, "adaptive")])
def test_modes_derive_from_complete_specs_and_json_roundtrip(kwargs, mode):
    solver = wind.Solver(**kwargs)
    assert solver.mode == mode
    payload = json.loads(json.dumps(solver.to_dict()))
    assert wind.Solver.from_dict(payload) == solver
    if payload["monitor"] is not None:
        payload["monitor"]["region"][0] = -100
        assert solver.monitor.region[0] == 0
    assert not hasattr(wind, "SolverControl")


@pytest.mark.parametrize("kwargs", [dict(monitor=MONITOR), dict(max_solve_seconds=1),
    dict(policy="pedestrian-v1"), dict(policy="unknown"), dict(policy=np.array("pedestrian-v1")),
    dict(checkpoint_interval=1), dict(residual_interval=1), dict(tolerance=1e-12),
    dict(max_iterations=True), dict(raise_on_failure=1), dict(precision="double"),
    pytest.param(dict(tolerance=10**1000), id="overflowing-tolerance"),
    dict(max_solve_seconds=0, monitor=MONITOR),
    dict(max_solve_seconds=1, monitor=MONITOR, policy="pedestrian-v1", checkpoint_interval=1),
    dict(max_solve_seconds=1, monitor=replace(MONITOR,history_limit=4), policy="pedestrian-v1")])
def test_invalid_option_matrix_fails_before_geometry(kwargs, monkeypatch):
    monkeypatch.setattr(wind, "extract_city", lambda *a,**kw:pytest.fail("extracted geometry"))
    with pytest.raises((TypeError, ValueError)):
        wind.run(None, solver=wind.Solver(**kwargs), speed=5, direction=270)


def test_solver_schema_matches_dataset_and_rejects_unknown_or_old_payloads():
    assert set(_SolverPayload.__annotations__) == {f.name for f in fields(wind.Solver)} | {"schema_version"}
    for version in (None, True, 1.0, 2):
        payload = dict(wind.Solver().to_dict(), schema_version=version)
        with pytest.raises(ValueError, match="schema_version"):
            wind.Solver.from_dict(payload)
        with pytest.raises(ValueError):
            QESWindArgs(bounds=[0,0,24,24], solver=payload)
    with pytest.raises(ValueError, match="Invalid solver settings"):
        wind.Solver.from_dict(dict(wind.Solver().to_dict(), mode="bounded"))
    with pytest.raises(ValueError):
        QESWindArgs(bounds=[0,0,24,24], solver=dict(wind.Solver().to_dict(), unknown=True))
    args = QESWindArgs(bounds=[0,0,24,24], solver={"schema_version":1,"max_iterations":2})
    assert args.solver == wind.Solver(max_iterations=2).to_dict()
    default = QESWindArgs(bounds=[0,0,24,24]).wind_options()["solver"]
    assert (default.tolerance, default.max_iterations) == (1e-4,1000)


def test_input_known_exclusions_raise_before_preparation(monkeypatch):
    monkeypatch.setattr(wind, "_prepare_city", lambda *a,**kw:pytest.fail("prepared geometry"))
    solver = wind.Solver(max_solve_seconds=60, monitor=MONITOR, policy="pedestrian-v1",
                         precision="float64", raise_on_failure=True)
    with pytest.raises(wind.UnacceptedResultError) as caught:
        wind.run(None, profile=wind.UniformProfile(5,270), solver=solver, turbulence=wind.Turbulence())
    error = caught.value
    assert error.record is None and error.diagnostics is None
    assert error.exclusions == ("unqualified_inflow_profile", "unqualified_precision", "turbulence_outside_assessment_scope")
    assert "remaining checks run during the solve" in str(error)
    assert not hasattr(error, "control")


def test_nonraising_exclusion_warns_before_preparation_once(monkeypatch, caplog, dtcc_logger):
    prepare = wind._prepare_city
    def observed(*a, **kw):
        assert "unqualified_precision" in caplog.text
        return prepare(*a, **kw)
    monkeypatch.setattr(wind,"_prepare_city",observed)
    solver = wind.Solver(max_solve_seconds=60, monitor=MONITOR, policy="pedestrian-v1",
                         precision="float64", max_iterations=2)
    result = wind.run(City(), bounds=(0,0,0,24,24,24), solver=solver, turbulence=wind.Turbulence(), speed=5, direction=270)
    warnings = [r for r in caplog.records if r.name == "dtcc-qes" and r.levelname == "WARNING"]
    assert len(warnings) == 1 and "screening output" in warnings[0].message
    assert result.solver["record"]["accuracy_status"] == "not_assessed"
    assert result.turbulence is not None


def test_raw_native_record_is_unchanged_and_environment_exists_in_every_mode(monkeypatch):
    runner_type = _qes.WindRunner
    snapshots = []
    class ObservedRunner:
        def __init__(self): self.runner = runner_type()
        def prepare(self,*a,**kw): return self.runner.prepare(*a,**kw)
        def solve(self,*a,**kw):
            result = self.runner.solve(*a,**kw)
            snapshots.append(deepcopy(result.get("control")))
            return result
    monkeypatch.setattr(_qes,"WindRunner",ObservedRunner)
    for solver in (wind.Solver(), wind.Solver(max_solve_seconds=60,monitor=MONITOR)):
        result = wind.run(City(), bounds=(0,0,0,24,24,24), solver=solver, speed=5, direction=270)
        assert result.solver["record"] == snapshots[-1]
        assert set(result.solver) == {"spec","record","environment"}
        assert result.solver["spec"] == solver.to_dict()
        assert result.solver["environment"]["backend"] == _qes.cpu_backend
        assert result.solver["environment"]["precision"] == "float32"
        assert "solver_control" not in result.metadata and not hasattr(result,"control")
        if snapshots[-1] is not None:
            assert "execution" not in snapshots[-1]
        json.dumps(result.metadata, allow_nan=False)


@pytest.mark.parametrize("converged,raises", [(False,True),(True,False)])
def test_completed_work_deadline_mapping_with_manufactured_record(converged, raises, monkeypatch):
    # This tests Python precedence; native deterministic deadline execution is
    # deliberately deferred to the pure-C++ test-clock binding in Phase 9.
    runner_type = _qes.WindRunner
    class DeadlineRecord:
        def __init__(self): self.runner = runner_type()
        def prepare(self,*a,**kw): return self.runner.prepare(*a,**kw)
        def solve(self,*a,**kw):
            value = self.runner.solve(*a,**kw)
            value["diagnostics"]["converged"] = converged
            value["control"].update(termination_reason="time_limit", legacy_converged=converged)
            return value
    monkeypatch.setattr(_qes,"WindRunner",DeadlineRecord)
    solver=wind.Solver(max_solve_seconds=60,monitor=MONITOR,raise_on_failure=True,max_iterations=2)
    if raises:
        with pytest.raises(wind.ConvergenceError) as caught:
            wind.run(City(), bounds=(0,0,0,24,24,24), solver=solver, speed=5, direction=270)
        assert caught.value.record["termination_reason"] == "time_limit"
        assert caught.value.diagnostics.iterations >= 1
        assert not hasattr(caught.value,"control")
    else:
        assert wind.run(City(), bounds=(0,0,0,24,24,24), solver=solver, speed=5, direction=270).diagnostics.converged
