"""Frozen S3 cost evidence must reject edits and incomplete matrices."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    spec = importlib.util.spec_from_file_location("profile_solver_monitor", ROOT / "tools/profile_solver_monitor.py")
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
finally:
    sys.path.pop(0)


def test_profile_audit_rejects_modified_or_incomplete_evidence(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(dict(completed=True, parity_passed=True)))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(files={"summary.json":profile.common.digest(summary.read_bytes())})))
    assert profile.audit(tmp_path)["passed"]
    summary.write_text(json.dumps(dict(completed=False, parity_passed=True)))
    with pytest.raises(ValueError, match="Changed S3"):
        profile.audit(tmp_path)
    manifest.write_text(json.dumps(dict(files={"summary.json":profile.common.digest(summary.read_bytes())})))
    with pytest.raises(ValueError, match="Incomplete S3"):
        profile.audit(tmp_path)
