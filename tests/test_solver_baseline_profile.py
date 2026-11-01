"""Study integrity and fail-closed instrumentation, without running benchmarks."""

from fixtures.support import load_tool
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
profile = load_tool("solver_baseline_profile", ROOT/"tools/profile_solver_baseline.py")


def test_instrumentation_preserves_every_original_numerical_statement(tmp_path):
    # S0 instrumentation targets its immutable source snapshot, not the later
    # phase package. Historical evidence keeps its original source identity.
    with tarfile.open(ROOT/"docs/data/solver-control-s0/sources.tar.gz") as archive:
        archive.extractall(tmp_path,filter="data")
    originals = {name:(tmp_path/name).read_text().splitlines() for name in
        ("src/qes_core/winds/Solver_CPU.cpp","src/qes_core/winds/Solver_CPU_RB.cpp",
         "src/qes_core/dtcc/precision_solver.cpp")}
    profile.instrument(tmp_path)
    for name, original in originals.items():
        candidate = iter((tmp_path/name).read_text().splitlines())
        # Added clocks may surround statements, never replace or reorder them.
        for line in original:
            assert any(item==line for item in candidate), line
    with pytest.raises(ValueError,match="anchor"):
        profile.instrument(tmp_path)


def test_archive_audit_uses_frozen_sources_and_detects_tampering(tmp_path):
    source = tmp_path/"tree"
    source.mkdir()
    (source/"x.cpp").write_text("original\n")
    snapshot = profile.archive_files(tmp_path/"sources.tar.gz",[source/"x.cpp"],source)
    profile.write_json(tmp_path/"manifest.json",dict(sources={"sources.tar.gz":snapshot},legacy=dict(records={}),
        files={"sources.tar.gz":snapshot["sha256"]}))
    (source/"x.cpp").write_text("later refactor\n")
    assert profile.audit(tmp_path)["passed"]
    with (tmp_path/"sources.tar.gz").open("ab") as f:
        f.write(b"changed")
    with pytest.raises(ValueError,match="Changed archived file"):
        profile.audit(tmp_path)


def test_repeated_or_missing_anchor_is_rejected():
    for text in ("absent", "xx"):
        with pytest.raises(ValueError,match="once"):
            profile.replace_once(text,"x","y")


def test_inventory_excludes_function_arguments_and_comments():
    text = "std::vector<float> x, y; // std::vector<int> ignored;\nvoid f(std::vector<float> &argument);"
    result = profile.inventory(text,"wind")
    assert '"wind.x", x' in result and '"wind.y", y' in result
    assert "argument" not in result and "ignored" not in result
