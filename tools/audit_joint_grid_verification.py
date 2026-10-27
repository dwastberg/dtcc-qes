"""Recompute joint-grid decisions and audit every zero-start checkpoint."""
from pathlib import Path
import hashlib
import json

import numpy as np

from run_joint_grid_verification import (BACKENDS, HEIGHTS, assemble, atomic_json,
    collect, digest, fingerprint, gate, load_references, read, summarize, tasks,
    validate_checkpoint, input_text, resource_estimate)
from run_horizontal_sensitivity import array, values


def audit_backend(path, backend):
    manifest = read(path/"manifest.json")
    metadata = manifest["metadata"]
    identity = fingerprint(metadata)
    if metadata["backend"] != BACKENDS[backend]:
        raise ValueError("Manifest backend mismatch")
    for source, expected in metadata["source_sha256"].items():
        if digest(source) != expected:
            raise ValueError(f"Changed study source: {source}")
    if digest(metadata["executable"]) != metadata["executable_sha256"]:
        raise ValueError("Changed worker executable")
    for source, expected in metadata["references_sha256"].items():
        if digest(source) != expected:
            raise ValueError(f"Changed reference archive: {source}")
    references, configs, frozen, _ = load_references(backend)
    if configs != manifest["configurations"] or frozen != metadata["frozen_critical_indices"]:
        raise ValueError("Changed frozen grid configuration")
    doc = collect(path, metadata)
    if doc != read(path/"raw.json.gz"):
        raise ValueError("Raw archive differs from atomic case records")
    summary = summarize(doc, references)
    if summary != read(path/"summary.json"):
        raise ValueError("Comparison decisions do not recompute exactly")
    checkpoint_costs = []
    cached = {}
    initial_states = {}
    for task in tasks():
        initial_state = None
        for checkpoint_path in sorted((path/"checkpoints"/task["id"]).glob("*.json.gz")):
            checkpoint = read(checkpoint_path)
            request, run = checkpoint["request"], checkpoint["run"]
            if (request["study_identity"] != identity or request["task"] != task
                    or checkpoint_path.name != f"{request['sweeps']:06d}.json.gz"
                    or request["input_sha256"] != hashlib.sha256(input_text(task, configs).encode()).hexdigest()
                    or checkpoint["run_sha256"] != fingerprint(run)):
                raise ValueError("Checkpoint request/content mismatch")
            validate_checkpoint(run, task, configs, BACKENDS[backend], request["sweeps"])
            state = {key: run[key] for key in ("initial_planes", "profile_planes", "sample_x", "sample_y",
                                               "z_faces", "roof_errors", "horizontal_bounds")}
            if initial_state is not None and state != initial_state:
                raise ValueError("Initial fields or support changed across zero-start checkpoints")
            initial_state = state
            initial_states[task["id"]] = state
            cached[str(checkpoint_path)] = run
            c = run["checkpoints"][0]
            checkpoint_costs.append(dict(task=task["id"], sweeps=request["sweeps"],
                physical_cells=run["cells"],
                solve_seconds=c["solve_seconds"], prep_seconds=run["prep_seconds"],
                residual_seconds=c["residual_seconds"], sampling_seconds=c["sampling_seconds"],
                peak_rss_bytes=run["peak_rss_bytes"], path=str(checkpoint_path), sha256=digest(checkpoint_path),
                execution_sha256=fingerprint(run)))
    primary_executions = {c["execution_sha256"] for c in checkpoint_costs}
    supplemental_executions = set()
    supplemental_plan = None
    if (path/"supplemental.json").exists():
        supplemental_plan = read(path/"supplemental.json")["plan"]
        plan = supplemental_plan
        expected_tasks = {t["id"]: t for t in tasks()}
        if (plan["primary_manifest_sha256"] != digest(path/"manifest.json")
                or plan["study_identity"] != identity or plan["backend"] != BACKENDS[backend]
                or digest(plan["source"]) != plan["source_sha256"]
                or plan["maximum_combined_workers"] != metadata["workers"]+plan["workers"]
                or any(t != expected_tasks.get(t["id"]) for t in plan["tasks"])
                or plan["estimated_additional_process_bytes"] != plan["workers"]*max(
                    resource_estimate(t, configs)["estimated_process_bytes"] for t in plan["tasks"])):
            raise ValueError("Supplemental scheduling provenance mismatch")
        for task in plan["tasks"]:
            supplemental_path = path/"supplemental/checkpoints"/task["id"]/f"{plan['sweeps']:06d}.json.gz"
            if not supplemental_path.exists():
                continue
            saved = read(supplemental_path)
            request, run = saved["request"], saved["run"]
            if (request != dict(study_identity=identity, task=task, sweeps=plan["sweeps"],
                    input_sha256=hashlib.sha256(input_text(task, configs).encode()).hexdigest())
                    or saved["run_sha256"] != fingerprint(run)):
                raise ValueError("Supplemental checkpoint content mismatch")
            validate_checkpoint(run, task, configs, BACKENDS[backend], plan["sweeps"])
            if task["id"] in initial_states:
                if any(run[k] != v for k, v in initial_states[task["id"]].items()):
                    raise ValueError("Supplemental initialization differs")
            execution = fingerprint(run)
            supplemental_executions.add(execution)
            c = run["checkpoints"][0]
            checkpoint_costs.append(dict(task=task["id"], sweeps=plan["sweeps"],
                physical_cells=run["cells"],
                solve_seconds=c["solve_seconds"], prep_seconds=run["prep_seconds"],
                residual_seconds=c["residual_seconds"], sampling_seconds=c["sampling_seconds"],
                peak_rss_bytes=run["peak_rss_bytes"], path=str(supplemental_path),
                sha256=digest(supplemental_path), execution_sha256=execution))
    # Hard-linked copies count once; genuinely duplicate invocations retain
    # their separate timings/content fingerprints and are charged separately.
    checkpoint_costs = list({c["execution_sha256"]: c for c in checkpoint_costs}.values())
    trial_ids = [(r["task"]["id"], r["checkpoints"][0]["iterations"]) for r in doc["attempts"]]
    if len(trial_ids) != len(set(trial_ids)) or any(gate(r)["accepted"] for r in doc["attempts"]):
        raise ValueError("Duplicate rejected trials or accepted solve mislabeled as rejected")
    for run in doc["runs"]+doc["attempts"]:
        documents, origins = [], run["checkpoint_origins"]
        for origin in origins:
            if digest(origin["path"]) != origin["sha256"]:
                raise ValueError("Selected checkpoint fingerprint mismatch")
            documents.append(cached[origin["path"]])
        if assemble(run["task"], documents, origins) != run:
            raise ValueError("Assembled solve differs from independent checkpoints")
    # Rejected trials are retained; acceptance is an observed result, not an
    # audit prerequisite. A valid archive may establish that joint scope fails.
    supplemental_complete = supplemental_plan is None or len(supplemental_executions) == len(supplemental_plan["tasks"])
    result = dict(complete=bool(summary["complete"] and supplemental_complete), final_cases=len(doc["runs"]),
        accepted_cases=sum(r["accepted"] for r in summary["runs"]),
        rejected_budget_triples=len(doc["attempts"]), unique_checkpoints=len(checkpoint_costs),
        executed_solve_seconds=sum(c["solve_seconds"] for c in checkpoint_costs),
        executed_fixed_sweeps=sum(c["sweeps"] for c in checkpoint_costs),
        executed_physical_cell_sweeps=sum(c["physical_cells"]*c["sweeps"] for c in checkpoint_costs),
        executed_preparation_seconds=sum(c["prep_seconds"] for c in checkpoint_costs),
        selected_certification_solve_seconds=sum(r["certification_solve_seconds"] for r in summary["runs"]),
        selected_certification_fixed_sweeps=sum(c["iterations"] for r in doc["runs"] for c in r["checkpoints"]),
        selected_certification_physical_cell_sweeps=sum(r["cells"]*c["iterations"] for r in doc["runs"] for c in r["checkpoints"]),
        peak_rss_bytes=max((c["peak_rss_bytes"] for c in checkpoint_costs), default=0),
        primary_unique_executions=len(primary_executions), supplemental_executions=len(supplemental_executions),
        supplemental_reused_in_primary=len(primary_executions & supplemental_executions),
        supplemental_plan=supplemental_plan,
        joint_scope_established=summary["joint_scope_established"], checkpoints=checkpoint_costs,
        archive_sha256=digest(path/"raw.json.gz"))
    return doc, summary, result


