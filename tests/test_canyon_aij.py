"""The AIJ comparison must not hide lost coverage or compare different rows."""
import numpy as np
import pytest

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
from aij.metrics import paired_scores


def test_paired_coverage_does_not_reward_dropped_observations():
    result = paired_scores([1.,2.,3.,4.], [1.,2.,np.nan,4.], [1.,2.,3.,5.])
    assert result["baseline_count"] == 4 and result["candidate_count"] == result["common_count"] == 3
    assert result["lost"] == 1 and result["gained"] == 0
    assert result["mae_change_percent"] == 0.


def test_paired_scores_reject_different_observation_shapes():
    with pytest.raises(ValueError, match="identical observation shapes"):
        paired_scores([1,2,3], [1,2], [1,2,3])


def test_paired_coverage_reports_gained_and_missing_measurements():
    result = paired_scores([1., 2., np.nan, 4.], [1., 2., 3., 4.], [1., 2., 3., np.nan])
    assert (result["lost"], result["gained"], result["common_count"]) == (0, 1, 2)
    assert result["baseline"] == result["candidate"] == {"count": 2}
    assert result["mae_change_percent"] is None


def test_paired_coverage_does_not_invent_percentage_from_perfect_baseline():
    result = paired_scores([1., 2., 3.], [1.1, 2., 3.], [1., 2., 3.])
    assert result["baseline"]["mae"] == 0.
    assert result["candidate"]["mae"] > 0.
    assert result["mae_change_percent"] is None
