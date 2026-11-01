"""Dataset integration of experimental layers, physical-height sampling and identity."""
import numpy as np
import pytest
from dtcc_core import datasets
from dtcc_core.model import FieldSlice

from dtcc_qes import wind
from dtcc_qes.datasets import QESWindArgs, _field_slice
from dtcc_qes._dataset_city import prepare_city, _source_city
from dtcc_qes.profiles import _profile_record
from fixtures.datasets import fetched, realization, request, source_city

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def manufactured(flags=None):
    # Unequal horizontal axes and nonuniform z; opposite horizontal components
    # ensure that interpolating speed instead of components fails the test.
    z=np.array([.25,.75,1.5,2.5],dtype=np.float32)
    x=np.array([.5,1.5,2.5],dtype=np.float32)
    y=np.array([.5,1.5],dtype=np.float32)
    velocity=np.zeros((4,2,3,3),dtype=np.float32)
    velocity[...,0]=(4-4*z)[:,None,None]
    velocity[...,1]=(2*z)[:,None,None]
    return wind.WindResult(velocity,x,y,z,
        np.ones((4,2,3),dtype=np.int32) if flags is None else flags,
        (300000.,6400000.,100.),"EPSG:3006",1.,
        wind.SolveDiagnostics(5,0,1e-5,True),
        {"profile":_profile_record(wind.LogProfile(5,270),None),
         "domain":{"effective_bounds":(300000.,6400000.,100.,300003.,6400002.,103.),
                   "vertical_grid":{"mode":"auto","uniform":False,"policy_status":"prototype_unvalidated"}}},
        z_faces=np.array([0,.5,1,2,3],dtype=np.float32))


@pytest.mark.parametrize("height",[1.5,1.75])
def test_linear_slice_matches_components_at_physical_height(height):
    result=manufactured()
    args=QESWindArgs(**request(product="slice",vertical_grid="auto",slice_sampling="linear",
                              slice_height=height,slice_resolution=5))
    obj=_field_slice(result,args)
    assert isinstance(obj,FieldSlice)
    np.testing.assert_array_equal(obj.points[:,2],100+height)
    expected=np.tile([4-4*height,2*height,0],(25,1))
    np.testing.assert_allclose(obj.field("velocity").values,expected)
    np.testing.assert_allclose(obj.field("speed").values,np.linalg.norm(expected,axis=1))
    assert obj.field("valid").values.all()
    assert obj.metadata_payload["sampling"]=="vertical_linear_nearest_horizontal"
    assert obj.metadata_payload["requested_height"]==height
    assert obj.metadata_payload["sampled_height"]==height
    assert obj.metadata_payload["automatic_grid_experimental"]
    assert not np.shares_memory(obj.field("velocity").values,result.velocity)


def test_validity_depends_on_both_vertical_contributors_not_nearest_flags():
    flags=np.ones((4,2,3),dtype=np.int32)
    flags[2,0,0]=0
    result=manufactured(flags)
    obj=_field_slice(result,QESWindArgs(**request(product="slice",slice_sampling="linear",
                                                 slice_height=2.25,slice_resolution=3)))
    # The nearest (upper) cell is fluid, but the lower interpolation cell is solid.
    assert obj.field("cell_flags").values[0]==1
    assert not obj.field("valid").values[0]
    assert np.isnan(obj.field("velocity").values[0]).all()
    assert np.isnan(obj.field("speed").values[0])
    assert obj.field("valid").values[-1]


def test_exact_centre_does_not_require_solid_neighbor():
    flags=np.ones((4,2,3),dtype=np.int32); flags[3]=2
    obj=_field_slice(manufactured(flags),QESWindArgs(**request(
        product="slice",slice_sampling="linear",slice_height=1.5,slice_resolution=3)))
    assert obj.field("valid").values.all()


@pytest.mark.parametrize("height",[0.,3.])
def test_physical_height_outside_centre_support_has_invalid_samples(height):
    obj=_field_slice(manufactured(),QESWindArgs(**request(
        product="slice",slice_sampling="linear",slice_height=height,slice_resolution=3)))
    np.testing.assert_array_equal(obj.points[:,2],100+height)
    assert not obj.field("valid").values.any()
    assert np.isnan(obj.field("velocity").values).all()
    assert obj.metadata_payload["sampled_height"] is None
    assert obj.metadata_payload["slice_height"] is None


