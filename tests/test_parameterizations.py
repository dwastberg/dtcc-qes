"""Building parameterization settings reach native preparation, metadata and eligibility."""
import json

import numpy as np
import pytest
from dtcc_qes import _qes, wind
from fixtures.geometry import tower_city
from fixtures.specs import pedestrian_solver
from fixtures.turbulence_domain import blocks

pytestmark = pytest.mark.usefixtures("dtcc_logger")
BOUNDS = (0, 0, 0, 160, 160, 64)
# A slender 40 m tower (H/L = 5) triggers the high-rise wake; 2 m cells resolve sidewall zones.
SLENDER = dict(speed=5, direction=270, bounds=BOUNDS, resolution=2, solver=wind.Solver(max_iterations=200))


def slender_city():
    return blocks((10, 10, 10, 40), width=8)


def test_defaults_are_the_native_and_qualified_settings():
    assert wind.Parameterizations._from_model(_qes.ModelSettings()) == wind.Parameterizations()
    assert wind.Parameterizations().to_dict() == dict(schema_version=1, rooftop=1, upwind_cavity=2, street_canyon=1,
                                                      wake=2, high_rise=0, sidewall=1, wall_roughness=0.001)


@pytest.mark.parametrize("changes,match", [
    (dict(rooftop=3), r"rooftop must be an integer in \[0, 2\]"),
    (dict(upwind_cavity=-1), "upwind_cavity"),
    (dict(street_canyon=2), "street_canyon"),
    (dict(high_rise=True), "high_rise"),
    (dict(sidewall=1.0), "sidewall"),
    (dict(wall_roughness=0), "wall_roughness must be positive"),
    (dict(wall_roughness=float("nan")), "wall_roughness"),
    (dict(wall_roughness=1e39), "finite in float32"),
    (dict(wake=0), "wake must be nonzero"),
])
def test_invalid_settings_are_rejected_on_construction(changes, match):
    with pytest.raises(ValueError, match=match):
        wind.Parameterizations(**changes)


def test_wake_may_be_off_with_its_dependent_models():
    spec = wind.Parameterizations(np.int64(0), 0, 0, 0, 0, 0)
    assert spec.wake == 0 and type(spec.rooftop) is int


def test_default_settings_leave_the_solve_unchanged():
    base = wind.run(slender_city(), **SLENDER)
    explicit = wind.run(slender_city(), **SLENDER, parameterizations=wind.Parameterizations())
    np.testing.assert_array_equal(base.velocity, explicit.velocity)
    assert base.metadata["model"]["parameterizations"] == wind.Parameterizations().to_dict()


@pytest.mark.parametrize("changes", [dict(high_rise=1), dict(wall_roughness=0.05), dict(sidewall=0),
                                     dict(street_canyon=0), dict(upwind_cavity=1), dict(wake=1),
                                     dict(rooftop=0, street_canyon=0, sidewall=0, wake=0, upwind_cavity=0)])
def test_each_setting_reaches_the_solver_and_is_recorded(changes):
    spec = wind.Parameterizations(**changes)
    base = wind.run(slender_city(), **SLENDER)
    result = wind.run(slender_city(), **SLENDER, parameterizations=spec)
    assert np.nanmax(np.abs(result.velocity - base.velocity)) > 0.1
    model = result.metadata["model"]
    assert wind.Parameterizations.from_dict(model["parameterizations"]) == spec
    assert model["high_rise_flag"] == spec.high_rise and model["wall_roughness"] == spec.wall_roughness
    json.dumps(result.metadata, allow_nan=False)


def test_non_default_settings_are_outside_pedestrian_policy(monkeypatch):
    options = dict(speed=5, direction=270, bounds=BOUNDS, solver=pedestrian_solver())
    default = wind.preview_grid(tower_city(), **options)
    assert "unqualified_model_settings" not in default.eligibility["exclusions"]
    for spec in (wind.Parameterizations(high_rise=1), wind.Parameterizations(wall_roughness=0.002)):
        preview = wind.preview_grid(tower_city(), **options, parameterizations=spec)
        assert "unqualified_model_settings" in preview.eligibility["exclusions"]
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("allocated native fields"))
    with pytest.raises(wind.UnacceptedResultError) as error:
        wind.run(tower_city(), **dict(options, solver=pedestrian_solver(raise_on_failure=True)),
                 parameterizations=wind.Parameterizations(high_rise=1))
    # An experimental native build is rejected at input preflight, before the
    # prepared-model check exercised above. It must not inherit qualification.
    expected = "unqualified_model_settings" if _qes.solver_policy_build_supported else "unqualified_build"
    assert expected in error.value.exclusions


@pytest.mark.parametrize("operation", [wind.run, wind.preview_grid])
def test_parameterizations_require_the_specification(operation):
    with pytest.raises(TypeError, match="parameterizations must be Parameterizations"):
        operation(tower_city(), speed=5, direction=270, bounds=BOUNDS, parameterizations=dict(high_rise=1))
