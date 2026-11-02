"""Phase 5: variants, the canopy inflow, the tuning search rules and the resampled scores."""

from dataclasses import replace

import numpy as np
import pytest

from aij import campaigns, case_d, case_e, cityutil, compare, inflow, sensitivity, tables
from aij.runspec import RunSpec


def test_canopy_height_matches_the_cities():
    for case, city in (("D", case_d.build_case_d().city), ("E", case_e.build_case_e("before").city)):
        rows = cityutil.footprints(city)
        area = np.array([p.area for _, p, _ in rows])
        height = np.array([h for _, _, h in rows])
        assert campaigns.CANOPY_HEIGHT[case] == pytest.approx((area * height).sum() / area.sum(), abs=0.005)


def test_canopy_profile():
    data = tables.load_inflow_e()
    approach = inflow.measured_profile(data, 0.0)
    profile = inflow.canopy_profile(data, 0.0, canopy_roughness=0.6, blending_height=36.0)
    above = np.array([36.0, 50.0, 120.0, 250.0])
    np.testing.assert_allclose(np.hypot(*profile.evaluate(above).T), np.hypot(*approach.evaluate(above).T), rtol=1e-9)
    low = np.array([0.5, 2.0, 15.9])
    expected = inflow.reference_speed(approach, 36.0) * np.log1p(low / 0.6) / np.log1p(36.0 / 0.6)
    np.testing.assert_allclose(np.hypot(*profile.evaluate(low).T), expected, rtol=2e-3)  # log-height interpolation
    # The normaliser stays the approach flow at the reference height.
    assert inflow.reference_speed(inflow.approach_profile(data, "canopy", 0.0, interpolation="log_height")) == \
        inflow.reference_speed(approach)
    assert profile.roughness_length == approach.roughness_length  # the QES-Turb ground is unchanged


def test_runspec_phase5_fields():
    base = campaigns.baseline()[3]
    canopy = campaigns.tuned({"canopy": (0.1, 6.0)}, select={("E", "before")})[0]
    assert canopy.inflow == "canopy" and canopy.canopy_roughness == pytest.approx(0.603)
    assert canopy.key != base.key and "canopy_roughness" not in base.to_dict()
    assert RunSpec.from_dict(canopy.to_dict()) == canopy
    with pytest.raises(ValueError, match="canopy"):
        replace(base, canopy_roughness=0.5)
    with pytest.raises(ValueError, match="0 < canopy_roughness < blending_height"):
        replace(base, inflow="canopy", canopy_roughness=5.0, blending_height=4.0)
    with pytest.raises(ValueError, match="ground_roughness"):
        replace(base, inflow="log", ground_roughness=0.05)
    with pytest.raises(ValueError, match="city"):
        replace(base, city="blocky")


def test_sensitivity_variants_change_one_setting():
    base = {s.key for s in campaigns.baseline()}
    for name, specs in campaigns.sensitivity_variants():
        assert specs and not base & {s.key for s in specs}, name
    cases = {name: {s.case for s in specs} for name, specs in campaigns.sensitivity_variants()}
    assert cases["slabs filled to the ground"] == {"E"} and cases["padding 100 m"] == {"D"}


def test_tuning_candidates_are_valid_single_changes():
    labels = [label for label, _ in campaigns.tuning_candidates({})]
    assert len(labels) == 22 and "no canopy" not in labels and "wake=2" not in labels
    off = dict(parameterizations=dict(wake=0, rooftop=0, street_canyon=0, sidewall=0), canopy=(0.1, 6.0))
    candidates = dict(campaigns.tuning_candidates(off))
    assert "rooftop=1" not in candidates and "wake=1" in candidates and "no canopy" in candidates
    assert "canopy" not in candidates["no canopy"]


def test_choose_and_accept():
    rows = [dict(label=n, objective=dict(q=q, rho=r)) for n, q, r in (("a", 0.30, 0.40), ("b", 0.295, 0.50),
                                                                       ("c", 0.25, 0.90))]
    assert sensitivity.choose(rows)["label"] == "b"  # within 0.01 of the best q, higher rho
    assert sensitivity.accepted(dict(q=0.285), rows[1]) and not sensitivity.accepted(dict(q=0.29), rows[1])


