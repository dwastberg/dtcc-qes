"""Dataset request identity and conditioned direct-run parity with turbulence."""
import json
from unittest.mock import patch

import numpy as np
import pytest
from dtcc_core import datasets
from dtcc_qes import wind
from dtcc_qes.datasets import QESWindArgs,_field_slice
from dtcc_qes._dataset_city import prepare_city,_source_city
from test_datasets import source_city,fetched,request,realization

pytestmark=pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("payload",[dict(schema_version=1),wind.Turbulence().to_dict(),
    wind.Turbulence("wall_distance").to_dict(),dict(schema_version=True),dict(schema_version=2),
    dict(schema_version=1,mixing_length="bad"),dict(schema_version=1,extra=True)])
def test_turbulence_schema_matches_spec_and_binds_identity(payload):
    try:
        spec=wind.Turbulence.from_dict(payload)
    except ValueError:
        with pytest.raises(ValueError):
            QESWindArgs(**request(turbulence=payload))
    else:
        args=QESWindArgs(**request(turbulence=payload))
        assert args.turbulence==spec.to_dict()
        assert args.model_dump(mode="json")["turbulence_numerics_version"]=="dtcc-qes-turbulence-v1"
        with pytest.raises(ValueError,match="numerics changed"):
            QESWindArgs(**request(turbulence=payload,turbulence_numerics_version="old"))


@pytest.mark.parametrize("axis,sampling",[("x","nearest"),("y","nearest"),("z","nearest"),("z","linear")])
@pytest.mark.parametrize("grid",["uniform","auto"])
def test_dataset_direct_turbulent_slice_parity(source_city,fetched,axis,sampling,grid):
    args=QESWindArgs(**request(product="slice",vertical_grid=grid,slice_axis=axis,slice_sampling=sampling,
        slice_resolution=7,turbulence=wind.Turbulence().to_dict(),
        profile=wind.UniformProfile(5,270).to_dict()))
    _,bounds,_=prepare_city(source_city,args)
    assert bounds[-1] is None
    direct=wind.run(_source_city(source_city,[]),**args.wind_options(),bounds=bounds,terrain=bounds[2],
        height_policy="allow_estimated",footprints=wind.Footprints(min_detail=args.min_building_detail,fallback="tallest"))
    actual=datasets.qes_wind(**args.model_dump(mode="json"))
    expected=_field_slice(direct,args)
    assert realization(actual)["qualification"]==direct.qualification
    dataset_domain=realization(actual)["simulation"]["domain"]
    # This hole-free fixture has identical solids; provenance still records
    # the dataset's explicit courtyard-fill policy versus direct preservation.
    assert dataset_domain["footprints"]["remove_holes"]
    assert not direct.metadata["domain"]["footprints"]["remove_holes"]
    assert {k:v for k,v in dataset_domain.items() if k!="footprints"} == {
        k:v for k,v in direct.metadata["domain"].items() if k!="footprints"}
    for name in ("velocity","speed","speedup","valid","cell_flags","streamwise_std","turbulence_intensity","stress_valid"):
        np.testing.assert_array_equal(actual.field(name).values,expected.field(name).values)
    assert actual.field("streamwise_std").unit=="m/s"
    json.dumps(actual.dataset_context.model_dump(mode="json"),allow_nan=False)


def test_volume_export_classifies_current_covariance_once():
    from dtcc_core.model import City
    from dtcc_qes import result as module
    solved=wind.run(City(),speed=5,direction=270,bounds=(0,0,0,24,24,32),turbulence=wind.Turbulence())
    with patch.object(module,"_stress_validity",wraps=module._stress_validity) as validity:
        exported=solved.to_dtcc()
    assert validity.call_count==1
    expected=solved.streamwise_std.transpose(1,2,0).reshape(-1)
    np.testing.assert_array_equal(next(f for f in exported.fields if f.name=="streamwise_std").values,expected)


def test_shared_defaults_are_bound_to_request():
    import inspect
    assert QESWindArgs(**request()).solver==wind.Solver().to_dict()
    assert inspect.signature(wind.run).parameters["solver"].default==wind.Solver()
