"""Prevent false closure and unsafe reuse in the joint spatial study."""

from fixtures.support import load_tool
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from fixtures.auto_grid_controls import native_run
from fixtures.precision_verification import precision_document

_tools = Path(__file__).parents[1]/"tools"
study = load_tool("joint_grid_verification", _tools/"run_joint_grid_verification.py")
precompute = load_tool("joint_precompute", _tools/"precompute_joint_checkpoints.py")
audit = load_tool("joint_audit", _tools/"audit_joint_grid_verification.py")


from fixtures.joint_grid_verification import joint_documents, manufactured

def test_matrix_preserves_both_extents_and_fixed_vertical_operands_above_soft_target():
    configs = {f: dict(layers_input=[.5]*128) for f in study.FAMILIES}
    assert len(study.tasks()) == 8
    for task in study.tasks():
        tokens = list(map(float, study.input_text(task, configs).split()))
        assert tokens[:9] == [.5, (80-task["extent"])/2, (80-task["extent"])/2,
                              task["extent"], task["extent"], 128, 2, 4, 0]
        assert tokens[9:137] == [.5]*128
        estimate = study.resource_estimate(task, configs)
        assert estimate["physical_cells"] == (task["extent"]/.5)**2*128
        assert estimate["solver_workspace_bytes"] == (task["extent"]/.5)**2*129*16+64*129*8
    assert estimate["physical_cells"] == 29491200 > 20000000


def test_single_tight_reference_cannot_substitute_for_whole_predeclared_subset():
    doc = precision_document()
    for run in doc["runs"]:
        run["disabled_mask"] = 0
    study.require_reference_matrix(doc, "precision", "manufactured")
    run = doc["runs"][0]
    run["checkpoints"][0]["max_divergence"] = 1e-4
    assert study.gate(run)["accepted"]
    assert not study.gate(run)["ten_times_tighter_accepted"]
    with pytest.raises(ValueError, match="Every predeclared tighter"):
        study.require_reference_matrix(doc, "precision", "manufactured")


def test_full_joint_scope_needs_complete_matrix_and_both_spatial_axes():
    doc, refs = joint_documents()
    result = study.summarize(doc, refs)
    assert result["complete"] and result["joint_scope_established"]
    assert len(result["comparisons"]) == 64
    doc["runs"].pop()
    assert not study.summarize(doc, refs)["joint_scope_established"]


def test_near_wall_failure_is_retained_despite_aggregate_and_old_critical_pass():
    doc, refs = joint_documents()
    target, = [r for r in doc["runs"] if r["task"]["id"] == "joint/240/auto/270/0.5"]
    point_index = list(study.POINTS).index(27)+len(study.POINTS)*list(study.POINTS).index(21)
    for checkpoint in target["checkpoints"]:
        checkpoint["planes"][0]["velocity"][point_index] = [4, 0, 0]
    result = study.summarize(doc, refs)
    row, = [r for r in result["comparisons"] if r["comparison"] == "xy_1_to_0.5_at_240"
             and r["family"] == "auto" and r["direction"] == 270 and r["height"] == 1.5 and r["region"] == "all"]
    assert row["matched_accuracy"] and row["within_budget"]
    assert not row["local_checks_within_budget"] and not result["joint_scope_established"]


def test_failed_solve_withholds_spatial_comparison():
    doc, refs = joint_documents()
    doc["runs"][0]["checkpoints"][0]["max_divergence"] = 1
    result = study.summarize(doc, refs)
    assert not result["joint_scope_established"]
    assert any(not r["matched_accuracy"] and "p95_abs_delta_K" not in r for r in result["comparisons"])


def test_corrupted_checkpoint_is_rejected_before_native_execution(tmp_path):
    task = study.tasks()[0]
    path = study.checkpoint_path(tmp_path, task, 2000)
    study.atomic_json(path, dict(request={}, run={}, run_sha256="wrong"))
    with pytest.raises(ValueError, match="identity/content"):
        study.obtain_checkpoint(task, {"auto": dict(layers_input=[.5]*128)}, Path("/missing"),
                                "manufactured", 2000, 40000000, tmp_path, "frozen")


