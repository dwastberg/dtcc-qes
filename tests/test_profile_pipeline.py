"""Canonical profiles and the one record shared by preparation and solving."""
from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest
from dtcc_core.model import City

from dtcc_qes import _qes, wind
from dtcc_qes.profiles import _profile_record
from city_cases import city_case
from fixtures.cases import ONE_BUILDING


PROFILES = [wind.LogProfile(5.123456789,359.9999999), wind.UniformProfile(5,270),
    wind.PowerLawProfile(5,270,10,.2),
    wind.MeasuredProfile([1,5,10,40,100],[2,4,5,6,7],directions=[350,10,30,40,50],
                         reference_height=10,below="log")]
GRIDS = [None, wind.VerticalGrid.from_faces([0,1,2,3,5,8,12,18,26,40,48,56,64]), wind.VerticalGrid.auto()]


@pytest.mark.parametrize("profile",PROFILES)
@pytest.mark.parametrize("grid",GRIDS)
@pytest.mark.parametrize("turbulence",[None,wind.Turbulence()])
def test_preview_and_run_share_identical_profile_records(profile,grid,turbulence):
    options=dict(bounds=(0,0,0,80,80,64),vertical_grid=grid,turbulence=turbulence)
    preview=wind.preview_grid(City(),profile,**options)
    result=wind.run(City(),profile,**options)
    record=preview.domain["profile"]
    assert record == result.metadata["domain"]["profile"] == result.metadata["profile"]
    assert result.metadata["domain"]["profile"] is result.metadata["profile"]
    assert result.metadata["model"]["boundary_layer"] == record["boundary_layer"]
    assert "condition" not in result.metadata and "effective_condition" not in result.metadata
    assert result.reference_speed == record["reference"]["speed"]
    assert record["experimental"] == (profile.kind != "log")
    if profile.kind == "log":
        assert record["interpolation"] == "analytic" and "layer_table" not in record
    else:
        np.testing.assert_array_equal(record["layer_table"]["heights"],result.z.astype(np.float64))
    json.dumps(result.metadata,allow_nan=False)


def test_resolver_returns_profile_or_none_without_placeholder_condition():
    assert wind._resolve_condition(None,None,None,allow_unknown=True) is None
    shorthand=wind._resolve_condition(5,270,None)
    assert shorthand == wind.LogProfile(5,270)
    for profile in PROFILES:
        assert wind._resolve_condition(None,None,profile) is profile
    assert not hasattr(wind,"_validate_condition")
    preview=wind.preview_grid(City(),bounds=(0,0,0,24,24,24))
    assert preview.domain["profile"] is None and preview.domain["inflow"] == "unknown"


@pytest.mark.parametrize("height,roughness",[(1e-20,.1),(1e38,1e-38),
    (float(np.finfo(np.float32).max),float(np.finfo(np.float32).max))])
def test_log_constructor_rejects_unrepresentable_native_ratios(height,roughness,monkeypatch):
    monkeypatch.setattr(wind,"extract_city",lambda *a,**kw:pytest.fail("extracted geometry"))
    with pytest.raises(ValueError,match="float32 log profile"):
        wind.LogProfile(5,270,reference_height=height,roughness_length=roughness)


def test_log_does_not_request_layer_heights_and_keeps_declared_monitor_speed(monkeypatch):
    monkeypatch.setattr(wind,"_layer_heights",lambda *a:pytest.fail("allocated log layer supports"))
    profile=wind.LogProfile(5.123456789,359.9999999)
    solver=wind.Solver(max_solve_seconds=60,monitor=wind.MonitorSpec((0,24,0,24)))
    result=wind.run(City(),profile,bounds=(0,0,0,24,24,24),solver=solver)
    record=result.metadata["profile"]
    native=wind._native_condition(record)
    assert native.profile_kind == _qes.ProfileKind.log
    assert native.layer_u == native.layer_v == []
    assert native.speed == result.reference_speed == result.solver["record"]["monitor"]["reference_speed"] == profile.speed
    assert native.speed != record["native_reference_scalars"]["speed"]
    assert native.direction == profile.direction
    calm=wind.LogProfile(0,33)
    assert wind._native_condition(_profile_record(calm,None)).direction == 33


def test_reference_speed_reads_only_profile_metadata():
    result=wind.run(City(),speed=5,direction=270,bounds=(0,0,0,24,24,24))
    metadata=deepcopy(result.metadata)
    metadata["condition"]={"speed":999}
    metadata["profile"]["reference"]["speed"]=7
    assert replace(result,metadata=metadata).reference_speed == 7
    metadata.pop("profile")
    assert replace(result,metadata=metadata).reference_speed is None


def test_canonical_footprints_resolve_record_after_final_grid_and_extend_once(monkeypatch):
    city,condition,_,_=city_case(ONE_BUILDING)
    profile=wind.MeasuredProfile([1,5,10,100],[2,4,5,6],direction=270,reference_height=10,below="log")
    called=[]
    builder=wind._profile_record
    def observed(p,heights):
        called.append(np.array(heights,copy=True))
        return builder(p,heights)
    monkeypatch.setattr(wind,"_profile_record",observed)
    result=wind.run(city,profile,vertical_grid=wind.VerticalGrid.auto(),turbulence=wind.Turbulence(),
                    footprints=wind.Footprints(min_detail=.01))
    assert len(called)==1
    np.testing.assert_array_equal(called[0],result.z)
    assert result.metadata["domain"]["profile"] == result.metadata["profile"]
