"""Profile reference evaluator, owned native tables and public integration."""
from dataclasses import FrozenInstanceError, asdict
import json
import numpy as np
import pytest
from dtcc_qes import wind, _qes, comfort
from dtcc_qes.profiles import profile_from_dict, evaluate, _layer_record
from dtcc_qes.datasets import QESWindArgs, QESWindDataset, _field_slice
from city_cases import city_case
from fixtures.cases import FLAT, ONE_BUILDING
from runner_cases import prepared

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("profile", [wind.LogProfile(0,270), wind.UniformProfile(0,270)])
def test_adaptive_calm_profile_uses_evaluated_reference_before_geometry(profile):
    control=wind.SolverControl(1,wind.MonitorSpec((0,24,0,24)),mode="adaptive")
    with pytest.raises(ValueError,match="calm"):
        wind.run(None,profile=profile,solver_control=control)
    with pytest.raises(ValueError,match="calm"):
        QESWindArgs(bounds=[0,0,24,24],profile=profile.to_dict(),
                    solver_control=asdict(control))


def measured(**kwargs):
    return wind.MeasuredProfile([2,5,10,20,40],[2,4,5,3,7],direction=270,reference_height=10,below="log",**kwargs)


@pytest.mark.parametrize("mode,midpoint", [("log_height",6.),("linear", 4+8/3/2)])
def test_interpolation_knots_midpoints_and_skipped_intervals(mode,midpoint):
    p=wind.MeasuredProfile.from_components([1,2,3,10,40],[1,3,2,4,8],[0,0,0,0,0],
                                         reference_height=10,interpolation=mode)
    np.testing.assert_allclose(p.evaluate([1,2,3,10,40,80])[:,0],[1,3,2,4,8,8])
    assert p.evaluate(20)[0] == pytest.approx(midpoint)
    u,v=evaluate(p,[10,20,40],.1)
    np.testing.assert_array_equal(u,p.evaluate([10,20,40])[:,0])
    np.testing.assert_array_equal(v,0)


def test_wrap_reversals_calm_nonmonotonic_and_log_tail():
    p=wind.MeasuredProfile.from_directions([1,4],[5,5],[350,10],reference_height=2)
    np.testing.assert_allclose(p.evaluate(2),[0,-5*np.cos(np.deg2rad(10))],atol=1e-14)
    assert p.reference["speed"]<5
    reverse=wind.MeasuredProfile.from_components([1,3],[5,-5],[0,0],reference_height=2,interpolation="linear")
    assert reverse.reference == dict(height=2,u=0,v=0,speed=0,direction=None)
    p=wind.MeasuredProfile.from_components([2,10],[2,6],[-1,-3],reference_height=10,below="log")
    for rough in (.1,.5):
        factor=np.log1p(1/rough)/np.log1p(2/rough)
        np.testing.assert_allclose(p.evaluate([0,1,2],rough),[[0,0],[2*factor,-factor],[2,-1]])
    calm=wind.MeasuredProfile([2,10],[0,5],direction=270,reference_height=10,below="log")
    np.testing.assert_array_equal(calm.evaluate([0,1]),0)


def test_immutable_inputs_serialization_and_scaling():
    heights,u,v,metadata=[2,10],[2,5],[0,0],{"source":"mast","location":[1,2]}
    p=wind.MeasuredProfile.from_components(heights,u,v,reference_height=10,below="log",metadata=metadata)
    heights[0],u[0],metadata["location"][0]=1,100,99
    assert p.heights==(2,10) and p.u==(2,5) and p.metadata["location"]==(1,2)
    with pytest.raises(FrozenInstanceError): p.reference_height=2
    with pytest.raises(TypeError): p.metadata["source"]="changed"
    assert profile_from_dict(json.loads(json.dumps(p.to_dict()))).to_dict()==p.to_dict()
    np.testing.assert_allclose(p.scaled(3).evaluate([1,5,10]),p.evaluate([1,5,10])*3)
    for factor in (0,-1,np.nan,np.inf,True):
        with pytest.raises(ValueError): p.scaled(factor)


