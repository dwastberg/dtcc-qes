"""Guard the numerical archive gate against hiding real changes."""

from fixtures.support import load_tool
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


baseline = load_tool("feature_merge_baseline", Path(__file__).parents[1]/"tools/feature_merge_baseline.py")


def archives(tmp_path):
    roots = [tmp_path/"a", tmp_path/"b"]
    for root in roots:
        root.mkdir()
        baseline.write(root/"manifest.json", dict(lock_sha256="lock", backend="serial",
            omp_num_threads="2", compiler=["clang"], policy_revision="native", extension_sha256="extension",
            cases={"case": {"diagnostics": {"iterations": 30}}}))
        np.savez(root/"case.npz", velocity=np.array([np.nan, 1.], dtype="float32"), valid=np.array([False, True]))
    return roots


def test_exact_archive_comparison_detects_mask_and_byte_changes(tmp_path):
    a,b = archives(tmp_path)
    assert baseline.compare(a,b)
    np.savez(b/"case.npz", velocity=np.array([np.nan, 1.], dtype="float32"), valid=np.array([True, True]))
    assert not baseline.compare(a,b)
    np.savez(b/"case.npz", velocity=np.array([np.nan, 1.], dtype="float64"), valid=np.array([False, True]))
    assert not baseline.compare(a,b)


def test_identity_exception_does_not_allow_dependency_changes(tmp_path):
    a,b = archives(tmp_path)
    data=json.loads((b/"manifest.json").read_text())
    data.update(policy_revision="candidate", extension_sha256="candidate-binary")
    baseline.write(b/"manifest.json",data)
    assert not baseline.compare(a,b)
    assert baseline.compare(a,b,("native","candidate"))
    assert not baseline.compare(a,b,("other","candidate"))
    data["lock_sha256"]="changed"
    baseline.write(b/"manifest.json",data)
    assert not baseline.compare(a,b,("native","candidate"))


def test_timing_filter_keeps_budget_and_numerical_evidence():
    value={"max_solve_seconds":60., "timings":{"solve_seconds":.1},
           "history":[{"elapsed_seconds":.02,"iteration":25,"error":1e-4}]}
    timings={}
    assert baseline.deterministic(value,timings)=={
        "max_solve_seconds":60.,"timings":{},"history":[{"iteration":25,"error":1e-4}]}
    assert len(timings)==2
    with pytest.raises(ValueError,match="Invalid timing"):
        baseline.deterministic({"timings":{"solve_seconds":float("nan")}}, {})


@pytest.mark.parametrize("value",[True,-1,float("inf"),"0"])
def test_timing_filter_rejects_invalid_durations(value):
    with pytest.raises(ValueError,match="Invalid timing"):
        baseline.deterministic({"timings":{"public_call_seconds":value}}, {})
    timings={}
    assert baseline.deterministic({"timings":{"public_call_seconds":None}},timings)=={"timings":{}}
    assert timings=={"/timings/public_call_seconds":None}


def test_phase3_migration_keeps_existing_diagnostics_strict():
    from copy import deepcopy
    from dtcc_core.model import City
    from dtcc_qes import wind
    result=wind.run(City(),speed=5,direction=270,bounds=(0,0,0,24,24,24),
                    vertical_grid=wind.VerticalGrid.auto())
    current={"case":dict(metadata=baseline.deterministic(result.metadata,{}))}
    old=deepcopy(current)
    metadata=old["case"]["metadata"]
    metadata.pop("timings")
    metadata["domain"].pop("top_requirements")
    sampling=metadata["domain"]["vertical_grid"]["pedestrian_sampling"]
    old_keys={"height","centre_indices","bracketing_centres","upper_weight","third_centre",
              "reference_height","roughness_length","flat_profile_exact_K",
              "flat_profile_interpolated_K","flat_profile_bias_K"}
    for key in set(sampling)-old_keys:
        sampling.pop(key)
    assert baseline.comparison_cases(old)==baseline.comparison_cases(current)
    for edit in ("constraint","profile_diagnostic","timing_scope"):
        changed=deepcopy(current)
        metadata=changed["case"]["metadata"]
        if edit=="constraint":
            metadata["domain"]["top_requirements"]["minimum_cells"]["count"]=3
        elif edit=="profile_diagnostic":
            metadata["domain"]["vertical_grid"]["pedestrian_sampling"]["vector_interpolation_error_mps"]=99
        else:
            metadata["timings"]["scopes"]["native"]="changed scope"
        assert baseline.comparison_cases(old)!=baseline.comparison_cases(changed)


