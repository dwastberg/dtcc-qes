"""Background diagnostics describe the selected profile without changing grids."""
import json
import math

import numpy as np
import pytest
from dtcc_core.model import City
from dtcc_qes import wind
from fixtures.turbulence_domain import blocks


def preview(profile=None,**kwargs):
    return wind.preview_grid(City(),profile,bounds=(0,0,0,24,24,24),
        vertical_grid=wind.VerticalGrid.auto(first_layer_thickness=.4),**kwargs)


def test_uniform_unknown_and_calm_diagnostics():
    uniform=preview(wind.UniformProfile(5,33)).domain["vertical_grid"]["pedestrian_sampling"]
    assert uniform["flat_profile_exact_K"]==uniform["flat_profile_interpolated_K"]==1.
    assert uniform["flat_profile_bias_K"]==uniform["vector_interpolation_error_mps"]==0.
    unknown=preview().domain["vertical_grid"]["pedestrian_sampling"]
    assert unknown["inflow"]=="unknown" and unknown["flat_profile_exact_K"] is None
    assert unknown["normalization_unavailable_reason"]=="unknown_inflow"
    # Calm at the reference need not imply calm at every sampled height.
    calm=wind.MeasuredProfile([1,2,10,100],[2,4,0,5],direction=270,reference_height=10,below="log")
    record=preview(calm).domain["vertical_grid"]["pedestrian_sampling"]
    assert record["normalization_unavailable_reason"]=="calm_reference"
    for key in ("flat_profile_exact_K","flat_profile_interpolated_K","flat_profile_bias_K",
                "vector_interpolation_error_over_reference"):
        assert record[key] is None
    assert record["vector_interpolation_error_mps"] is not None
    json.dumps(record,allow_nan=False)


def test_turning_profile_interpolates_components_before_speed():
    profile=wind.MeasuredProfile([1,2,10,100],[4,6,5,7],directions=[0,160,270,300],
                                 reference_height=10,below="log")
    planned=preview(profile)
    record=planned.domain["vertical_grid"]["pedestrian_sampling"]
    lo,hi=record["centre_indices"]
    weight=record["upper_weight"]
    vectors=profile.evaluate(planned.z[[lo,hi]].astype(float))
    interp=vectors[0]+(vectors[1]-vectors[0])*weight
    exact=profile.evaluate(record["height"])
    np.testing.assert_array_equal(record["interpolated_velocity_mps"],interp)
    assert record["flat_profile_interpolated_K"]==math.hypot(*interp)/5
    assert record["vector_interpolation_error_mps"]==math.hypot(*(interp-exact))
    assert record["vector_interpolation_error_over_reference"]==math.hypot(*(interp-exact))/5
    interpolated_speeds=math.hypot(*vectors[0])*(1-weight)+math.hypot(*vectors[1])*weight
    assert math.hypot(*interp)!=pytest.approx(interpolated_speeds,abs=1e-8)


def test_log_preserves_historical_scalar_operations_bitwise():
    profile=wind.LogProfile(5,33,reference_height=10.123456,roughness_length=.123456)
    record=preview(profile).domain["vertical_grid"]["pedestrian_sampling"]
    a,b=record["bracketing_centres"]; weight=record["upper_weight"]
    z0,ref=float(np.float32(profile.roughness_length)),float(np.float32(profile.reference_height))
    denominator=math.log1p(ref/z0)
    exact=math.log1p(record["height"]/z0)/denominator
    interpolated=(math.log1p(a/z0)*(1-weight)+math.log1p(b/z0)*weight)/denominator
    assert record["flat_profile_exact_K"].hex()==exact.hex()
    assert record["flat_profile_interpolated_K"].hex()==interpolated.hex()
    assert record["flat_profile_bias_K"].hex()==(interpolated-exact).hex()


def test_explicit_top_attributes_two_cells_without_imposing_uniform_spacing():
    planned=wind.preview_grid(City(),wind.UniformProfile(5,270),bounds=(0,0,0,24,24,.2),
        vertical_grid=wind.VerticalGrid.from_faces([0,.1,.2]))
    requirements=planned.domain["top_requirements"]
    assert requirements["requested_top"]==.2
    assert requirements["minimum_cells"]==dict(count=2,minimum_top=None,applied=True)
    assert not requirements["profile_reference"]["applied"]


@pytest.mark.parametrize("grid",[None,wind.VerticalGrid.auto()])
def test_top_attribution_and_growth_coverage_error(grid):
    city=blocks()
    options=dict(vertical_grid=grid)
    base=wind.preview_grid(city,**options)
    grown=wind.preview_grid(city,**options,turbulence=wind.Turbulence())
    req=grown.domain["top_requirements"]
    assert req["effective_top"]==float(grown.z_faces[-1])
    assert req["roof_clearance"]["minimum_top"]==35
    assert req["profile_reference"]["minimum_top"]==10
    assert req["minimum_cells"]==dict(count=2,minimum_top=4.,applied=True)
    assert req["turbulence_reference"]["reference_height"]==45
    assert req["turbulence_reference"]["effective_margin_face"]>=45
    assert req["turbulence_rotation_15m"]["minimum_top"]==15
    assert (req["auto_grid_endpoint_fit"] is not None)==(grid is not None)
    last=float(base.z[-1])
    profile=wind.MeasuredProfile([1,10,last],[2,5,6],direction=270,reference_height=10,below="log",above="error")
    wind.preview_grid(city,profile,**options)
    with pytest.raises(ValueError,match="turbulence domain growth.*top_requirements="):
        wind.preview_grid(city,profile,**options,turbulence=wind.Turbulence())
    short=wind.MeasuredProfile([1,10,12],[2,5,6],direction=270,reference_height=10,below="log",above="error")
    with pytest.raises(ValueError) as error:
        wind.preview_grid(city,short,**options,turbulence=wind.Turbulence())
    assert "top_requirements" not in str(error.value)


@pytest.mark.parametrize("last,attributed",[(40,True),(12,False)])
def test_regenerated_top_coverage_error_only_attributes_new_growth(last,attributed):
    profile=wind.MeasuredProfile([1,10,last],[2,5,6],direction=270,reference_height=10,
                                 below="log",above="error")
    with pytest.raises(ValueError) as error:
        wind.preview_grid(blocks(),profile,vertical_grid=wind.VerticalGrid.auto(fine_region_height=40),
                          turbulence=wind.Turbulence())
    assert ("top_requirements=" in str(error.value))==attributed