@pytest.mark.parametrize("args",[
    dict(heights=[1],speeds=[1],direction=0), dict(heights=[0,2],speeds=[1,2],direction=0),
    dict(heights=[2,1],speeds=[1,2],direction=0), dict(heights=[1,1],speeds=[1,2],direction=0),
    dict(heights=[1,2],speeds=[1,-2],direction=0), dict(heights=[1,2],speeds=[1],direction=0),
    dict(heights=[1,2],speeds=[1,2]),dict(heights=[1,2],speeds=[1,2],direction=0,directions=[0,1]),
    dict(heights=[1,2],speeds=[1,2],directions=[0]),dict(heights=[1,2],speeds=[1,2],direction=360),
    dict(heights=[1,2],u=[1,2],v=[0]),dict(heights=[1,2],u=[1,np.nan],v=[0,0]),
    dict(heights=[1,2],speeds=[1,2],direction=0,u=[1,2],v=[0,0]),
    dict(heights=[1,2],u=[1,2],v=[0,0],below="linear_to_zero"),
    dict(heights=[1,2],u=[1,2],v=[0,0],above="linear"),
    dict(heights=[1,2],u=[1,2],v=[0,0],interpolation="cubic"),
])
def test_bad_measured_input(args):
    with pytest.raises(ValueError): wind.MeasuredProfile(reference_height=1,**args)


def test_reference_validation_and_power_law_ground():
    for height in (0,-1,np.nan,1e40,1e-50,.5):
        with pytest.raises(ValueError): wind.MeasuredProfile([1,2],[1,2],direction=0,reference_height=height)
    for exponent in (0,-1,np.nan,np.inf,True):
        with pytest.raises(ValueError): wind.PowerLawProfile(5,270,10,exponent)
    p=wind.PowerLawProfile(5,270,10,.25)
    np.testing.assert_allclose(p.evaluate([0,10,160])[:,0],[0,5,10])
    with pytest.raises(ValueError): wind.LogProfile(5,270,1e-20,1)
    assert wind.UniformProfile(5,270,1e-20).reference["speed"]==5
    # Knots stay float64: native code sees only the evaluated physical layers.
    wind.MeasuredProfile([1,1+1e-9],[1,2],direction=0,reference_height=1)


@pytest.mark.parametrize("p",[wind.UniformProfile(5,30),wind.PowerLawProfile(5,30,10,.22),measured(),
    wind.MeasuredProfile([1,3,10,40],[5,2,4,7],directions=[350,10,30,50],reference_height=10,below="log")])
@pytest.mark.parametrize("nonuniform",[False,True])
@pytest.mark.parametrize("precision",["float32","float64"])
def test_empty_fields_match_reference_zero_divergence_and_grid(p,nonuniform,precision):
    city,_,grid,_=city_case(FLAT)
    if nonuniform: grid["vertical_grid"]=wind.VerticalGrid.from_faces([0,.5,1,2,4,8,14,24,40])
    result=wind.run(city,profile=p,**grid,solver_precision=precision)
    expected=np.zeros_like(result.velocity)
    expected[...,:2]=p.evaluate(result.z)[:,None,None,:]
    np.testing.assert_array_equal(result.velocity,expected)
    assert result.diagnostics.max_divergence==0 and result.diagnostics.top_band_max_divergence==0
    preview=wind.preview_grid(city,profile=p,**grid)
    np.testing.assert_array_equal(preview.z,result.z)
    assert preview.domain["profile"]==result.metadata["profile"]
    json.dumps(result.metadata,allow_nan=False)


@pytest.mark.parametrize("direction",[0.,33.123456789,359.9999999])
def test_explicit_log_bitwise_legacy(direction):
    city,_,grid,_=city_case(ONE_BUILDING)
    p=wind.LogProfile(4.321987654,direction,11.12345678,.123456789)
    actual=wind.run(city,profile=p,**grid)
    expected=wind.run(city,p.speed,p.direction,reference_height=p.reference_height,roughness_length=p.roughness_length,**grid)
    np.testing.assert_array_equal(actual.velocity,expected.velocity)


@pytest.mark.parametrize("kw",[dict(speed=5),dict(direction=270),dict(reference_height=10)])
def test_mixed_arguments(kw):
    city,_,grid,_=city_case(FLAT)
    with pytest.raises(ValueError,match="mutually exclusive"): wind.run(city,profile=measured(),**kw,**grid)
    with pytest.raises(ValueError,match="roughness_length"):
        wind.run(city,profile=wind.LogProfile(5,270),roughness_length=.1,**grid)