def test_profile_schema_migration_preserves_physical_parameters():
    old={"case":{"metadata":{"condition":{"roughness_length":.7},"profile":{
        "schema_version":1,"type":"uniform","requested":{"schema_version":1,"kind":"uniform","speed":5}}}}}
    migrated=baseline.comparison_cases(old)
    assert migrated["case"]["metadata"]["profile"]["requested"]["roughness_length"]==.7
    assert old["case"]["metadata"]["profile"]["schema_version"]==1
    changed=json.loads(json.dumps(migrated))
    changed["case"]["metadata"]["profile"]["requested"]["roughness_length"] = .1
    assert baseline.comparison_cases(changed) != migrated


def test_solver_metadata_migration_keeps_native_evidence_and_environment():
    environment = dict(sweep_order="red_black", precision="float32", backend="serial CPU")
    old = {"case":{"metadata":{"solver":dict(tolerance=1e-5, max_iterations=30,
        precision="float32", raise_on_nonconvergence=False), "solver_control":dict(
            execution=environment, mode="bounded", accuracy_status="not_assessed", accepted=False,
            requested=dict(max_solve_seconds=60.,checkpoint_interval=25,residual_interval=0,policy=None),
            monitor=dict(origin=[0,0,0],crs="",reference_speed=5.,region=[0,24,0,24],
                heights=[1.5,1.75],short_window=1,long_window=2,global_mass=False))}}}
    migrated = baseline.comparison_cases(old)
    solver = migrated["case"]["metadata"]["solver"]
    assert solver["environment"] == environment
    assert "execution" not in solver["record"]
    assert "execution" in old["case"]["metadata"]["solver_control"]
    assert solver["spec"]["max_solve_seconds"] == 60.
    changed = json.loads(json.dumps(migrated))
    changed["case"]["metadata"]["solver"]["record"]["accepted"] = True
    assert baseline.comparison_cases(changed) != migrated


def test_phase1_names_preserve_caveats_and_nondefault_inflow_parameters():
    old={"case":{"request":dict(wind_speed=3.,wind_direction=225.,reference_height=15.,roughness_length=.5),
        "metadata":{"profile":dict(schema_version=2,type="measured",turbulence_caveat="model limitation"),
                    "turbulence":dict(profile_caveat="model limitation")}}}
    migrated=baseline.comparison_cases(old)
    metadata=migrated["case"]["metadata"]
    assert metadata["profile"]["kind"] == "measured"
    assert metadata["profile"]["caveats"] == metadata["turbulence"]["caveats"] == ["model limitation"]
    assert migrated["case"]["request"]["profile"]["reference_height"] == 15.
    assert migrated["case"]["request"]["profile"]["roughness_length"] == .5
    assert "type" in old["case"]["metadata"]["profile"]
    changed=json.loads(json.dumps(migrated))
    changed["case"]["metadata"]["profile"]["caveats"] = []
    assert baseline.comparison_cases(changed) != migrated


def test_phase2_removes_only_condition_facts_verified_against_the_profile():
    profile=dict(schema_version=2,kind="log",requested=dict(direction=270.,roughness_length=.1),
                 reference=dict(speed=5.,direction=270.,height=10.))
    condition=dict(speed=5.,direction=270.,reference_height=10.,roughness_length=.1)
    old={"case":{"metadata":dict(profile=profile,domain={},model=dict(boundary_layer="neutral logarithmic"),
            condition=condition,effective_condition={k:float(np.float32(v)) for k,v in condition.items()})}}
    migrated=baseline.comparison_cases(old)["case"]["metadata"]
    assert "condition" not in migrated and "effective_condition" not in migrated
    assert migrated["profile"] == migrated["domain"]["profile"]
    assert migrated["profile"]["boundary_layer"] == "neutral logarithmic"
    assert "condition" in old["case"]["metadata"]
    for key in ("condition","effective_condition"):
        bad=json.loads(json.dumps(old))
        bad["case"]["metadata"][key]["speed"]=999
        with pytest.raises(ValueError,match="disagrees with the profile"):
            baseline.comparison_cases(bad)