def cross_backend(serial, parallel):
    aa = {r["task"]["id"]: r for r in serial["runs"]}
    bb = {r["task"]["id"]: r for r in parallel["runs"]}
    rows = []
    for key in sorted(aa.keys() & bb.keys()):
        a, b = aa[key], bb[key]
        if not gate(a)["accepted"] or not gate(b)["accepted"]:
            continue
        for attr in ("initial_planes", "profile_planes", "sample_x", "sample_y", "z_faces", "roof_errors"):
            if a[attr] != b[attr]:
                raise ValueError(f"CPU initial/support disagreement: {key}/{attr}")
        for height in HEIGHTS:
            av, bv = [array(values(r, height)) for r in (a, b)]
            am, bm = np.isfinite(av).all(axis=1), np.isfinite(bv).all(axis=1)
            np.testing.assert_array_equal(am, bm)
            ap, = [p for p in a["checkpoints"][-1]["planes"] if p["height"] == height]
            bp, = [p for p in b["checkpoints"][-1]["planes"] if p["height"] == height]
            if ap["flags"] != bp["flags"]:
                raise ValueError("CPU occupancy flags disagree")
            delta = np.linalg.norm(av[am]-bv[bm], axis=1)/5
            rows.append(dict(task=key, height=height, max_vector_difference_over_Uref=float(delta.max()),
                             p95_vector_difference_over_Uref=float(np.percentile(delta, 95))))
    return rows