@pytest.mark.parametrize("axis",["x","y","z"])
def test_nearest_slices_mark_solids_and_nonfinite_vectors_invalid(axis):
    result=manufactured()
    result.cell_flags[0,0,0]=2
    result.velocity[-1,-1,-1]=np.nan
    args=QESWindArgs(**request(product="slice",slice_axis=axis,slice_position=0.,slice_resolution=3))
    obj=_field_slice(result,args)
    assert not obj.field("valid").values[0]
    assert np.isnan(obj.field("velocity").values[0]).all()
    assert obj.field("cell_flags").values[0]==2
    args=QESWindArgs(**request(product="slice",slice_axis=axis,slice_position=1.,slice_resolution=3))
    obj=_field_slice(result,args)
    assert not obj.field("valid").values[-1]
    assert np.isnan(obj.field("speed").values[-1])


@pytest.mark.parametrize("options",[
    {"vertical_grid":"auto","product":"field"},
    {"slice_sampling":"linear","product":"field"},
    {"slice_sampling":"linear","product":"slice","slice_axis":"x"},
    {"slice_sampling":"linear","product":"slice","slice_axis":"y"},
    {"vertical_grid":"invalid"},{"pedestrian_height":0.},{"pedestrian_height":np.inf},
    {"growth_rate":1.},{"growth_rate":1.21},{"growth_rate":np.nan},
    {"solver":{"schema_version":1,"precision":"double"}},{"slice_sampling":"cubic"},
])
def test_unsupported_requests_fail_before_fetch(fetched,options):
    with pytest.raises(ValueError):
        datasets.qes_wind(**(request()|options))
    assert not fetched


@pytest.mark.parametrize("axis",["x","y"])
def test_height_override_is_applied_before_linear_axis_validation(axis):
    args=QESWindArgs(**request(product="slice",slice_axis=axis,slice_height=1.75,slice_sampling="linear"))
    assert args.slice_axis=="z"


@pytest.mark.parametrize("options",[
    {"vertical_grid":"auto"},{"pedestrian_height":1.75},{"growth_rate":1.1},
    {"solver":wind.Solver(tolerance=1e-4, max_iterations=1000, precision="float64").to_dict()},{"slice_sampling":"linear"},
])
def test_new_options_participate_in_request_identity(options):
    base=QESWindArgs(**request(product="slice"))
    args=QESWindArgs(**(request(product="slice")|options))
    context=datasets.qes_wind.create_context(args)
    assert context.request.parameters==args.model_dump(mode="json")
    assert context.request.parameters!=datasets.qes_wind.create_context(base).request.parameters
    for name,value in options.items():
        assert context.request.parameters[name]==value


@pytest.mark.parametrize("height",[1.5,1.75])
def test_experimental_dataset_slice_matches_direct_solve_and_keeps_provenance(source_city,fetched,height):
    args=QESWindArgs(**request(product="slice",vertical_grid="auto",slice_sampling="linear",
                              slice_height=height,slice_resolution=5))
    _,bounds,_=prepare_city(source_city,args)
    direct=wind.run(_source_city(source_city, []), **args.wind_options(), bounds=bounds,
                    terrain=bounds[2], height_policy="allow_estimated",
                    footprints=wind.Footprints(min_detail=args.min_building_detail, fallback="tallest"))
    expected=_field_slice(direct,args)
    actual=datasets.qes_wind(**args.model_dump())
    for name in ("velocity","speed","speedup","cell_flags","valid"):
        np.testing.assert_array_equal(actual.field(name).values,expected.field(name).values)
    np.testing.assert_array_equal(actual.points,expected.points)
    health=actual.dataset_context.health
    assert health["automatic_grid_experimental"]
    assert health["precision"]=="float32"
    assert health["max_divergence"]==direct.diagnostics.max_divergence
    assert health["rms_divergence"]==direct.diagnostics.rms_divergence
    assert health["valid_samples"]+health["invalid_samples"]==25
    assert any("experimental" in message for message in actual.dataset_context.warnings)
    assert realization(actual)["simulation"]["domain"]["vertical_grid"]["policy_status"]=="prototype_unvalidated"
    assert realization(actual)["sampling"]==actual.metadata_payload
    assert len(fetched)==1


def test_float64_precision_and_tolerance_reach_solver(fetched):
    obj=datasets.qes_wind(**request(product="slice", solver=wind.Solver(precision="float64", tolerance=1e-10, max_iterations=1000).to_dict()))
    assert realization(obj)["diagnostics"]["precision"]=="float64"
    assert realization(obj)["diagnostics"]["tolerance"]==1e-10
    assert not obj.dataset_context.health["automatic_grid_experimental"]


def test_discovery_labels_auto_experimental_and_field_output_uniform():
    meta=datasets.qes_wind.describe()
    field,slice_product=meta["products"]
    assert field["vertical_grids"]==["uniform"]
    assert slice_product["experimental_vertical_grids"]==["auto"]
    assert "valid" in slice_product["field_names"]