def test_tail_counts_coverage_before_native_and_roughness(monkeypatch):
    city,_,grid,_=city_case(FLAT)
    p=wind.MeasuredProfile([2,10],[2,5],direction=270,reference_height=10)
    with pytest.raises(ValueError,match="coverage"): wind.preview_grid(city,profile=p,**grid)
    p=wind.MeasuredProfile([2,10],[2,5],direction=270,reference_height=10,below="log")
    result=wind.run(city,profile=p,roughness_length=.5,**grid)
    assert result.metadata["profile"]["tail_layers"]==dict(below=1,above=15)
    assert result.metadata["condition"]["roughness_length"]==.5
    np.testing.assert_allclose(result.velocity[0,5,5,:2],p.evaluate(1,.5),atol=1e-7)
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("Allocated before coverage validation"))
    p=wind.MeasuredProfile([1,38],[1,5],direction=270,reference_height=10,above="error")
    with pytest.raises(ValueError,match="coverage"): wind.run(city,profile=p,**grid)
    # Last centre, not the domain top face, controls measured coverage.
    p=wind.MeasuredProfile([1,39],[1,5],direction=270,reference_height=10,above="error")
    wind.preview_grid(city,profile=p,**grid)


@pytest.mark.parametrize("p",[wind.UniformProfile(5,270),wind.PowerLawProfile(5,270,10,.22),measured(),
    wind.MeasuredProfile([1,10,40],[3,5,7],directions=[180,270,330],reference_height=10)])
@pytest.mark.parametrize("mixing_length", ["height", "wall_distance"])
def test_turbulence_and_turning_buildings_supported(p,mixing_length,caplog):
    city,_,grid,_=city_case(ONE_BUILDING)
    result=wind.run(city,profile=p,turbulence=wind.Turbulence(mixing_length=mixing_length),**grid)
    assert result.turbulence is not None and np.isfinite(result.velocity).all()
    assert "morphometric" in result.metadata["profile"]["turbulence_caveat"]
    assert "morphometric" in result.metadata["turbulence"]["profile_caveat"]
    if result.metadata["profile"]["max_turning_deg"]>45:
        assert "roof-level" in caplog.text


def test_calm_at_roof_and_zero_reference():
    city,_,grid,_=city_case(ONE_BUILDING)
    p=wind.MeasuredProfile([1,12,40],[0,0,5],direction=270,reference_height=10)
    result=wind.run(city,profile=p,**grid)
    assert result.reference_speed==0 and np.isfinite(result.velocity).all()
    assert result.metadata["profile"]["reference"]["direction"] is None
    assert np.isnan(result.speedup).all()
    args=QESWindArgs(bounds=list(grid["bounds"]),profile=p.to_dict(),product="slice")
    assert np.isnan(_field_slice(result,args).field("speedup").values).all()
    with pytest.raises(ValueError,match="positive"): comfort.assess([1],[270],[[[1]]],[270],0)


@pytest.mark.parametrize("case",[FLAT,ONE_BUILDING])
def test_native_tables_atomic_owned_and_repeated(case):
    runner,legacy,options=prepared(case)
    original=runner.solve(legacy,options)
    for p in (measured(),wind.UniformProfile(3,30),wind.PowerLawProfile(5,270,10,.3)):
        condition,_=wind._resolve_condition(None,None,wind._UNSET,wind._UNSET,p)
        native=wind._native_condition(condition,_layer_record(p,original["z"],condition["roughness_length"]))
        fresh,_,_=prepared(case)
        expected=fresh.solve(native,options)
        np.testing.assert_array_equal(runner.solve(native,options)["velocity"],expected["velocity"])
        for name,value in (("layer_u",[1,2]),("layer_v",[np.inf]*len(original["z"]))):
            bad=wind._native_condition(condition,_layer_record(p,original["z"],condition["roughness_length"]))
            setattr(bad,name,value)
            with pytest.raises(ValueError): runner.solve(bad,options)
        np.testing.assert_array_equal(runner.solve(native,options)["velocity"],expected["velocity"])
    np.testing.assert_array_equal(runner.solve(legacy,options)["velocity"],original["velocity"])


def test_native_exact_layers_reference_and_python_ownership():
    runner,_,options=prepared(FLAT)
    condition=_qes.WindCondition(); condition.profile_kind=_qes.ProfileKind.layer_table
    u=[2.]*20; condition.layer_u=u; condition.layer_v=[2.]*20; condition.speed=np.sqrt(8)
    u[0]=99; assert condition.layer_u[0]==2
    control=wind.SolverControl(10,wind.MonitorSpec(region=(4,76,4,56)))
    result=runner.solve(condition,options,control=control._native((0,0,0),None))
    assert result["control"]["monitor"]["reference_speed"]==condition.speed
    np.testing.assert_array_equal(result["velocity"][...,:2],2)


