"""Inflow profiles built from the AIJ tables (plan: Inflow, Normalisation)."""

import numpy as np
import pytest
from dtcc_qes.profiles import LogProfile, MeasuredProfile, PowerLawProfile

from aij import inflow, tables


@pytest.fixture(scope="module", params=["D", "E"])
def data(request):
    return tables.load_inflow_d() if request.param == "D" else tables.load_inflow_e()


def test_measured_profile_reproduces_the_table(data):
    profile = inflow.measured_profile(data, 247.5)
    assert isinstance(profile, MeasuredProfile)
    assert (profile.below, profile.above, profile.interpolation) == ("log", "constant", "log_height")
    vectors = profile.evaluate(data.heights)
    np.testing.assert_allclose(np.hypot(*vectors.T), data.speeds, rtol=1e-12)
    np.testing.assert_allclose(vectors / np.hypot(*vectors.T)[:, None],
                               np.broadcast_to(-np.array([np.sin(np.radians(247.5)), np.cos(np.radians(247.5))]),
                                               vectors.shape), atol=1e-12)


def test_measured_tail_is_shifted_log(data):
    profile = inflow.measured_profile(data, 0.0)
    z0, z1 = profile.roughness_length, data.heights[0]
    z = np.array([0.25, 0.5, 1.0])
    expected = data.speeds[0] * np.log1p(z / z0) / np.log1p(z1 / z0)
    np.testing.assert_allclose(np.hypot(*profile.evaluate(z).T), expected, rtol=1e-12)
    # The wind-tunnel floor is aerodynamically almost smooth near the ground.
    assert profile.roughness_length < 1e-3


def test_reference_speeds():
    d, e = tables.load_inflow_d(), tables.load_inflow_e()
    # Case D: stated U_H = 6.65 m/s; the table interpolates to within 0.3 % of it.
    assert inflow.reference_speed(inflow.measured_profile(d, 270)) == pytest.approx(6.65, rel=3e-3)
    assert inflow.reference_speed(inflow.measured_profile(d, 270, interpolation="linear")) == pytest.approx(6.65, rel=3e-3)
    # Case E: U(15.9 m)/U_R is 0.509 in log height and 0.504 linearly; the quantisation implies 0.5045.
    assert inflow.reference_speed(inflow.measured_profile(e, 0)) / tables.U_R == pytest.approx(0.5094, abs=5e-4)
    assert inflow.reference_speed(inflow.measured_profile(e, 0, interpolation="linear")) / tables.U_R == pytest.approx(0.5037, abs=5e-4)


@pytest.mark.parametrize("kind", inflow.KINDS)
def test_profile_kinds_build(data, kind):
    options = dict(canopy_roughness=0.6, blending_height=36.0) if kind == "canopy" else {}
    profile = inflow.profile(data, kind, 90.0, **options)
    assert isinstance(profile, dict(measured=MeasuredProfile, power_law=PowerLawProfile, log=LogProfile,
                                    canopy=MeasuredProfile)[kind])
    assert profile.reference_height == data.reference["height"]
    assert profile.reference["direction"] == pytest.approx(90.0)
    assert inflow.reference_speed(profile) == pytest.approx(profile.reference["speed"], rel=1e-6)
    rotated = profile.with_direction(180.0)
    assert inflow.reference_speed(rotated) == pytest.approx(inflow.reference_speed(profile), rel=1e-6)


def test_fit_power_law_recovers_exponent():
    z = np.array([2.0, 5.0, 10.0, 40.0, 100.0])
    fit = inflow.fit_power_law(z, 6.0 * (z / 100.0) ** 0.22, 100.0)
    assert fit.exponent == pytest.approx(0.22, abs=1e-12) and fit.speed == pytest.approx(6.0, rel=1e-12)
    assert fit.rms < 1e-12


def test_fit_log_recovers_roughness():
    z = np.array([1.0, 2.0, 5.0, 10.0, 30.0, 80.0])
    fit = inflow.fit_log(z, 0.9 * np.log1p(z / 0.05))
    assert fit.roughness_length == pytest.approx(0.05, rel=1e-6)
    assert fit.amplitude == pytest.approx(0.9, rel=1e-6)


def test_fits_of_the_aij_profiles():
    d, e = tables.load_inflow_d(), tables.load_inflow_e()
    power_d = inflow.fit_power_law(d.heights, d.speeds, 100.0, inflow.FIT_HEIGHT["D"])
    power_e = inflow.fit_power_law(e.heights, e.speeds, 15.9, inflow.FIT_HEIGHT["E"])
    assert 0.1 < power_d.exponent < 0.25 and 0.1 < power_e.exponent < 0.3
    assert power_d.points == 9 and power_e.points == 9


def test_unknown_kind():
    with pytest.raises(ValueError):
        inflow.profile(tables.load_inflow_d(), "spline", 0.0)
