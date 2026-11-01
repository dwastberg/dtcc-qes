"""Check the existing log policy after native implementation changes.

Rerun the frozen S7 release workers against freshly built serial/OpenMP
packages. Require exact fields, diagnostics and numerical decisions; the only
permitted provenance change is the declared native implementation revision.
This does not qualify any new inflow family or change policy thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmark_prepared_wind import comparable
from compare_native_builds import stage_package

ROOT = Path(__file__).resolve().parents[1]


def check(output, serial, openmp):
    output.mkdir(parents=True, exist_ok=False)
    evidence = ROOT / "docs/data/solver-control-s7"
    protocol = json.loads((evidence / "release-online-protocol.json").read_text())
    expected = json.loads((evidence / "release-online-results.json").read_text())["rows"]
    if [r["request"] for r in expected] != protocol["rows"]:
        raise ValueError("Frozen worker matrix does not match its results")
    revisions = {}
    for name, folder in [("serial", serial), ("openmp", openmp)]:
        stage_package(ROOT, next(folder.glob("_qes*.so")), output / name)
        identity = (folder / "solver-policy-identity.txt").read_bytes()
        (output / f"{name}-identity.txt").write_bytes(identity)
        revisions[name] = hashlib.sha256(identity).hexdigest()
    if revisions["serial"] != revisions["openmp"]:
        raise ValueError("Native source/arithmetic identities differ")
    report = dict(passed=False, native_revision=revisions["serial"],
        previous_revision=expected[0]["control"]["policy_revision"],
        frozen_manifest_sha256=hashlib.sha256((evidence / "manifest.json").read_bytes()).hexdigest(),
        lock_sha256=hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(), workers=[])
    for req, old in zip(protocol["rows"], expected):
        print(req["id"], req["case"], req["variant"], flush=True)
        package = output / ("serial" if req.get("backend") == "serial" else "openmp")
        path = output / (req["id"] + ".json")
        command = [sys.executable, str(ROOT / "tools/validate_solver_policy.py"),
            "--worker", str(evidence), "--request", json.dumps(req),
            "--package", str(package), "--output", str(path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30,
            env=os.environ | {"PYTHONPATH": str(package), "OMP_NUM_THREADS": str(req["threads"]),
                              "OMP_DYNAMIC": "FALSE", "PYTHONDONTWRITEBYTECODE": "1"})
        (output / (req["id"] + ".log")).write_text(result.stdout + result.stderr)
        result.check_returncode()
        row = json.loads(path.read_text())
        differences = [key for key in ["status", "field_hashes", "diagnostics"] if row.get(key) != old.get(key)]
        if row.get("control") is not None:
            for key in ["accepted", "accuracy_status", "assessment_reason", "assessment",
                        "assessment_history", "checkpoint_history", "method", "monitor"]:
                if comparable(row["control"].get(key)) != comparable(old["control"].get(key)):
                    differences.append("control/" + key)
            if row["control"]["policy_revision"] != revisions["serial"]:
                differences.append("control/policy_revision")
        report["workers"].append(dict(request=req, differences=differences))
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        if differences:
            raise ValueError(f"Frozen policy regression in {req['id']}: {differences}")
    report["passed"] = True
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"All {len(expected)} frozen workers match exactly; only source identity changed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial", type=Path, required=True)
    parser.add_argument("--openmp", type=Path, required=True)
    args = parser.parse_args()
    check(args.output.resolve(), args.serial.resolve(), args.openmp.resolve())
