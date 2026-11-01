"""S2 snapshot profiling must preserve arithmetic and reject edited evidence."""

from fixtures.support import load_tool
import importlib.util
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
profile = load_tool("profile_solver_s2", ROOT/"tools/profile_solver_s2.py")


def test_phase_instrumentation_preserves_solver_sources_and_native_calls(tmp_path):
    with tarfile.open(ROOT/"docs/data/solver-control-s1a/sources.tar.gz") as archive:
        archive.extractall(tmp_path,filter="data")
    files = list((tmp_path/"src/qes_core/solver").glob("*"))
    originals = {p:p.read_bytes() for p in files}
    runner = tmp_path/"src/qes_core/dtcc/wind_runner.cpp"
    before = runner.read_text().splitlines()
    profile.instrument(tmp_path)
    assert all(p.read_bytes() == content for p,content in originals.items())
    after = iter(runner.read_text().splitlines())
    for line in before:
        assert any(item == line for item in after), line
    with pytest.raises(ValueError,match="already instrumented"):
        profile.instrument(tmp_path)


def test_s2_audit_detects_source_and_evidence_tampering(tmp_path):
    tree = tmp_path/"tree"
    tree.mkdir()
    (tree/"x.cpp").write_text("source\n")
    snapshot = profile.legacy.archive_files(tmp_path/"sources.tar.gz",[tree/"x.cpp"],tree)
    profile.legacy.write_json(tmp_path/"summary.json",dict(completed=True,parity_passed=True))
    files = {n:profile.legacy.digest((tmp_path/n).read_bytes()) for n in ("sources.tar.gz","summary.json")}
    profile.legacy.write_json(tmp_path/"manifest.json",dict(sources={"sources.tar.gz":snapshot},files=files))
    assert profile.audit(tmp_path)["passed"]
    (tmp_path/"summary.json").write_text("{}")
    with pytest.raises(ValueError,match="Changed S2 evidence"):
        profile.audit(tmp_path)
