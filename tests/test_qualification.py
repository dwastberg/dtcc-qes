"""Derived execution views retain independent assessment and stop evidence."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from dtcc_core.model import City
from dtcc_qes import wind
from dtcc_qes.solver_control import LEGACY_METHOD


@pytest.fixture
def result():
    return wind.run(City(), speed=5, direction=270, bounds=(0,0,0,24,24,24))


@pytest.mark.parametrize("mode,status,termination,converged,assessment", [
    ("legacy",None,"legacy_tolerance",True,"not_requested"),
    ("legacy",None,"iteration_limit",False,"not_requested"),
    ("bounded","not_assessed","time_limit",True,"not_requested"),
    ("bounded","not_assessed","iteration_limit",False,"not_requested"),
    ("adaptive","not_assessed","legacy_tolerance",True,"not_assessed"),
    ("adaptive","accepted","accepted",False,"accepted"),
    ("adaptive","unaccepted","stagnation",True,"unaccepted"),
    ("adaptive","unaccepted","time_limit",True,"unaccepted"),
])
def test_mapping_keeps_combined_states_and_raw_record(result,mode,status,termination,converged,assessment):
    metadata=deepcopy(result.metadata)
    spec=metadata["solver"]["spec"]
    spec.update(policy="pedestrian-v1" if mode=="adaptive" else None,
                max_solve_seconds=None if mode=="legacy" else 60.)
    record=None if mode=="legacy" else dict(mode=mode,accuracy_status=status,
        termination_reason=termination,method=LEGACY_METHOD,
        assessment_scope="pedestrian_roi_and_required_receptors" if status!="not_assessed" else None,
        assessment_reason="unqualified_inflow_profile" if mode=="adaptive" and status=="not_assessed" else None,
        assessment={"independent_native_evidence":True})
    metadata["solver"]["record"]=record
    solved=replace(result,metadata=metadata,diagnostics=replace(result.diagnostics,converged=converged))
    before=deepcopy(solved.metadata)
    view=solved.qualification["solver"]
    assert view["mode"]==mode and view["assessment"]==assessment
    assert view["execution"]==(termination if termination in ("time_limit","iteration_limit") else "completed")
    assert view["termination_reason"]==termination and view["legacy_converged"]==converged
    assert view["exclusions"]==(["unqualified_inflow_profile"] if assessment=="not_assessed" else [])
    assert view["pending_runtime_checks"]==[]
    assert solved.metadata==before and "qualification" not in solved.metadata
    assert view["method"]==LEGACY_METHOD


def test_views_are_fresh_and_track_current_evidence(result):
    result.metadata["turbulence"]=dict(mixing_length="height",numerics_version="v1",caveats=["screening"])
    view=result.qualification
    view["solver"]["legacy_converged"]=False
    view["profile"]["caveats"].append("edited snapshot")
    view["turbulence"]["wind_basis"]["assessment"]="accepted"
    assert result.qualification["solver"]["legacy_converged"]
    assert result.qualification["profile"]["caveats"]==[]
    assert result.qualification["turbulence"]["wind_basis"]["assessment"]=="not_requested"
    changed=replace(result,diagnostics=replace(result.diagnostics,converged=False))
    assert changed.qualification["turbulence"]["wind_basis"]["execution"]=="iteration_limit"
    assert "wind_basis" not in result.metadata["turbulence"]


def test_native_method_timing_copy_and_export_snapshot(result):
    solver=wind.Solver(max_solve_seconds=60,monitor=wind.MonitorSpec((0,24,0,24)))
    bounded=wind.run(City(),speed=5,direction=270,bounds=(0,0,0,24,24,24),solver=solver)
    assert bounded.solver["record"]["method"]==LEGACY_METHOD
    assert bounded.metadata["timings"]["native"]==bounded.solver["record"]["timings"]
    assert bounded.metadata["timings"]["native"] is not bounded.solver["record"]["timings"]
    for solved in (result,bounded):
        timing=solved.metadata["timings"]
        assert timing["public_call_seconds"]>=timing["city_preparation_seconds"]>=0
        json.dumps(solved.metadata,allow_nan=False)
    assert result.metadata["timings"]["native"] is None
    exported=bounded.to_dtcc()
    field=next(f for f in exported.fields if f.name=="velocity")
    snapshot=json.loads(field.description.split("qualification=",1)[1])
    assert snapshot==bounded.qualification
    bounded.metadata["profile"]["caveats"].append("new caveat")
    assert snapshot!=bounded.qualification