def _records(case, state, labels, ids, values, xyz):
    out = {}
    for d, label in enumerate(labels):
        probes = dict(ids=ids.tolist(), K=values[:, d].tolist(), K_min=(values[:, d] - 0.1).tolist(),
                      K_max=(values[:, d] + 0.1).tolist(), wall_distance=[3.0] * len(ids), xyz=xyz.tolist())
        out[(case, state, label)] = dict(key=f"{case}{state}{d}", spec=dict(case=case), probes=probes)
    return out


def test_objective_and_neighbourhood_on_a_perfect_model():
    m = tables.load_results_e("before")
    records = _records("E", "before", m.labels, m.ids, m.values, m.xyz)
    assert sensitivity.objective(records)["q"] == 1.0 and sensitivity.objective(records)["directions"] == 16
    shifted = _records("E", "before", m.labels, m.ids, m.values + 0.08, m.xyz)
    comparison = compare.case_e_comparisons(shifted, ("K",))[0]
    assert comparison.scores()["hit_rate"] < 1.0
    assert sensitivity.neighbourhood_best(comparison, shifted).scores()["hit_rate"] == 1.0  # 0.08 < 0.1 span


def test_nearest_reads_the_stored_plane(tmp_path):
    x, y = np.array([0.5, 1.5, 2.5]), np.array([0.5, 1.5])
    velocity = np.zeros((2, 3, 3), np.float32)
    velocity[1, 2] = (3.0, 4.0, 0.0)
    (tmp_path / "E").mkdir()
    np.savez(tmp_path / "E" / "r.npz", x=x, y=y, velocity=velocity, valid=np.ones((2, 3), bool),
             reference_speed=np.float64(10.0))
    record = dict(key="r", spec=dict(case="E"), probes=dict(K=[0.0], xyz=[[2.2, 1.9, 2.0]]))
    assert sensitivity.nearest({("E", "before", "N"): record}, tmp_path)[("E", "before", "N")]["probes"]["K"] == [0.5]
    assert record["probes"]["K"] == [0.0]  # the source record is unchanged


def test_fill_slabs():
    city = case_e.build_case_e("before").city
    filled = cityutil.fill_slabs(city)
    slabs = cityutil.elevated_footprints(city)
    assert len(filled.buildings) == len(city.buildings) + len(slabs) == len(city.buildings) + 32
    assert not cityutil.city_objects(filled) and len(cityutil.city_objects(city)) == 32
    heights = {b.id: b.measured_height for b in filled.buildings}
    assert all(heights[f"{id_}-filled"] == zmax for id_, _, _, zmax in slabs)


def test_upstream_turbulence_takes_cells_upwind_of_every_building(tmp_path):
    from shapely.geometry import box
    x = y = np.arange(0.5, 100.0, 1.0)
    gx, gy = np.meshgrid(x, y)
    k = np.where(gx < 60, 2.0, 50.0).astype(np.float32)  # k = 2 upwind of the block
    (tmp_path / "E").mkdir()
    np.savez(tmp_path / "E" / "r.npz", x=x, y=y, velocity=np.zeros((100, 100, 3), np.float32),
             valid=np.ones((100, 100), bool), reference_speed=np.float64(2.0), k=k)
    record = dict(key="r", spec=dict(case="E", direction=270.0), probes={})  # wind from the west
    out = sensitivity.upstream_turbulence({("E", "before", "W"): record}, tmp_path, [box(60, 40, 70, 60)],
                                          tables.load_inflow_e())
    distance = np.hypot(np.maximum.reduce([60 - gx, 0 * gx, gx - 70]), np.maximum.reduce([40 - gy, 0 * gy, gy - 60]))
    assert out["median"] == 0.5 and out["cells"] == int(((gx < 60) & (distance >= 25)).sum())
    assert out["table"] == pytest.approx(0.0331, abs=5e-4)