def test_supplemental_publication_is_complete_and_never_overwrites(tmp_path):
    source, target = tmp_path/"complete.json.gz", tmp_path/"primary/checkpoint.json.gz"
    study.atomic_json(source, dict(run="independent zero start"))
    assert precompute.publish(source, target)
    assert study.read(source) == study.read(target)
    replacement = tmp_path/"different.json.gz"
    study.atomic_json(replacement, dict(run="other execution"))
    assert not precompute.publish(replacement, target)
    assert study.read(target) == dict(run="independent zero start")


def test_audit_counts_reused_execution_once_and_duplicate_work_separately(tmp_path, monkeypatch):
    task = study.tasks()[0]
    _, refs = joint_documents()
    configs = {f: dict(layers_input=[.5]*128, expected_faces=np.arange(0, 64.5, .5).tolist())
               for f in study.FAMILIES}
    frozen = joint_documents()[0]["metadata"]["frozen_critical_indices"]
    executable = tmp_path/"worker"
    executable.write_bytes(b"unit-test worker identity")
    metadata = dict(backend=study.BACKENDS["serial"], executable=str(executable),
        executable_sha256=study.digest(executable), source_sha256={}, references_sha256={},
        frozen_critical_indices=frozen, workers=2)
    study.atomic_json(tmp_path/"manifest.json", dict(metadata=metadata, configurations=configs))
    identity = study.fingerprint(metadata)
    resource = study.resource_estimate(task, configs)
    documents, origins = [], []
    for sweeps in (1000, 2000, 4000):
        run = manufactured(task)
        run.update(backend=metadata["backend"], direction=task["direction"], resolution=.5,
            cells=resource["physical_cells"], solver_workspace_bytes=resource["solver_workspace_bytes"],
            z_faces=configs["auto"]["expected_faces"], horizontal_bounds=[-40, -40, 120, 120])
        run["checkpoints"] = [run["checkpoints"][0] | dict(iterations=sweeps, residual_seconds=.01)]
        path = study.checkpoint_path(tmp_path, task, sweeps)
        request = dict(study_identity=identity, task=task, sweeps=sweeps,
            input_sha256=study.hashlib.sha256(study.input_text(task, configs).encode()).hexdigest())
        study.atomic_json(path, dict(request=request, run=run, run_sha256=study.fingerprint(run)))
        documents.append(run)
        origins.append(dict(path=str(path), sha256=study.digest(path)))
    assembled = study.assemble(task, documents, origins)
    study.atomic_json(tmp_path/"cases"/(task["id"]+".json.gz"),
        dict(study_identity=identity, run=assembled, attempts=[], accepted=True))
    study.write_summary(tmp_path, metadata, refs)
    plan = dict(primary_manifest_sha256=study.digest(tmp_path/"manifest.json"), study_identity=identity,
        source=__file__, source_sha256=study.digest(__file__), backend=metadata["backend"], workers=1,
        maximum_combined_workers=3, sweeps=4000, tasks=[task],
        estimated_additional_process_bytes=resource["estimated_process_bytes"])
    study.atomic_json(tmp_path/"supplemental.json", dict(plan=plan))
    extra = study.checkpoint_path(tmp_path/"supplemental", task, 4000)
    extra.parent.mkdir(parents=True)
    assert precompute.publish(Path(origins[-1]["path"]), extra)
    monkeypatch.setattr(audit, "load_references", lambda backend: (refs, configs, frozen, {}))
    _, _, result = audit.audit_backend(tmp_path, "serial")
    assert result["unique_checkpoints"] == 3 and result["supplemental_reused_in_primary"] == 1
    assert result["executed_solve_seconds"] == 3
    assert result["executed_fixed_sweeps"] == 7000
    assert result["executed_physical_cell_sweeps"] == resource["physical_cells"]*7000
    # A genuinely separate invocation has its own timing/content fingerprint.
    # Atomic replacement leaves the primary hard-linked checkpoint unchanged.
    saved = study.read(extra)
    saved["run"]["checkpoints"][0]["solve_seconds"] = 2
    saved["run_sha256"] = study.fingerprint(saved["run"])
    study.atomic_json(extra, saved)
    _, _, result = audit.audit_backend(tmp_path, "serial")
    assert result["unique_checkpoints"] == 4 and result["supplemental_reused_in_primary"] == 0
    assert result["executed_solve_seconds"] == 5
    assert result["executed_fixed_sweeps"] == 11000
    assert result["executed_physical_cell_sweeps"] == resource["physical_cells"]*11000


