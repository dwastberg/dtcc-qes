"""Checks of the scoring protocol: python -m pytest experiments/accuracy/test_score.py"""
import numpy as np

import data
import score


def test_mean_speed_limits():
    assert np.isclose(data.mean_speed(3.0, 0.0), 3.0)
    sigma = np.sqrt(2 * 1.5 / 3)
    assert np.isclose(data.mean_speed(0.0, 1.5), 2 * sigma * np.sqrt(2 / np.pi))
    rng = np.random.default_rng(1)
    for m, k in ((1.0, 0.3), (0.2, 1.0), (2.0, 0.1)):
        sample = rng.normal(0, np.sqrt(2 * k / 3), (400000, 3)) + [m, 0, 0]
        assert abs(data.mean_speed(m, k) - np.linalg.norm(sample, axis=1).mean()) < 5e-3
        assert data.mean_speed(m, k) <= np.sqrt(m * m + 2 * k) + 1e-12


def test_slope_identity_and_shrinkage():
    rng = np.random.default_rng(2)
    m = rng.normal(0.5, 0.1, (40, 6))
    s = 0.5 + 1.8 * (m - 0.5) + rng.normal(0, 0.2, m.shape)
    st = score.stats(s, m)
    slope = np.polyfit(s.ravel(), m.ravel(), 1)[0]
    assert np.isclose(st["b"], slope) and np.isclose(st["b"], st["R"] / st["r"])
    candidate = 0.5 + 0.5 * (s - 0.5) + rng.normal(0, 0.01, m.shape)
    shrunk, factor = score.shrinkage(s, candidate, m)
    assert np.isclose(shrunk.std(), candidate.std()) and np.isclose(score.stats(shrunk, m)["R"], st["R"])
    assert 0.4 < factor < 0.6


def test_paired_interval_is_narrower_than_separate():
    rng = np.random.default_rng(3)
    m = rng.normal(0.5, 0.15, (60, 8))
    parent = m + rng.normal(0, 0.15, m.shape)
    candidate = parent - 0.01 * np.sign(parent - m)
    groups = np.arange(60)
    diff = score.paired(candidate, parent, m, groups, replicates=300)["MAE"]
    separate = score.scored(parent, m, groups, replicates=300)["MAE"]
    assert diff[0] < 0 and diff[2] < 0
    assert diff[2] - diff[1] < 0.2 * (separate[2] - separate[1])


def test_vector_and_signs():
    m = np.array([[1.0, 0.0, np.nan], [-0.5, 0.2, np.nan], [0.3, 0.0, np.nan]])
    s = np.array([[1.1, 0.0, 0.0], [0.5, 0.2, 0.0], [0.3, 0.1, 0.0]])
    v = score.vector_stats(s, m)
    assert np.isnan(v["MAE_W"]) and np.isclose(v["MAE_U"], (0.1 + 1.0 + 0.0) / 3)
    assert score.sign_errors(s[:, 0], m[:, 0]) == dict(n=3, wrong=1, measured_reverse=1, reverse_found=0)
