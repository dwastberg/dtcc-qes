"""Independent contributor and provenance checks using manufactured fields."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
from aij.sampling import probe_sample
from aij.stage_sampling import StageSampler
from fixtures.sampling import manufactured


def captured():
    result = manufactured()
    # A solid contributor forces canonical nearest-fluid fallback.
    result.cell_flags[:, 1, 1] = 0
    xyz = np.asarray(result.origin) + np.array([[3., .5, 1.3], [1.5, 1.5, 1.75], [50., 50., 1.75]])
    prepared = SimpleNamespace(resolution=result.resolution, origin=result.origin,
        domain=dict(shape=list(result.cell_flags.shape), vertical_grid=dict(effective_faces=result.z_faces)))
    sampler = StageSampler(xyz)
    cells = np.array(sampler(None, prepared))
    keys = tuple(cells[:, d] for d in (2, 1, 0))
    velocity, flags = result.velocity[keys], result.cell_flags[keys]
    e = dict(stages=["canyon", "projection"], stage_cells=cells,
             stage_velocity=np.stack([velocity * .5, velocity]),
             stage_flags=np.stack([flags, flags]))
    return sampler, replace(result, metadata=dict(experiment=e)), xyz


def test_stages_reproduce_canonical_vectors_and_methods_on_nonuniform_grid():
    sampler, result, xyz = captured()
    before = result.velocity.copy()
    sampled = sampler.sample(result)
    expected = probe_sample(result, xyz)
    assert sampled["final_bitwise_parity"]
    np.testing.assert_array_equal(sampled["velocity"][-1], expected["velocity"])
    np.testing.assert_array_equal(sampled["method"][-1], expected["method"])
    assert set(expected["method"]) == {"linear", "nearest_fluid", "none"}
    np.testing.assert_allclose(sampled["velocity"][0], expected["velocity"] * .5, equal_nan=True)
    np.testing.assert_array_equal(result.velocity, before)
    assert len(sampler.cells) == len(np.unique(sampler.cells, axis=0))


@pytest.mark.parametrize("mutation", ["missing_projection", "duplicate", "truncated_velocity", "truncated_flags", "cells", "vectors", "method"])
def test_corrupt_capture_is_rejected(mutation):
    sampler, result, _ = captured()
    result = replace(result, metadata=deepcopy(result.metadata))
    e = result.metadata["experiment"]
    if mutation == "missing_projection": e["stages"][-1] = "other"
    elif mutation == "duplicate": e["stages"][0] = "projection"
    elif mutation == "truncated_velocity": e["stage_velocity"] = e["stage_velocity"][:1]
    elif mutation == "truncated_flags": e["stage_flags"] = e["stage_flags"][:, :-1]
    elif mutation == "cells": e["stage_cells"] = e["stage_cells"][::-1]
    elif mutation == "vectors": e["stage_velocity"][-1] += 1
    elif mutation == "method": e["stage_flags"][-1] = 0
    with pytest.raises(ValueError): sampler.sample(result)


@pytest.mark.parametrize("xyz", [[1, 2, 3], [[1, 2]], [[1, np.nan, 3]]])
def test_invalid_probe_coordinates_are_rejected(xyz):
    with pytest.raises(ValueError, match="finite coordinates"):
        StageSampler(xyz)


def test_sampling_requires_preparation():
    with pytest.raises(ValueError, match="Prepare stage contributors"):
        StageSampler([[0, 0, 0]]).sample(manufactured())
