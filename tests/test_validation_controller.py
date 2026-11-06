"""Campaign controls can run from a clean checkout without research archives."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
from aij.controller import journal, require_predecessor, reserve_stage
from aij.evidence import file_hash, write_json
from aij.workers import run_worker

LIMITS = dict(qualification=6, coarse=2, refinement=2, transfer=2)
PREDECESSORS = dict(coarse="qualification", refinement="coarse", transfer="refinement")


def predecessor(root):
    folder = reserve_stage(root, "qualification", limits=LIMITS)
    write_json(folder / "manifest.json", dict(identity={"binary": "frozen"}))
    (folder / "fields.npz").write_bytes(b"immutable evidence")
    journal(folder, dict(decision="pass", checks=dict(parity=True), attempts=6))
    return folder


def require(root):
    return require_predecessor(root, "coarse", {"binary": "frozen"},
                               limits=LIMITS, predecessors=PREDECESSORS)


def test_reservation_cannot_be_replenished_or_reordered(tmp_path):
    reserve_stage(tmp_path, "coarse", limits=LIMITS)
    with pytest.raises(FileExistsError):
        reserve_stage(tmp_path, "coarse", limits=LIMITS)
    with pytest.raises(ValueError, match="earlier stage"):
        reserve_stage(tmp_path, "qualification", limits=LIMITS)
    with pytest.raises(ValueError, match="Unknown campaign stage"):
        reserve_stage(tmp_path, "typo", limits=LIMITS)


@pytest.mark.parametrize("mutation", ["decision", "epoch", "empty_checks", "false_check",
    "truthy_check", "attempts", "outcome", "changed_evidence", "missing_evidence", "escape"])
def test_predecessor_fails_closed(tmp_path, mutation):
    folder = predecessor(tmp_path)
    assert require(tmp_path) == "qualification"
    report = json.loads((folder / "report.json").read_text())
    if mutation == "decision": report["decision"] = "stop"
    elif mutation == "epoch": write_json(folder / "manifest.json", dict(identity={"binary": "other"}))
    elif mutation == "empty_checks": report["checks"] = {}
    elif mutation == "false_check": report["checks"]["parity"] = False
    elif mutation == "truthy_check": report["checks"]["parity"] = "False"
    elif mutation == "attempts": report["attempts"] = 5
    elif mutation == "outcome": write_json(folder / "outcome.json", dict(complete=False))
    elif mutation == "changed_evidence": (folder / "fields.npz").write_bytes(b"altered")
    elif mutation == "missing_evidence": (folder / "fields.npz").unlink()
    elif mutation == "escape":
        outside = tmp_path / "outside"; outside.write_text("outside stage")
        report["evidence_hashes"] = {"../outside": file_hash(outside)}
    write_json(folder / "report.json", report)
    with pytest.raises((ValueError, FileNotFoundError)):
        require(tmp_path)


def test_journal_preserves_worker_report_and_failure_and_supports_external_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = reserve_stage(Path("external"), "qualification", limits=LIMITS)
    plan = tmp_path / "plan.md"; plan.write_text("plan\n")
    report = dict(decision="stop", checks=dict(parity=np.bool_(False)), attempts=2)
    path = journal(folder, report, plan=plan)
    frozen = path.read_bytes()
    failure = journal(folder, report, plan=plan)
    assert path.read_bytes() == frozen
    assert failure.name == "supervisor-failure.json"
    assert "external/qualification/report.json" in plan.read_text()
    failure_bytes = failure.read_bytes()
    with pytest.raises(FileExistsError): journal(folder, report, plan=plan)
    assert failure.read_bytes() == failure_bytes
    assert "evidence_hashes" not in report  # Caller retains its original record.


def test_worker_preserves_failure_logs_and_has_no_memory_rejection(tmp_path):
    result = run_worker([sys.executable, "-S", "-c",
                         "import sys; print('output'); print('failure', file=sys.stderr); sys.exit(7)"],
                        tmp_path / "failure.log", deadline=3.)
    assert result["status"] == "failed" and result["returncode"] == 7
    assert result["rss_limit_bytes"] is None and not result["complete"]
    assert Path(result["stdout_path"]).read_text().strip() == "output"
    assert Path(result["stderr_path"]).read_text().strip() == "failure"


def test_worker_success_and_deadline(tmp_path):
    result = run_worker([sys.executable, "-S", "-c", "print('complete')"], tmp_path / "done.log", deadline=3.)
    assert result["complete"] and result["rss_limit_bytes"] is None
    result = run_worker([sys.executable, "-S", "-c", "import time; time.sleep(10)"], tmp_path / "timeout.log", deadline=.1)
    assert result["status"] == "timeout" and not result["complete"]
