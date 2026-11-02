"""Phase 2: grids, run specs, probe sampling and one small solve end to end."""

import json

import numpy as np
import pytest

from aij import campaigns, grids, runner, sampling
from aij.runspec import RunSpec
from dtcc_qes import wind


@pytest.mark.parametrize("dz", [4.0, 2.0, 1.0, 0.5])
def test_vertical_faces_centre_the_probe_layer(dz):
    faces = grids.vertical_faces(dz, 80.0, 36.0, max_dz=4 * dz)
    centres = (faces[:-1] + faces[1:]) / 2
    layer = int(np.argmin(np.abs(centres - grids.PROBE_HEIGHT)))
    assert centres[layer] == pytest.approx(2.0, abs=1e-9)
    assert faces[layer + 1] - faces[layer] == pytest.approx(dz)
    thickness = np.diff(faces)
    assert thickness.max() <= 4 * dz + 1e-9
    # A thinner remainder layer sits below the probe layer (dz/2 here, a 2:1 step); growth is gentle above it.
    assert np.all(thickness[layer + 1:] / thickness[layer:-1] <= grids.GROWTH + 1e-9)
    assert np.all(thickness[:layer] < dz + 1e-9)
    assert faces[-1] >= 80.0 and faces[0] == 0.0
    fine = faces <= 36.0
    assert np.allclose(np.diff(faces[fine])[1:], dz)  # uniform up to the fine top, after the bottom remainder


def test_vertical_faces_uniform_and_invalid():
    faces = grids.vertical_faces(2.0, 30.0, 10.0, growth=None)
    assert np.allclose(np.diff(faces)[1:], 2.0) and faces[1] == 1.0
    with pytest.raises(ValueError):
        grids.vertical_faces(8.0, 30.0, 10.0)


def test_runspec_key():
    spec = campaigns.case_e("N", resolution=2.0)
    assert spec.direction == 0.0 and spec.min_detail == 0.1 and spec.state == "after"
    assert RunSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec
    assert spec.key == campaigns.case_e("N", resolution=2.0).key
    assert spec.key != campaigns.case_e("N", resolution=1.0).key
    assert campaigns.case_d(45.0).direction == 225.0 and campaigns.case_d(45.0).min_detail is None
    keys = [s.key for s in campaigns.campaign("convergence")]
    assert len(keys) == len(set(keys)) == 32
    # Keys of stored runs must not change when campaigns move or grow.
    assert campaigns.case_d(0.0, resolution=2.0, turbulence=False).key == "3af75ea91b3dfde2"


def test_runspec_parameterizations():
    base = campaigns.case_d(0.0, resolution=2.0, turbulence=False)
    # Defaults, given explicitly, are dropped: the key of a default run never changes.
    assert campaigns.case_d(0.0, resolution=2.0, turbulence=False, parameterizations=dict(high_rise=0)).key == base.key
    tall = campaigns.case_d(0.0, resolution=2.0, turbulence=False, parameterizations=dict(high_rise=1, wake=2))
    assert tall.parameterizations == (("high_rise", 1),) and tall.key != base.key and tall.name.endswith("high_rise1")
    assert tall.to_dict()["parameterizations"] == dict(high_rise=1) and "parameterizations" not in base.to_dict()
    assert RunSpec.from_dict(json.loads(json.dumps(tall.to_dict()))) == tall
    assert tall.parameterization_spec() == wind.Parameterizations(high_rise=1)
    with pytest.raises(ValueError, match="wake must be nonzero"):
        campaigns.case_d(0.0, parameterizations=dict(wake=0))


def test_baseline_campaign():
    specs = campaigns.campaign("baseline")
    assert len(specs) == 3 + 2 * 16
    assert all(s.max_iterations == 2000 and s.tolerance == campaigns.FIXED_WORK_TOLERANCE for s in specs)
    assert {s.state for s in specs if s.case == "E"} == {"before", "after"}


@pytest.fixture(scope="module")
def solved():
    spec = campaigns.case_d(0.0, resolution=8.0, max_iterations=200, tolerance=1.2e-7, monitor=True)
    return spec, *runner.run(spec)


def test_record(solved, tmp_path):
    spec, record, arrays = solved
    probes = record["probes"]
    assert record["key"] == spec.key and record["schema"] == runner.RECORD_SCHEMA
    assert len(probes["K"]) == 78 and np.isfinite(probes["K"]).all()
    assert set(probes["method"]) <= {sampling.LINEAR, sampling.NEAREST_FLUID}
    assert record["diagnostics"]["iterations"] == 200
    assert record["qualification"]["solver"]["mode"] == "bounded"
    assert np.isfinite(probes["k"]).all() and np.all(probes["K_scalar"] >= probes["K"])
    assert np.all(probes["K_min"] <= probes["K"] + 1e-12) and np.all(probes["K_max"] >= probes["K"] - 1e-12)
    assert arrays["sampled_height"] == pytest.approx(2.0)
    path = runner.write(record, arrays, tmp_path)
    assert runner.load(tmp_path, spec.key)["probes"]["method"] == list(probes["method"])
    assert path.with_suffix(".npz").exists()


def test_linear_probes_match_an_independent_bilinear(solved):
    """Linear probe values equal a bilinear interpolation of the stored 2 m plane."""
    _, record, arrays = solved
    x, y, velocity = arrays["x"], arrays["y"], arrays["velocity"].astype(np.float64)
    probes = record["probes"]
    for (px, py, _), method, speed in zip(probes["xyz"], probes["method"], probes["speed"]):
        if method != sampling.LINEAR:
            continue
        i, j = np.searchsorted(x, px) - 1, np.searchsorted(y, py) - 1
        tx, ty = (px - x[i]) / (x[i + 1] - x[i]), (py - y[j]) / (y[j + 1] - y[j])
        v = ((1 - tx) * (1 - ty) * velocity[j, i] + tx * (1 - ty) * velocity[j, i + 1]
             + (1 - tx) * ty * velocity[j + 1, i] + tx * ty * velocity[j + 1, i + 1])
        assert np.linalg.norm(v) == pytest.approx(speed, rel=1e-5, abs=1e-6)


def test_fallback_probes_are_near_and_valid(solved):
    _, record, _ = solved
    probes = record["probes"]
    fallback = np.array(probes["method"]) == sampling.NEAREST_FLUID
    assert fallback.any()  # 8 m cells put several probes next to walls
    offset = np.linalg.norm(np.array(probes["sampled"])[fallback] - np.array(probes["xyz"])[fallback], axis=1)
    assert np.all(offset <= 8.0 * np.sqrt(2.0) + 1e-9)


def test_history_ends_at_the_record(solved):
    _, record, _ = solved
    history = record["history"]
    assert history["iterations"][0] == 0 and history["iterations"][-1] == 200 and not history["truncated"]
    linear = np.array(record["probes"]["method"]) == sampling.LINEAR
    last = np.array([np.nan if v is None else v for v in history["K"][-1]])
    np.testing.assert_allclose(last[linear], np.array(record["probes"]["K"])[linear], rtol=1e-5)
