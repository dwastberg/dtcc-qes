"""Native input/grid eligibility is shared with runtime float32 narrowing."""
from dataclasses import replace
import json

import pytest
from dtcc_core.model import City
from dtcc_qes import _qes,wind
from fixtures.geometry import tower_city
from fixtures.specs import pedestrian_solver

pytestmark=pytest.mark.usefixtures("dtcc_logger")
BOUNDS=(0,0,0,160,160,64)


def test_preview_schema_unknown_inflow_and_nonadaptive_modes():
    city=City();bounds=(0,0,0,24,24,32)
    assert wind.preview_grid(city,bounds=bounds).eligibility is None
    for solver in (wind.Solver(),wind.Solver(max_solve_seconds=1,monitor=wind.MonitorSpec((0,24,0,24)))):
        preview=wind.preview_grid(city,bounds=bounds,solver=solver)
        assert preview.eligibility==dict(mode=solver.mode,policy=None,exclusions=[],pending_runtime_checks=[])
        assert preview.domain["inflow"]=="unknown"
    with pytest.raises(ValueError,match="explicit profile.*grid-only"):
        wind.preview_grid(city,bounds=bounds,solver=pedestrian_solver())


def test_eligibility_does_not_construct_runner_or_invent_execution(monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("allocated native fields"))
    preview=wind.preview_grid(tower_city(),speed=5,direction=270,bounds=BOUNDS,solver=pedestrian_solver())
    expected=[] if _qes.solver_policy_build_supported else ["unqualified_build"]
    assert preview.eligibility["exclusions"]==expected
    assert preview.eligibility["pending_runtime_checks"]==["actual_thread_team"]
    assert set(preview.eligibility)=={"mode","policy","exclusions","pending_runtime_checks"}
    json.dumps(preview.eligibility,allow_nan=False)


def test_preflight_uses_native_narrowed_grid_and_inflow():
    profile=wind.LogProfile(5.000000001,270,reference_height=10.000000001,roughness_length=.100000000001)
    preview=wind.preview_grid(tower_city(),profile,bounds=BOUNDS,resolution=2.000000000001,
                               solver=pedestrian_solver())
    assert preview.eligibility["exclusions"]==([] if _qes.solver_policy_build_supported else ["unqualified_build"])


def test_full_exclusions_are_finalized_and_copied_from_native_record():
    solver=pedestrian_solver(precision="float64",max_iterations=3)
    result=wind.run(City(),wind.UniformProfile(5,270),bounds=(0,0,0,80,80,32),
                    solver=solver,turbulence=wind.Turbulence())
    expected=(["unqualified_build"] if not _qes.solver_policy_build_supported else [])+[
        "unqualified_inflow_profile","unqualified_precision","turbulence_outside_assessment_scope",
        "unqualified_grid","unqualified_geometry"]
    # Required heights remain valid monitor inputs on the excluded small grid.
    assert result.solver["record"]["exclusions"]==expected
    assert result.qualification["solver"]["exclusions"]==expected
    assert result.qualification["solver"]["pending_runtime_checks"]==[]
    assert result.solver["record"]["assessment_reason"]==expected[0]
    assert result.qualification["solver"]["mode"]=="adaptive"


def test_known_grid_exclusion_raises_before_native_runner(monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("allocated native fields"))
    solver=pedestrian_solver(raise_on_failure=True)
    with pytest.raises(wind.UnacceptedResultError) as error:
        wind.run(tower_city(),speed=5,direction=270,bounds=(0,0,0,160,160,66),solver=solver)
    assert error.value.diagnostics is None and error.value.record is None
    assert "unqualified_grid" in error.value.exclusions or not _qes.solver_policy_build_supported


@pytest.mark.parametrize("precision,turbulence",[("float32",None),("float64",None),("float32",wind.Turbulence())])
def test_preview_first_reason_matches_runtime_with_actual_team(precision,turbulence):
    solver=pedestrian_solver(precision=precision,max_iterations=3)
    options=dict(bounds=BOUNDS,solver=solver,turbulence=turbulence)
    preview=wind.preview_grid(tower_city(),speed=5,direction=270,**options)
    result=wind.run(tower_city(),speed=5,direction=270,**options)
    assert result.solver["record"]["exclusions"]==preview.eligibility["exclusions"]
    assert result.solver["record"]["actual_threads"] in (1,2,4)


def test_actual_eight_thread_team_is_finalized_in_fresh_process(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import json
from dtcc_qes import wind, _qes
from fixtures.geometry import tower_city
from fixtures.specs import pedestrian_solver
options=dict(bounds=(0,0,0,160,160,64),solver=pedestrian_solver(max_iterations=1))
preview=wind.preview_grid(tower_city(),speed=5,direction=270,**options)
result=wind.run(tower_city(),speed=5,direction=270,**options)
record=result.solver["record"]
assert "unqualified_thread_team" not in preview.eligibility["exclusions"]
assert preview.eligibility["pending_runtime_checks"]==["actual_thread_team"]
assert record["actual_threads"] == (8 if _qes.openmp_enabled else 1)
assert ("unqualified_thread_team" in record["exclusions"]) == _qes.openmp_enabled
assert result.qualification["solver"]["pending_runtime_checks"]==[]
'''
    env=os.environ|dict(OMP_NUM_THREADS="8",OMP_DYNAMIC="FALSE")
    env["PYTHONPATH"]=os.pathsep.join(filter(None,[env.get("PYTHONPATH"),str(__import__('pathlib').Path(__file__).parent)]))
    completed=subprocess.run([sys.executable,"-c",script],env=env,capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stdout+completed.stderr


def test_legacy_native_timing_scopes_are_measured_without_a_control_record():
    result=wind.run(City(),speed=5,direction=270,bounds=(0,0,0,24,24,32))
    timings=result.metadata["timings"]
    native=timings["native"]
    assert result.solver["record"] is None
    assert all(type(v) is float and v>=0 for v in native.values())
    assert timings["public_call_seconds"]>=timings["city_preparation_seconds"]>=0
    assert timings["public_call_seconds"]>=native["native_total_seconds"]>=native["solve_seconds"]
    assert native["solve_seconds"]>=sum(native[k] for k in (
        "mutex_wait_seconds","initialization_seconds","workspace_seconds","rhs_seconds",
        "sweeps_seconds","monitoring_seconds","finalization_seconds"))
    assert native["monitoring_seconds"]==native["deadline_overshoot_seconds"]==0
