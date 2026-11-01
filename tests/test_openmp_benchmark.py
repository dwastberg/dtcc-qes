"""Independent checks of the bounded benchmark's reported error measures."""

from fixtures.support import load_tool
import importlib.util
from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
benchmark = load_tool('openmp_benchmark', TOOLS / 'benchmark_openmp.py')


def test_vector_error_is_distinct_from_speed_error():
    result = benchmark.metrics([[3, 4, 0]], [[-3, -4, 0]])
    assert result['common_fluid_points'] == 1
    assert result['p95_vector_error_mps'] == pytest.approx(10)
    assert result['max_vector_error_mps'] == pytest.approx(10)
    assert result['p95_speed_error_mps'] == 0
    assert result['max_speed_error_mps'] == 0


def test_invalid_support_is_counted_and_excluded_from_errors():
    result = benchmark.metrics([[3, 4, 0], None, [5, 0, 0], None],
                               [[0, 0, 0], [1, 0, 0], None, None])
    assert result['common_fluid_points'] == 1
    assert result['validity_changes'] == 2
    assert result['p95_vector_error_mps'] == pytest.approx(5)
    assert result['max_speed_error_mps'] == pytest.approx(5)


def test_percentile_and_maximum_are_reported_independently():
    result = benchmark.metrics([[1, 0, 0], [3, 0, 0]], [[0, 0, 0], [0, 0, 0]])
    assert result['p95_speed_error_mps'] == pytest.approx(2.9)
    assert result['max_speed_error_mps'] == pytest.approx(3)
