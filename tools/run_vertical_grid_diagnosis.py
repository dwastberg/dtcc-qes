"""Reproduce the bounded tower diagnosis; this is not a preset validation gate."""

import os
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess

from run_vertical_grid_study import evaluate

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(raw):
    results = []
    for run in raw["runs"]:
        checkpoints = []
        for checkpoint in run["checkpoints"]:
            inspection = checkpoint["solver_diagnostics"]
            checkpoints.append({
                "iterations": checkpoint["iterations"],
                "max_face_reconstruction_gap": inspection["max_face_reconstruction_gap"],
                "norms": inspection["norms"],
                "worst_cell": inspection["worst_stored_cells"][0],
            })
        probe = run["checkpoints"][-1]["precision_probe"]
        final = probe["checkpoints"][-1]["norms"]["cast_float_flux"]
        scale = run["hmax"] / 5
        results.append({
            "backend": run["backend"], "grid": run["grid"],
            "baseline_acceptance": evaluate(run), "checkpoints": checkpoints,
            "precision_probe": probe,
            "probe_final_residual_meets_base_bounds":
                final["max"] * scale <= 1e-3 and final["rms"] * scale <= 1e-4,
            "probe_final_residual_meets_tighter_bounds":
                final["max"] * scale <= 1e-4 and final["rms"] * scale <= 1e-5,
        })
    return {
        "metadata": raw["metadata"],
        "limitations": [
            "One tower geometry and one wind direction; no universal precision or aspect limit.",
            "Double probe warm-starts an existing float solution; it is not a from-zero solver test.",
            "Probe snapshots are not the full residual/velocity-stability acceptance gate.",
            "Probe retains float geometry/coefficients and reports corrected fields cast to float.",
            "Probe uses backend node order but no parallel updates; no performance comparison.",
        ],
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="append", type=Path,
                        help="Built native worker; repeat for multiple CPU backends")
    parser.add_argument("--output", type=Path, default=Path("build/vertical-grid-diagnosis/final"))
    parser.add_argument("--summarize", action="store_true", help="Use stored raw data without solving")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw_path = args.output / "raw.json.gz"
    if args.summarize:
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    else:
        workers = args.worker or [ROOT / "build/extension/vertical_grid_study",
                                  ROOT / "build/openmp/vertical_grid_study"]
        source_paths = [
            "tools/vertical_grid_study.cpp", "tools/vertical_grid_diagnostics.cpp",
            "tools/vertical_grid_diagnostics.h", "tools/run_vertical_grid_diagnosis.py",
            "tools/run_vertical_grid_study.py", "src/qes_core/dtcc/divergence.cpp",
            *[str(p) for p in [p for p in sorted(Path("src/qes_core").rglob("*")) if p.suffix in (".cpp", ".h", ".txt")]],
            "src/qes_core/winds/Wall.cpp", "src/qes_core/qes/Domain.cpp",
            "src/qes_core/dtcc/model_inputs.cpp", "CMakeLists.txt",
        ]
        raw = {"metadata": {
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(), "python": platform.python_version(),
            "qes_revision": (ROOT / "src/dtcc_qes/_qes_revision.txt").read_text().strip(),
            "source_sha256": {name: sha256(ROOT / name) for name in source_paths},
            "workers": [{"path": str(p.resolve()), "sha256": sha256(p)} for p in workers],
            "purpose": "Focused operator/roundoff diagnosis, not timing or automatic-preset validation",
        }, "runs": []}
        for worker in workers:
            # The OpenMP control fails the RMS bound at 1,000 sweeps; use the
            # same accepted 2,000/4,000/8,000 control budgets on both backends.
            for spacing, n in [("0.5", 2000), ("0.25", 8000)]:
                command = [str(worker.resolve()), "tower", spacing, "270", str(n), "--diagnose"]
                print("Running:", " ".join(command), flush=True)
                run = json.loads(subprocess.check_output(command, env=os.environ | {"DTCC_QES_STUDY_ORDER": "legacy"}, cwd=ROOT))
                run["command"] = command
                raw["runs"].append(run)
                # Retain completed work if a later backend/process fails.
                raw_path.write_bytes(gzip.compress(json.dumps(raw, allow_nan=False).encode(), mtime=0))
                print(run["backend"], spacing, "baseline accepted:", evaluate(run)["accepted"], flush=True)
    summary = summarize(raw)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print("Wrote", args.output / "summary.json")


if __name__ == "__main__":
    main()
