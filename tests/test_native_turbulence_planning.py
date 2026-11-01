"""Independent float32 scalar/coordinate checks for the shared native planner."""
import numpy as np
import pytest
from dtcc_qes import _qes


def test_morphometric_scalars_keep_sorted_float32_arithmetic():
    heights=np.array([23.7,7.9,12.1,7.9],dtype=np.float32)
    mean=np.float32(np.cumsum(np.sort(heights),dtype=np.float32)[-1]/np.float32(len(heights)))
    actual=_qes._turbulence_reference(heights.tolist(),.1)
    assert actual["mean_height"]==float(mean)
    assert actual["reference_height"]==float(np.float32(3.*float(mean)))
    assert actual["roughness_length"]==float(np.float32(.1*float(mean)))
    assert actual["displacement_height"]==float(np.float32(.7*float(mean)))


@pytest.mark.parametrize("reference,added",[(24.,0),(np.nextafter(24.,np.inf),1),(25.,1)])
def test_shortest_tail_preserves_operands_and_double_query_boundary(reference,added):
    faces=np.arange(0,32,2,dtype=np.float32)
    actual=_qes._turbulence_extension(faces.tolist(),reference,2.,1,1,2**63-1)
    assert actual["added_layers"]==added and actual["limit"]==""
    np.testing.assert_array_equal(actual["faces"],np.arange(0,32+2*added,2,dtype=np.float32))


@pytest.mark.parametrize("faces,reference,thickness,nx,ny,maximum,reason",[
    ([0,1,2],1000,1,1,1,5,"max_cells limit"),
    ([0,1,2],1000,1,10000,10000,2**63-1,"native index limit"),
    (np.arange(10001,dtype=np.float32).tolist(),20000,1,1,1,2**63-1,"10000-layer limit"),
    ([0,1,1e20],1e20,1,1,1,2**63-1,"float32 coordinate progress limit"),
    ([0,float(np.finfo(np.float32).max)/4,float(np.finfo(np.float32).max)/2],
     float(np.finfo(np.float32).max),float(np.finfo(np.float32).max)/4,1,1,2**63-1,"float32 cell-centre progress limit")])
def test_structured_native_limits(faces,reference,thickness,nx,ny,maximum,reason):
    actual=_qes._turbulence_extension(faces,reference,thickness,nx,ny,maximum)
    assert actual["limit"]==reason