def test_local_low_speed_rule_and_solid_corner_cannot_pass():
    task = study.tasks()[0]
    a, b = manufactured(task), manufactured(task)
    index = list(study.POINTS).index(27)+len(study.POINTS)*list(study.POINTS).index(21)
    a["checkpoints"][-1]["planes"][0]["velocity"][index] = [.2, 0, 0]
    b["checkpoints"][-1]["planes"][0]["velocity"][index] = [0, 0, 0]
    row = study.local_checks(a, b, 1.5)[0]
    assert row["within_budget"] and row["relative_difference"] is None
    a["checkpoints"][-1]["planes"][0]["velocity"][index] = [.3, 0, 0]
    assert not study.local_checks(a, b, 1.5)[0]["within_budget"]
    a["checkpoints"][-1]["planes"][0]["velocity"][index] = None
    assert not study.local_checks(a, b, 1.5)[0]["within_budget"]


def test_budget_escalation_reuses_independent_checkpoints_and_saves_rejection(tmp_path, monkeypatch):
    task = study.tasks()[0]
    calls = []
    cache = {}

    def checkpoint(task, configs, executable, backend, sweeps, ceiling, output, identity):
        if sweeps not in cache:
            calls.append(sweeps)
            run = manufactured(task)
            run["checkpoints"] = [run["checkpoints"][0] | dict(iterations=sweeps,
                max_divergence=1 if sweeps == 1000 else 1e-6)]
            cache[sweeps] = run
        return cache[sweeps], dict(path=str(sweeps), sha256="fake")

    monkeypatch.setattr(study, "obtain_checkpoint", checkpoint)
    result = study.execute(task, {}, Path("/unused"), "manufactured", 1000, 2000,
                           40000000, tmp_path, "identity")
    assert calls == [1000, 2000, 4000, 8000]
    assert result["accepted"] and len(result["attempts"]) == 1
    saved = study.read(tmp_path/"cases"/(task["id"]+".json.gz"))
    assert saved == result
    assert [c["iterations"] for c in saved["run"]["checkpoints"]] == [2000, 4000, 8000]


def test_native_checkpoint_matches_triple_and_configurable_allocation_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("DTCC_QES_STUDY_ORDER", "legacy")
    executable = Path(os.environ.get("DTCC_QES_STUDY_EXECUTABLE", "build/extension/vertical_grid_study"))
    if not executable.exists():
        pytest.skip("Native study executable not built")
    configs = {f: dict(layers_input=[.5]*128, expected_faces=np.arange(0, 64.5, .5).tolist())
               for f in study.FAMILIES}
    task = study.previous_tasks("precision")[0]  # coarse 80 m pilot, never a new reference
    text = study.input_text(task, configs)
    command = [str(executable), "tower", "--horizontal", "270", "2", "--float64"]
    triple = json.loads(subprocess.run(command, input=text, text=True, capture_output=True, check=True).stdout)
    for checkpoint in triple["checkpoints"]:
        one_command = command[:4]+[str(checkpoint["iterations"])]+command[5:]
        single = json.loads(subprocess.run(one_command+["--checkpoint", "--max-cells", "40000000"],
            input=text, text=True, capture_output=True, check=True).stdout)
        assert len(single["checkpoints"]) == 1
        for key in ("max_divergence", "rms_divergence", "max_multiplier_change", "planes"):
            assert checkpoint[key] == single["checkpoints"][0][key]
        assert single["initial_planes"] == triple["initial_planes"]
    rejected = subprocess.run(command+["--max-cells", "1"], input=text, text=True, capture_output=True)
    assert rejected.returncode and "cell limit" in rejected.stderr
    for count in ("0", "-1", "4junk"):
        rejected = subprocess.run(command+["--max-cells", count], input=text, text=True, capture_output=True)
        assert rejected.returncode and "positive integer" in rejected.stderr
    actual, origin = study.obtain_checkpoint(task, configs, executable, single["backend"], 2,
                                             40000000, tmp_path, "frozen")
    def forbidden(*args, **kwargs):
        raise AssertionError("Cached zero-start checkpoint should not run again")
    monkeypatch.setattr(study.subprocess, "run", forbidden)
    cached, cached_origin = study.obtain_checkpoint(task, configs, executable, single["backend"], 2,
                                                   40000000, tmp_path, "frozen")
    assert actual == cached and origin == cached_origin
    with pytest.raises(ValueError, match="identity/content"):
        study.obtain_checkpoint(task, configs, executable, single["backend"], 2,
                                40000000, tmp_path, "changed-source")