def test_building_scaling_and_legacy_log_table():
    city,cond,grid,_=city_case(ONE_BUILDING)
    p=measured(); base=wind.run(city,profile=p,**grid)
    scaled=wind.run(city,profile=p.scaled(2.5),**grid)
    np.testing.assert_allclose(scaled.velocity/2.5,base.velocity,atol=2e-5)
    log=wind.LogProfile(**cond); legacy=wind.run(city,**cond,**grid)
    table=wind.MeasuredProfile.from_components(legacy.z,*log.evaluate(legacy.z).T,reference_height=10,interpolation="linear")
    table_result=wind.run(city,profile=table,**grid)
    np.testing.assert_allclose(table_result.velocity,legacy.velocity,atol=1e-5)


def test_dataset_roundtrip_conflicts_identity_and_invalid_before_fetch(monkeypatch):
    payload=measured().to_dict(); args=QESWindArgs(bounds=[0,0,80,60],profile=payload,roughness_length=.5)
    assert QESWindArgs.model_validate_json(args.model_dump_json()).profile==args.profile
    assert "wind_speed" not in args.model_dump() and args.wind_options()["roughness_length"]==.5
    for key,value in (("wind_speed",5.),("wind_direction",270.),("reference_height",10.)):
        with pytest.raises(ValueError,match="conflicts"): QESWindArgs(bounds=[0,0,80,60],profile=payload,**{key:value})
    from dtcc_core import datasets
    monkeypatch.setattr(datasets,"city",lambda **kw:pytest.fail("Fetched invalid profile"))
    with pytest.raises(ValueError): QESWindDataset()(bounds=[0,0,80,60],profile={"kind":"measured","heights":[1],"u":[1],"v":[0],"reference_height":1})
    other=QESWindArgs(bounds=[0,0,80,60],profile=measured(interpolation="linear").to_dict())
    assert args.model_dump()!=other.model_dump()


def test_dataset_direct_and_speedup_export_agree(monkeypatch):
    from dtcc_core import datasets
    from dtcc_core.model import City,Transform
    city=City(transform=Transform(srs="EPSG:3006")); monkeypatch.setattr(datasets,"city",lambda **kw:city)
    p=measured();args=QESWindArgs(bounds=[0,0,0,80,60,40],horizontal_padding=0.,product="slice",profile=p.to_dict(),roughness_length=.5)
    from dtcc_qes._dataset_city import prepare_city
    canonical,bounds,_=prepare_city(city,args)
    direct=wind.run(canonical,**args.wind_options(),bounds=bounds,terrain=0,height_policy="allow_estimated")
    ds=QESWindDataset().build(args);expected=_field_slice(direct,args)
    for name in ("velocity","speed","speedup"): np.testing.assert_array_equal(ds.field(name).values,expected.field(name).values)
    field=next(f for f in direct.to_dtcc(include_speedup=True).fields if f.name=="speedup")
    np.testing.assert_array_equal(field.values,direct.speedup.transpose(1,2,0).reshape(-1))


@pytest.mark.parametrize("height", [10., 100., 1e10])
def test_log_interpolation_preserves_neighbouring_float64_knots(height):
    heights = [height, np.nextafter(height, np.inf)]
    profile = wind.MeasuredProfile.from_components(heights, [1, 2], [0, 0], reference_height=height)
    np.testing.assert_array_equal(profile.evaluate(heights)[:, 0], [1, 2])
    assert profile.reference["speed"] == 1


def test_extreme_log_height_span_uses_finite_physical_brackets():
    profile = wind.MeasuredProfile.from_components([1e-300, 1e300], [1, 2], [0, 0], reference_height=10)
    expected = 1 + (np.log(10.) - np.log(1e-300)) / (np.log(1e300) - np.log(1e-300))
    assert profile.evaluate(10)[0] == pytest.approx(expected)
    np.testing.assert_array_equal(profile.evaluate(profile.heights)[:, 0], [1, 2])


@pytest.mark.parametrize("metadata", [[], 0, ""])
def test_measured_metadata_rejects_non_mappings(metadata):
    with pytest.raises(ValueError, match="mapping"):
        wind.MeasuredProfile([1, 2], [1, 2], direction=0, reference_height=1, metadata=metadata)


