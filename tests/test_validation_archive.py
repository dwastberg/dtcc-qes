import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "archive_results", Path(__file__).parents[1] / "validation/archive_results.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_archive_preserves_evidence_and_refuses_overwrite(tmp_path):
    output = tmp_path / "fast"
    output.mkdir()
    (output / "summary.txt").write_text("baseline")
    figure = output / "plot.png"
    figure.write_bytes(b"figure")
    runs = tmp_path / "runs/A"
    runs.mkdir(parents=True)
    for ext in ("json", "npz"):
        (runs / f"key.{ext}").write_bytes(ext.encode())
    args = (tmp_path, "baseline-fast", "abc123", output, [figure], [("A", "key")], "fingerprint")
    archive = module.archive_results(*args)
    manifest = json.loads((archive / "manifest.json").read_text())
    assert len(manifest["sha256"]) == 4
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((archive / name).read_bytes()).hexdigest() == digest
    (output / "summary.txt").write_text("changed")
    assert (archive / "summary.txt").read_text() == "baseline"
    with pytest.raises(FileExistsError):
        module.archive_results(*args)
    with pytest.raises(ValueError):
        module.archive_results(tmp_path, "../escape", *args[2:])
