"""Repeat the declared bounded matrix using its already-built frozen probes.

Run only after competing build/test workers finish. The full profiler is still
the build/reproduction entry point. This wrapper executes its unchanged matrix
code, retaining the original probe sources and declaring new timing outcomes.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--prior-profile", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import profile_solver_monitor as profile
common, audit = profile.common, profile.audit
prior = json.loads((args.prior_profile / "protocol.json").read_text())
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
for name in ("s2-probe-sources.tar.gz", "s3-probe-sources.tar.gz", "s2-build.log", "s3-build.log"):
    shutil.copyfile(args.prior_profile / name, output / name)
sources = prior["sources"]
executables = {label:(args.work_dir / f"{label}-build/solver_monitor_probe").resolve() for label in ("s2", "s3")}
args.baseline_archive = ROOT / "docs/data/solver-control-s2/final-sources.tar.gz"
args.candidate_archive = Path(__file__).resolve().parent / "sources.tar.gz"
tree = ast.parse(Path(profile.__file__).read_text())
body = next(node.body for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
start = next(i for i, node in enumerate(body) if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "layers" for target in node.targets))
exec(compile(ast.Module(body=body[start:], type_ignores=[]), profile.__file__, "exec"))
