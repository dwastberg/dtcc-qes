"""Audit complete raw matrices, provenance, decisions and CPU agreement."""
from pathlib import Path
import gzip
import json

import numpy as np
from run_precision_verification import (digest, gate, require_precision_reference, summarize, tasks)
from run_horizontal_sensitivity import references
from run_auto_grid_controls import HEIGHTS, height_run


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def audit_document(path, phase, precision_doc=None):
    doc = read(path)
    metadata = doc["metadata"]
    assert metadata["phase"] == phase
    expected = {t["id"] for t in tasks(phase)}
    assert {r["task"]["id"] for r in doc["runs"]} == expected and len(doc["runs"]) == len(expected)
    for source, expected_digest in metadata["source_sha256"].items():
        assert digest(source) == expected_digest, source
    assert digest(metadata["executable"]) == metadata["executable_sha256"]
    assert digest(metadata["reference"]) == metadata["reference_sha256"]
    calculated = summarize(doc, precision_doc)
    assert calculated == json.loads(path.with_name("summary.json").read_text())
    assert calculated["complete"]
    return doc, calculated


def main():
    base = Path("docs/data")
    documents = {}
    summaries = {}
    result = dict(backends={}, cross_backend=[], additional_source_sha256={str(p): digest(p) for p in (
        Path(__file__), Path("tools/plot_precision_verification.py"), Path("src/cpp/wind_config.h"),
        Path("src/cpp/wind_runner.cpp"), Path("src/cpp/bindings.cpp"), Path("CMakeLists.txt"),
        Path("src/dtcc_qes/wind.py"), Path("src/dtcc_qes/result.py"))})
    for backend in ("serial", "openmp"):
        precision_path = base/"precision-remedy"/backend/"raw.json.gz"
        precision, ps = audit_document(precision_path, "precision")
        require_precision_reference(precision)
        assert all(gate(r)["ten_times_tighter_accepted"] for r in precision["runs"]
                   if r["task"]["precision"] == "float64" and r["task"]["direction"] == 270)
        verification, vs = audit_document(base/"lateral-horizontal-verification"/backend/"raw.json.gz",
                                          "verification", precision)
        assert verification["metadata"]["precision_reference_sha256"] == digest(precision_path)
        assert all(r["accepted"] for r in vs["runs"])
        refs, _ = references(Path(precision["metadata"]["reference"]))
        matched = []
        for run in precision["runs"]:
            task = run["task"]
            if task["precision"] != "float32":
                continue
            old = refs[task["family"], task["direction"], task["resolution"]]
            checkpoints = {c["iterations"]: c for c in old["checkpoints"]}
            count = 0
            for c in run["checkpoints"]:
                if c["iterations"] not in checkpoints:
                    continue
                ref = checkpoints[c["iterations"]]
                for key in ("max_divergence", "rms_divergence", "top_band_max_divergence", "max_multiplier_change"):
                    assert c[key] == ref[key], (task["id"], key)
                for p, q in zip(c["planes"], ref["planes"]):
                    assert p["height"] == q["height"] and p["velocity"] == q["velocity"]
                count += 1
            assert count, "No shared archived float32 checkpoint"
            matched.append(dict(task=task["id"], exact_shared_checkpoints=count))
        tighter_changes = []
        for run in precision["runs"]:
            task = run["task"]
            if task["precision"] != "float64" or task["direction"] != 270:
                continue
            earlier = [r for r in precision["attempts"] if r["task"]["id"] == task["id"] and gate(r)["accepted"]]
            if not earlier:
                continue
            before = min(earlier, key=lambda r: r["checkpoints"][0]["iterations"])
            for height in HEIGHTS:
                av, bv = [np.array([v if v is not None else [np.nan]*3
                    for v in height_run(r, height)["checkpoints"][-1]["velocity"]]) for r in (before, run)]
                mask = np.isfinite(av).all(axis=1)
                np.testing.assert_array_equal(mask, np.isfinite(bv).all(axis=1))
                delta = np.linalg.norm(av[mask]-bv[mask], axis=1)/5
                maximum, p95 = float(delta.max()), float(np.percentile(delta, 95))
                assert maximum <= 1e-3 and p95 <= 5e-4
                tighter_changes.append(dict(task=task["id"], height=height,
                    common_final_sweeps=before["checkpoints"][-1]["iterations"],
                    tighter_final_sweeps=run["checkpoints"][-1]["iterations"],
                    max_vector_difference_over_Uref=maximum, p95_vector_difference_over_Uref=p95))
        result["backends"][backend] = dict(precision_accepted=ps["accepted"], tighter_accepted=ps["tighter_accepted"],
            verification_accepted=vs["accepted"], precision_rejected_budget_trials=len(precision["attempts"]),
            verification_rejected_budget_trials=len(verification["attempts"]), exact_float32_controls=matched,
            tighter_output_comparisons=tighter_changes,
            archives={str(p): digest(p) for p in (precision_path, base/"lateral-horizontal-verification"/backend/"raw.json.gz")})
        documents[backend] = {r["task"]["id"]: r for r in precision["runs"]+verification["runs"]}
        summaries[backend] = vs
    def decisions(summary):
        return {(r["comparison"], r["family"], r["direction"], r["height"], r["region"]):
                (r["matched_accuracy"], r.get("within_budget")) for r in summary["comparisons"]}
    assert decisions(summaries["serial"]) == decisions(summaries["openmp"])
    result["cross_backend_comparison_decisions_equal"] = True
    result["cross_backend_comparisons"] = len(decisions(summaries["serial"]))
    assert documents["serial"].keys() == documents["openmp"].keys()
    for name, serial in documents["serial"].items():
        parallel = documents["openmp"][name]
        assert serial["z_faces"] == parallel["z_faces"]
        for stage in ("profile_planes", "initial_planes"):
            assert serial[stage] == parallel[stage], (name, stage)
        largest = 0
        for a, b in zip(serial["checkpoints"][-1]["planes"], parallel["checkpoints"][-1]["planes"]):
            assert a["height"] == b["height"] and a["flags"] == b["flags"]
            av = np.array([v if v is not None else [np.nan]*3 for v in a["velocity"]])
            bv = np.array([v if v is not None else [np.nan]*3 for v in b["velocity"]])
            am, bm = np.isfinite(av).all(axis=1), np.isfinite(bv).all(axis=1)
            np.testing.assert_array_equal(am, bm)
            largest = max(largest, float(np.linalg.norm(av[am]-bv[bm], axis=1).max()/5))
        result["cross_backend"].append(dict(task=name, final_max_vector_difference_over_Uref=largest,
            initial_and_profile_support_exact=True, masks_and_flags_exact=True))
    path = base/"precision-remedy"/"audit.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print("Raw matrices, source/binary hashes, exact float32 controls and backend comparisons audited")


if __name__ == "__main__":
    main()
