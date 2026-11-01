"""Real whole-sweep deadline execution using a pure-C++ clock sequence."""
from dataclasses import replace
import inspect

import numpy as np
import pytest
from dtcc_core.model import City
from dtcc_qes import _qes,wind
from fixtures.cases import ONE_BUILDING
from fixtures.cities import city_case
from fixtures.condition_state import configuration

pytestmark=pytest.mark.usefixtures("dtcc_logger")


def inject_clock(monkeypatch,steps):
    native_runner=_qes.WindRunner
    class ClockRunner:
        def __init__(self):self.native=native_runner()
        def prepare(self,*args,**kwargs):self.native.prepare(*args,**kwargs)
        def solve(self,*args,**kwargs):
            return self.native.solve(*args,**kwargs,_test_clock_steps=steps)
    monkeypatch.setattr(_qes,"WindRunner",ClockRunner)


def solver(**changes):
    return wind.Solver(**(dict(max_iterations=8,tolerance=float(np.finfo(np.float32).eps),
        max_solve_seconds=1,monitor=wind.MonitorSpec((0,80,0,60)))|changes))


@pytest.mark.parametrize("turbulence",[None,wind.Turbulence()])
def test_zero_whole_sweeps_always_raise_without_a_field(monkeypatch,turbulence):
    city,condition,grid,_=city_case(ONE_BUILDING)
    inject_clock(monkeypatch,[0.,100.])
    with pytest.raises(wind.BudgetExhaustedError) as error:
        wind.run(city,**condition,**grid,solver=solver(),turbulence=turbulence)
    assert error.value.record["iterations"]==0
    assert error.value.record["termination_reason"]=="time_limit"
    assert "_test_clock_steps" not in inspect.signature(wind.run).parameters


@pytest.mark.parametrize("completed,zeros",[(1,23),(2,27),(3,31)])
@pytest.mark.parametrize("turbulence",[None,wind.Turbulence()])
def test_mid_solve_deadline_returns_exact_completed_sweeps(completed,zeros,turbulence,monkeypatch,caplog):
    city,condition,grid,_=city_case(ONE_BUILDING)
    options=solver()
    reference=wind.run(city,**condition,**grid,solver=wind.Solver(tolerance=options.tolerance,
        max_iterations=completed),turbulence=turbulence)
    caplog.clear()
    # 20 clock reads precede the first sweep, then four per whole sweep.
    # The deadline is the after-sweep read, never a Python callback.
    inject_clock(monkeypatch,[0.]*zeros+[100.])
    actual=wind.run(city,**condition,**grid,solver=options,turbulence=turbulence)
    assert actual.diagnostics.iterations==completed
    assert actual.qualification["solver"]["execution"]=="time_limit"
    np.testing.assert_array_equal(actual.velocity,reference.velocity)
    assert actual.diagnostics==reference.diagnostics
    if turbulence is not None:
        for name in ("stress","tke","co_eps","mixing_length","computed","capped","stress_valid"):
            np.testing.assert_array_equal(getattr(actual.turbulence,name),getattr(reference.turbulence,name))
        assert actual.qualification["turbulence"]["wind_basis"]["execution"]=="time_limit"
    warnings=[r.message for r in caplog.records if r.name=="dtcc-qes" and r.levelname=="WARNING"]
    assert len(warnings)==1
    if turbulence is not None:
        assert "screening output" in warnings[0]


@pytest.mark.parametrize("converged",[False,True])
@pytest.mark.parametrize("raise_on_failure",[False,True])
@pytest.mark.parametrize("turbulence",[None,wind.Turbulence()])
def test_convergence_at_deadline_and_failure_precedence(converged,raise_on_failure,turbulence,monkeypatch):
    city,condition,grid,_=city_case(ONE_BUILDING)
    if converged:
        city=City()
    inject_clock(monkeypatch,[0.]*23+[100.])
    options=solver(raise_on_failure=raise_on_failure)
    if raise_on_failure and not converged:
        with pytest.raises(wind.ConvergenceError) as error:
            wind.run(city,**condition,**grid,solver=options,turbulence=turbulence)
        assert error.value.diagnostics.iterations==1
        assert error.value.record["termination_reason"]=="time_limit"
    else:
        result=wind.run(city,**condition,**grid,solver=options,turbulence=turbulence)
        assert result.diagnostics.iterations==1 and result.diagnostics.converged==converged
        assert result.qualification["solver"]["execution"]=="time_limit"
        assert result.qualification["solver"]["legacy_converged"]==converged


@pytest.mark.parametrize("steps",[[],[1.,0.],[0.,float("nan")],[0.,float("inf")]])
def test_private_clock_rejects_invalid_sequences(steps):
    grid,model,arrays=configuration()
    runner=_qes.WindRunner();runner.prepare(grid,model,**arrays)
    with pytest.raises(ValueError,match="finite and monotonic"):
        runner.solve(_qes.WindCondition(),control=solver()._native((0,0,0),None),_test_clock_steps=steps)
