"""Final inflow API and fixed/computed-top domain contracts."""
import inspect
import json

import numpy as np
import pytest
from dtcc_core.model import City

from dtcc_qes import _qes, wind
from dtcc_qes.datasets import QESWindArgs, _LogPayload, _UniformPayload, _PowerPayload, _MeasuredPayload
from city_cases import city_case
from fixtures.cases import ONE_BUILDING


@pytest.mark.parametrize("operation", [wind.run, wind.preview_grid])
def test_final_entry_point_signatures_and_removed_arguments(operation, monkeypatch):
    parameters = inspect.signature(operation).parameters
    assert list(parameters)[:2] == ["city", "profile"]
    assert parameters["profile"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["speed"].kind == parameters["direction"].kind == inspect.Parameter.KEYWORD_ONLY
    assert parameters["turbulence"].default is None
    assert "reference_height" not in parameters and "roughness_length" not in parameters
    if operation is wind.preview_grid:
        assert "solver" not in parameters  # Native eligibility arrives in Phase 9.
    monkeypatch.setattr(wind,"extract_city",lambda *a,**kw:pytest.fail("extracted geometry"))
    for removed in ("reference_height","roughness_length"):
        with pytest.raises(TypeError,match=removed):
            operation(None, **{removed:10.})
    with pytest.raises(TypeError):
        operation(None,5,270)
    with pytest.raises(ValueError,match="mutually exclusive"):
        operation(None,wind.LogProfile(5,270),speed=5)
    for value in (True,False,np.bool_(True)):
        with pytest.raises(ValueError,match="boolean shorthand was removed"):
            operation(None,wind.LogProfile(5,270),turbulence=value)


@pytest.mark.parametrize("speed,direction", [(5,270),(4.321987654,359.9999999),(0,33)])
def test_shorthand_and_positional_profile_have_identical_fields_and_profile_records(speed,direction):
    city,_,grid,_=city_case(ONE_BUILDING)
    direct=wind.run(city,speed=speed,direction=direction,**grid)
    explicit=wind.run(city,wind.LogProfile(speed,direction),**grid)
    for name in ("velocity","cell_flags","x","y","z","z_faces"):
        assert getattr(direct,name).tobytes() == getattr(explicit,name).tobytes()
    assert direct.metadata["profile"] == explicit.metadata["profile"]
    assert direct.metadata["profile"]["kind"] == "log"
    assert direct.metadata["profile"]["caveats"] == []
    assert "type" not in direct.metadata["profile"]


def test_grid_only_preview_records_unknown_inflow_without_allocating_fields(monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("allocated native fields"))
    options=dict(bounds=(0,0,100,24,24,None),resolution=2)
    unknown=wind.preview_grid(City(),**options)
    known=wind.preview_grid(City(),wind.LogProfile(1,0),**options)
    assert unknown.domain["profile"] is None and unknown.domain["inflow"] == "unknown"
    for name in ("x","y","z","z_faces","solver_dz"):
        np.testing.assert_array_equal(getattr(unknown,name),getattr(known,name))
    assert unknown.origin[2] == 100
    json.dumps(unknown.domain,allow_nan=False)


@pytest.mark.parametrize("grid", [None,wind.VerticalGrid.auto(),wind.VerticalGrid.auto(fine_region_height=40)])
@pytest.mark.parametrize("footprints", [None,wind.Footprints(min_detail=.01)])
def test_computed_top_matches_automatic_generate_then_extend(grid,footprints,monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("allocated native fields"))
    city,condition,_,_=city_case(ONE_BUILDING,(3000,5000,100))
    options=dict(vertical_grid=grid,turbulence=wind.Turbulence(),footprints=footprints)
    automatic=wind.preview_grid(city,**condition,**options)
    bounds=automatic.domain["effective_bounds"]
    computed=wind.preview_grid(city,**condition,**options,bounds=(*bounds[:5],None))
    for name in ("x","y","z","z_faces","solver_dz"):
        np.testing.assert_array_equal(getattr(automatic,name),getattr(computed,name))
    assert computed.origin == automatic.origin
    assert computed.domain["turbulence"] == automatic.domain["turbulence"]
    assert computed.domain["vertical_grid"] == automatic.domain["vertical_grid"]
    assert computed.domain["requested_bounds"][-1] is None
    assert computed.domain["turbulence"]["extension_policy"] != "check_only"
    if grid is not None and grid._automatic.fine_region_height == 40:
        assert computed.domain["turbulence"]["extension_policy"] == "regenerated_then_constant_last_thickness"
    json.dumps(computed.domain,allow_nan=False)


@pytest.mark.parametrize("grid", [None,wind.VerticalGrid.auto()])
def test_computed_top_without_turbulence_and_fixed_top_result_parity(grid):
    city,condition,_,_=city_case(ONE_BUILDING)
    automatic=wind.preview_grid(city,**condition,vertical_grid=grid)
    bounds=automatic.domain["effective_bounds"]
    computed=wind.run(city,**condition,bounds=(*bounds[:5],None),vertical_grid=grid)
    requested_top=automatic.domain["vertical_grid"].get("endpoint_fit",{}).get("requested_top",bounds[5]-bounds[2])
    fixed=wind.run(city,**condition,bounds=(*bounds[:5],bounds[2]+requested_top),vertical_grid=grid)
    for name in ("velocity","cell_flags","x","y","z","z_faces"):
        np.testing.assert_array_equal(getattr(computed,name),getattr(fixed,name))


def test_numeric_tops_and_explicit_faces_stay_fixed():
    city,condition,_,_=city_case(ONE_BUILDING)
    insufficient=(0,0,0,80,80,20)
    with pytest.raises(ValueError,match="Turbulence domain top"):
        wind.preview_grid(city,**condition,bounds=insufficient,turbulence=wind.Turbulence())
    with pytest.raises(ValueError,match="Turbulence domain top"):
        wind.preview_grid(city,**condition,bounds=(*insufficient[:5],None),turbulence=wind.Turbulence(),
                          vertical_grid=wind.VerticalGrid.from_faces(np.arange(0,30,2)))
    for bounds,grid in [((0,0,0,80,80,64),None),
                         ((0,0,0,80,80,None),wind.VerticalGrid.from_faces(np.arange(0,66,2)))]:
        preview=wind.preview_grid(city,**condition,bounds=bounds,vertical_grid=grid,turbulence=wind.Turbulence())
        assert preview.domain["turbulence"]["extension_policy"] == "check_only"
        assert preview.z_faces[-1] == 64


@pytest.mark.parametrize("bounds", [(None,0,0,24,24,None),(0,0,None,24,24,None),
    (0,0,0,None,24,None),(0,0,0,24,np.inf,None),(0,0,0,24,24,np.nan),
    (0,0,0,0,24,None),(0,0,0,24,24,False),(0,0,0,24,24,-1)])
def test_invalid_computed_bounds_fail_before_flow_allocation(bounds,monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("allocated native fields"))
    with pytest.raises(ValueError):
        wind.run(City(),speed=5,direction=270,bounds=bounds)


@pytest.mark.parametrize("profile,payload", [(wind.LogProfile,_LogPayload),(wind.UniformProfile,_UniformPayload),
    (wind.PowerLawProfile,_PowerPayload),(wind.MeasuredProfile,_MeasuredPayload)])
def test_dataset_profile_payloads_match_constructor_fields(profile,payload):
    assert set(payload.__annotations__) - {"schema_version","kind"} == set(inspect.signature(profile).parameters)


def test_dataset_uses_new_inflow_names_and_rejects_removed_inputs_before_fetch(monkeypatch):
    from dtcc_core import datasets
    monkeypatch.setattr(datasets,"city",lambda **kw:pytest.fail("fetched invalid request"))
    shorthand=QESWindArgs(bounds=[0,0,24,24],speed=3.,direction=225.)
    assert shorthand.wind_options()["speed"] == 3.
    assert shorthand.reference_condition() == wind.LogProfile(3.,225.).reference
    explicit=QESWindArgs(bounds=[0,0,24,24],profile=wind.LogProfile(3.,225.,reference_height=15,roughness_length=.5).to_dict())
    assert not {"speed","direction"}.intersection(explicit.model_dump())
    assert explicit.wind_options()["profile"].roughness_length == .5
    for removed in ("wind_speed","wind_direction","reference_height","roughness_length"):
        with pytest.raises(ValueError,match="Extra inputs"):
            datasets.qes_wind(bounds=[0,0,24,24],**{removed:5.})
    with pytest.raises(ValueError,match="conflicts"):
        QESWindArgs(bounds=[0,0,24,24],profile=wind.LogProfile(5,270).to_dict(),speed=5.)