def test_requested_measurements_and_scaling_preserve_caller_provenance():
    metadata = {"measurements": {"source": "caller", "averaging_period": "10 minutes"}}
    profile = wind.MeasuredProfile([1, 2], [1, 2], direction=0, reference_height=1, metadata=metadata)
    requested = profile.to_dict()
    assert requested["metadata"] == metadata
    assert requested["speeds"] == [1, 2] and requested["direction"] == 0
    assert "u" not in requested and "v" not in requested
    scaled = profile.scaled(2)
    assert scaled.to_dict()["speeds"] == [2, 4]
    assert scaled.to_dict()["metadata"] == metadata
    assert profile_from_dict(requested).to_dict() == requested


def test_lower_tail_uses_actual_run_roughness_before_native_narrowing():
    profile = wind.MeasuredProfile([10, 20], [8e38, 8e38], direction=270,
                                  reference_height=1, below="log")
    city, _, _, _ = city_case(FLAT)
    preview = wind.preview_grid(city, profile=profile, roughness_length=1e6, resolution=.5,
                                bounds=(0, 0, 0, 4, 4, 2))
    record = preview.domain["profile"]
    assert record["reference"] == profile.reference_at(1e6)
    assert np.isfinite(record["layer_table"]["effective_u"]).all()
    assert max(record["layer_table"]["effective_u"]) < 2e38


@pytest.mark.parametrize("version", [True, 1.0, 2])
def test_dataset_schema_versions_are_strict(version):
    with pytest.raises(ValueError):
        QESWindArgs(bounds=[0, 0, 80, 60], profile={"kind": "uniform", "speed": 5,
                    "direction": 270, "schema_version": version})


def test_dataset_schema_exposes_all_four_profile_discriminators():
    options = QESWindArgs.model_json_schema()["properties"]["profile"]["anyOf"]
    schema = next(option for option in options if "discriminator" in option)
    assert schema["discriminator"]["propertyName"] == "kind"
    assert set(schema["discriminator"]["mapping"]) == {"log", "measured", "uniform", "power_law"}


@pytest.mark.parametrize("profile", [wind.UniformProfile(0, 0), wind.PowerLawProfile(0, 0, 10, 1e300),
    wind.MeasuredProfile([1, 2], [0, 0], direction=0, reference_height=1)])
def test_calm_vectors_have_positive_zero_roof_orientation(profile):
    vectors = profile.evaluate([1, 2, 40])
    np.testing.assert_array_equal(vectors, 0)
    assert not np.signbit(vectors).any()
    np.testing.assert_array_equal(np.arctan2(vectors[:, 1], vectors[:, 0]), 0)
    assert profile.reference["direction"] is None


def test_public_preparation_evaluates_one_physical_layer_table(monkeypatch):
    profile = measured()
    original = wind.MeasuredProfile._evaluate
    bulk_queries = []
    def counted(self, heights, roughness):
        if heights.ndim:
            bulk_queries.append(heights.copy())
        return original(self, heights, roughness)
    monkeypatch.setattr(wind.MeasuredProfile, "_evaluate", counted)
    city, _, grid, _ = city_case(FLAT)
    for operation in (wind.run, wind.preview_grid):
        bulk_queries.clear()
        result = operation(city, profile=profile, **grid)
        assert len(bulk_queries) == 1
        np.testing.assert_array_equal(bulk_queries[0], result.z)


def test_overflowing_layer_table_fails_before_native_preparation(monkeypatch):
    city, _, grid, _ = city_case(FLAT)
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Native allocation occurred"))
    with pytest.raises(ValueError, match="float32"):
        wind.run(city, profile=wind.UniformProfile(3e38, 270), **grid)
    with pytest.raises(ValueError, match="finite"):
        wind.run(city, profile=wind.PowerLawProfile(5, 270, 10, 1e300), **grid)


@pytest.mark.parametrize("profile", [wind.LogProfile(4.321987654, 270), wind.UniformProfile(4.321987654, 270),
                                     wind.PowerLawProfile(4.321987654, 270, 10, .22)])
def test_dataset_slice_uses_declared_reference_without_float32_rounding(profile):
    city, _, grid, _ = city_case(FLAT)
    result = wind.run(city, profile=profile, **grid)
    args = QESWindArgs(bounds=list(grid["bounds"]), profile=profile.to_dict(), product="slice")
    sliced = _field_slice(result, args)
    reference = sliced.metadata_payload["speedup_reference"]["speed"]
    assert reference == profile.speed == result.reference_speed
    np.testing.assert_array_equal(sliced.field("speedup").values, sliced.field("speed").values / reference)
