"""Scalar validation boundaries, independent of the native runner."""
import numpy as np
import pytest
from dtcc_qes._validation import real,integer
from dtcc_qes import wind,comfort


@pytest.mark.parametrize("value",[True,np.bool_(False),"1",1+0j,np.array(1.),np.array([1.]),
                                  float("nan"),float("inf"),10**1000])
def test_real_rejects_non_scalar_or_nonfinite(value):
    with pytest.raises(ValueError,match="coordinate"):
        real(value,"coordinate")


@pytest.mark.parametrize("value",[1,1.,np.int32(1),np.uint64(1),np.float32(1),np.float64(1)])
def test_real_accepts_real_number_types_and_returns_python_float(value):
    assert type(real(value,"value")) is float
    assert real(value,"value",positive=True,float32=True)==1.


def test_signed_positive_nonnegative_and_narrowing_boundaries():
    assert real(-5,"coordinate")==-5
    assert real(0,"height",nonnegative=True)==0
    with pytest.raises(ValueError,match="nonnegative"):
        real(-1,"height",nonnegative=True)
    with pytest.raises(ValueError,match="positive"):
        real(0,"length",positive=True)
    maximum=float(np.finfo(np.float32).max)
    assert real(maximum,"native",positive=True,float32=True)==maximum
    subnormal=float(np.nextafter(np.float32(0),np.float32(1)))
    assert real(subnormal,"native",positive=True,float32=True)==subnormal
    assert real(subnormal/4,"budget",positive=True)==subnormal/4
    with pytest.raises(ValueError,match="float32"):
        real(subnormal/4,"roughness",positive=True,float32=True)
    with pytest.raises(ValueError,match="float32"):
        real(maximum*2,"native",float32=True)


@pytest.mark.parametrize("value",[True,np.bool_(False),"1",1.,np.array(1),np.array([1]),
                                  1+0j,-1,2**31])
def test_integer_rejects_coercion_and_range_errors(value):
    with pytest.raises(ValueError,match="count"):
        integer(value,"count")


def test_integer_scalar_types_and_explicit_bounds():
    assert type(integer(np.int64(5),"count")) is int
    assert integer(np.int64(2**40),"capacity",maximum=np.iinfo(np.int64).max)==2**40
    assert integer(-1,"last",minimum=-1)==-1
    assert integer(0,"residual_interval",minimum=0)==0


@pytest.mark.parametrize("value",[True,np.bool_(True),"2",np.array(2.),np.array([2.])])
def test_public_specifications_share_scalar_rejection(value):
    for create in (lambda:wind.LogProfile(value,270),lambda:wind.Solver(tolerance=value),
        lambda:wind.VerticalGrid.auto(growth_rate=value),
        lambda:comfort.log_law_transfer([5],value,.1,10,.1)):
        with pytest.raises(ValueError):
            create()


def test_signed_monitor_coordinates_and_nonnegative_heights():
    assert wind.Receptor("negative",np.float32(-1),np.int64(-2),0).x==-1
    with pytest.raises(ValueError,match="nonnegative"):
        wind.Receptor("below",0,0,-1)
    with pytest.raises(ValueError,match="nonnegative"):
        wind.MonitorSpec((-10,10,-10,10),heights=(-1,))
