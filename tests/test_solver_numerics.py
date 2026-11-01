"""Reference qualification must reject insufficient or changed evidence."""

from fixtures.support import load_tool
import json
from pathlib import Path
import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / "tools/run_solver_numerics.py"
module = load_tool("solver_numerics", PATH)


def triple(tmp_path):
    rows = []
    for i, n in enumerate([500, 1000, 2000]):
        samples = np.zeros((1, 6, 4))
        samples[:, :, 3] = 1
        np.savez_compressed(tmp_path / f"{i}.npz", samples=samples)
        rows.append(
            dict(
                status="completed",
                request=dict(
                    id=str(i), case="case", purpose="reference_triple", iterations=n
                ),
                result=dict(
                    initial_hashes=["same"] * 4,
                    plane_points=2,
                    checkpoints=[dict(mass=dict(maximum=1e-5, rms=1e-6))],
                ),
            )
        )
    return rows


def test_triple_requires_every_gate(tmp_path):
    rows = triple(tmp_path)
    assert module.qualify(rows, tmp_path)[0]["accepted"]
    rows[0]["result"]["checkpoints"][-1]["mass"]["maximum"] = 1
    assert not module.qualify(rows, tmp_path)[0]["accepted"]
    rows[0]["result"]["checkpoints"][-1]["mass"]["maximum"] = 1e-5
    rows[1]["result"]["initial_hashes"][0] = "different"
    assert not module.qualify(rows, tmp_path)[0]["accepted"]


def test_reference_rejects_mask_change_and_invalid_receptor(tmp_path):
    rows = triple(tmp_path)
    a = np.zeros((1, 6, 4))
    a[:, :, 3] = 1
    a[0, -1, 3] = 0
    np.savez_compressed(tmp_path / "2.npz", samples=a)
    assert not module.qualify(rows, tmp_path)[0]["accepted"]
    np.savez_compressed(tmp_path / "1.npz", samples=a)
    np.savez_compressed(tmp_path / "0.npz", samples=a)
    assert not module.qualify(rows, tmp_path)[0]["accepted"]


def test_reference_checks_both_pairs_and_both_heights(tmp_path):
    rows = triple(tmp_path)
    a = np.zeros((1, 6, 4))
    a[:, :, 3] = 1
    a[0, 2, 0] = 0.01
    np.savez_compressed(tmp_path / "0.npz", samples=a)
    result = module.qualify(rows, tmp_path)[0]
    assert not result["accepted"] and result["pairs"][0][1]["maximum"] > 0.001
    assert result["pairs"][1][1]["maximum"] == 0


def test_incomplete_not_qualified(tmp_path):
    rows = triple(tmp_path)
    rows[1]["status"] = "failed"
    r = module.qualify(rows, tmp_path)[0]
    assert not r["accepted"] and not r["complete"]
    assert not module.qualify(rows[:2], tmp_path)[0]["accepted"]


def test_study_inputs_are_exact_and_bounded():
    case = module.affordable_cases()[1]
    text = module.stdin_for(case, dict(iterations=2000, cadence=25, direction=270))
    assert text.split()[:10] == [
        "80",
        "80",
        "32",
        "2.0",
        "5",
        "270",
        "10",
        "2000",
        "25",
        "1",
    ]
    assert len(case["buildings"]) == 20


def test_invalid_samples_keep_nan_velocity_without_fabricating_validity():
    a = np.zeros((6, 4))
    a[:, 3] = 1
    a[0, :3] = np.nan
    a[0, 3] = 0
    result = module.compare_samples(a, a, 2)
    assert result[0]["common_valid"] == 2
    b = a.copy()
    b[1, 0] = np.nan
    with pytest.raises(ValueError, match="Nonfinite valid"):
        module.compare_samples(a, b, 2)


def test_reference_rejects_wrong_independent_budgets(tmp_path):
    rows = triple(tmp_path)
    rows[1]["request"]["iterations"] = 1500
    assert not module.qualify(rows, tmp_path)[0]["accepted"]


def test_hotspot_arithmetic_replays_frozen_evidence():
    import importlib.util

    path = PATH.with_name("analyze_solver_numerics.py")
    analysis = load_tool("numerics_analysis", path)
    evidence = PATH.parents[1] / "docs/data/solver-control-s5b"
    if not (evidence / "results.json").exists():
        pytest.skip("Published S5b study not present")
    result = analysis.analyze(evidence)
    assert result["passed"] and len(result["hotspots"]) == 50
    core = [
        r
        for r in result["hotspots"]
        if r["worker"] in ("00", "02", "03")
        and r["iteration"] == 2000
        and r["group"] == 1
    ]
    assert len(core) == 3
    assert all(
        r["classification"] == "solid_to_fluid_operator_mask_reconstruction_defect"
        for r in core
    )
    assert all(abs(r["divergence_minus_half_residual"]) > 3 for r in core)


def test_prepare_uses_published_cases_without_historical_build_tree(
    tmp_path, monkeypatch
):
    root = PATH.parents[1]
    evidence = root / "docs/data/solver-control-s5b"
    if not evidence.exists():
        pytest.skip("Published S5b inputs not available")
    isolated = tmp_path / "checkout"
    isolated.mkdir()
    # A fresh checkout has published evidence, not local benchmark output dirs.
    (isolated / "docs").mkdir()
    (isolated / "docs/data").symlink_to(root / "docs/data", target_is_directory=True)
    for name in module.OVERLAYS:
        dest = isolated / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((root / name).read_bytes())
    monkeypatch.setattr(module, "ROOT", isolated)
    protocol = module.prepare(tmp_path / "prepared")
    assert protocol["workers"] == 16
    assert len(list((tmp_path / "prepared/cases").glob("*.json"))) == 6
    inventory = json.loads((tmp_path / "prepared/reference-inventory.json").read_text())
    assert inventory["existing"][2]["sha256"] is None
