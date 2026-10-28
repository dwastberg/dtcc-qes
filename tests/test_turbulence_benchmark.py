"""Exercise benchmark accounting and a real isolated native worker."""

import json
import importlib.util
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


_spec = importlib.util.spec_from_file_location(
    "turbulence_benchmark", Path(__file__).parents[1]/"tools/run_turbulence_benchmark.py")
benchmark = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(benchmark)


def test_statistics_retain_exclusions_and_zero_denominators():
    values = benchmark.changes([0, 2, np.nan, 4], [3, 3, 5, np.nan])
    assert values["common_count"] == 2
    assert values["zero_denominator_count"] == 1
    np.testing.assert_array_equal(values["excluded_indices"], [2, 3])
    assert values["zero_denominator_absolute"]["maximum"] == 3
    assert values["relative"]["count"] == 1


@pytest.mark.parametrize("failure", ["mask_mismatches", "count_mismatches", "computed_nonfinite",
                                     "invalid_finite_std", "invalid_finite_ti"])
def test_convergence_alone_cannot_accept_invalid_extraction(failure):
    run = dict(diagnostics=dict(converged=True), validity={failure: 1})
    assert not benchmark.accepted(run)
    assert not benchmark.pair(run, run)["accepted"]


def test_failed_solve_withholds_numerical_comparison():
    run = dict(diagnostics=dict(converged=False))
    assert benchmark.pair(run, run) == dict(accepted=False, reason="failed convergence or validity gate")


def test_independent_oracle_accepts_zero_and_rejects_indefinite_stress():
    stress = np.array([[0,0,0,0,0,0], [1,2,0,1,0,1]], dtype=np.float32)
    valid, eigen, projection, _ = benchmark.independent(stress, np.array([[1,0,0], [1,-1,0]]))
    np.testing.assert_array_equal(valid, [True, False])
    np.testing.assert_allclose(eigen, [0, -1])
    np.testing.assert_allclose(projection, [0, -1])


def test_turbulence_benchmark_self_test(tmp_path):
    tool = Path(__file__).resolve().parents[1] / "tools/run_turbulence_benchmark.py"
    output = tmp_path / "self-test.json"
    completed = subprocess.run(
        [sys.executable, str(tool), "--self-test", "--output", str(output)],
        text=True, capture_output=True, timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["passed"]
    assert report["checks"]["failed_solves_rejected"]
    assert report["checks"]["zero_denominators_accounted"]
    assert report["checks"]["invalid_interpolation_accounted"]
    assert report["worker"]["diagnostics"]["converged"]
    assert report["worker"]["validity"]["mask_mismatches"] == 0


def test_flat_error_decomposition_interpolates_variance(tmp_path):
    tool = Path(__file__).resolve().parents[1]/"tools/run_turbulence_benchmark.py"
    request, output = tmp_path/"request.json", tmp_path/"flat.json"
    request.write_text(json.dumps(benchmark.configuration("flat-control", "flat", top=32)))
    completed = subprocess.run([sys.executable, str(tool), "--worker", str(request),
                                "--output", str(output)], capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stdout+completed.stderr
    record = json.loads(output.read_text())
    for row in record["flat_profile"]:
        z = np.asarray(record["z"])
        exact_centres = 2.5*z/(z+.1)
        expected = np.sqrt(np.interp(row["height"], z, exact_centres**2))-row["analytic"]
        assert row["analytic_sampling_error"] == pytest.approx(expected, abs=1e-14)
        assert row["total_error"] == pytest.approx(row["derivative_error"]+expected, abs=1e-14)
        assert row["nearest_height"] == 1
