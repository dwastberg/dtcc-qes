"""ΔK and relative peaks have distinct, explicit denominators."""

from pathlib import Path
import numpy as np
import pytest
from fixtures.support import load_tool


def test_delta_k_uses_reference_speed_and_peak_uses_comparison_reference():
    module = load_tool(
        "turbulence_domain_metrics",
        Path(__file__).parents[1] / "tools/check_turbulence_domain.py",
    )
    a, b = np.array([1.0, 2.0]), np.array([1.0, 4.0])
    actual = module.error_metrics(a, b)
    assert actual["p95_abs_delta_K"] == pytest.approx(np.quantile(np.abs(a - b), 0.95))
    assert actual["peak_relative_difference"] == 0.5
    assert module.error_metrics([0.0], [0.0])["peak_relative_difference"] is None