def decisions(summary):
    return {(r["comparison"], r["family"], r["direction"], r["height"], r["region"]):
        (r["matched_accuracy"], r.get("within_budget"), r.get("local_checks_within_budget"),
         r.get("combined_within_budget")) for r in summary["comparisons"]}


def main():
    root = Path("docs/data/joint-grid-verification")
    documents, summaries, costs = {}, {}, {}
    for backend in BACKENDS:
        documents[backend], summaries[backend], costs[backend] = audit_backend(root/backend, backend)
    common_decisions = decisions(summaries["serial"])
    other = decisions(summaries["openmp"])
    shared = common_decisions.keys() & other.keys()
    cross = cross_backend(documents["serial"], documents["openmp"])
    fields_agree = all(r["max_vector_difference_over_Uref"] <= 1e-3
                      and r["p95_vector_difference_over_Uref"] <= 5e-4 for r in cross)
    result = dict(backends=costs, cross_backend=cross,
        complete=all(c["complete"] for c in costs.values()),
        cross_backend_decisions_equal=bool(common_decisions == other),
        shared_comparison_decisions_equal=all(common_decisions[k] == other[k] for k in shared),
        shared_comparisons=len(shared),
        cross_backend_fields_within_stability_budget=fields_agree,
        joint_scope_established=bool(all(s["joint_scope_established"] for s in summaries.values())
                                    and fields_agree and common_decisions == other),
        additional_source_sha256={str(p): digest(p) for p in (Path(__file__), Path("tests/test_joint_grid_verification.py"))})
    atomic_json(root/"audit.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("backends", "cross_backend")}, indent=2))


if __name__ == "__main__":
    main()
