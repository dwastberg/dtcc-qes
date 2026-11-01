"""Independent point-reconstruction checks before interpreting urban probes."""
import copy
from itertools import product
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/"tools"))
from near_wall_sampling import difference, interpolate, reconstruct
sys.path.pop(0)


from fixtures.near_wall_validation import patch

@pytest.mark.parametrize("method", ["centred", "staggered"])
def test_affine_vector_and_nonuniform_tensor_interpolation(method):
    f = lambda x,y,z: [1+2*x-3*y+.5*z, -x+y+z, 2*x-y-z]
    p = patch(.5, [1.2, 1.6, 1.75], f)
    np.testing.assert_allclose(reconstruct(p, method), f(*p["local_point"]), atol=2e-7, rtol=0)
    rows=[dict(position=list(q), value=f(*q)) for q in product([0,1,3], [0,2], [.25,.75,2.5])]
    np.testing.assert_allclose(interpolate(rows,[1.2,1,1.5],field="value",valid=lambda _:True), f(1.2,1,1.5),atol=1e-14)


def test_curved_field_exposes_extra_centring_filter_and_refines_quadratically():
    f=lambda x,y,z:[x*x,y*y,z*z]
    errors=[]
    for h in (1,.5,.25):
        p=patch(h,[2,2,2],f)
        np.testing.assert_allclose(reconstruct(p,"staggered"),[4,4,4],atol=0)
        error=reconstruct(p,"centred")-4
        np.testing.assert_allclose(error,np.full(3,h*h/2),atol=0)
        errors.append(error[0])
    np.testing.assert_array_equal(np.array(errors[:-1])/errors[1:],4)


def test_wall_normal_boundary_value_and_centring_at_one_metre_setback():
    # Wall at x=2; a discontinuous initialized face field, not a continuum solution.
    f=lambda x,y,z:[5. if x<2 else 0.,0.,0.]
    for h, expected in ((1,3.75),(.5,5.),(.25,5.)):
        p=patch(h,[1,1.5,1.5],f)
        for row in p["cells"]: row["flag"]=1 if row["position"][0]<2 else 0
        for row in p["faces"][0]:
            x=row["position"][0]
            row["flags"]=[1 if x-h/2<2 else 0,1 if x+h/2<2 else 0]
        assert reconstruct(p,"centred")[0] == expected
        assert reconstruct(p,"staggered")[0] == 5
    p["local_point"]=[2,1.5,1.5]
    assert reconstruct(p,"staggered")[0] == 0  # fluid/solid boundary face
    p["query_flag"]=0
    assert reconstruct(p,"staggered") is None


@pytest.mark.parametrize("method", ["centred", "staggered"])
def test_positive_weight_solid_and_nonfinite_support_rejected(method):
    p=patch(1,[1.2,1.3,1.4],lambda *p:[1,2,3])
    if method=="centred":
        row=next(r for r in p["cells"] if r["position"]==[.5,.5,.5])
        row["flag"]=2
    else:
        row=next(r for r in p["faces"][0] if r["position"]==[1,.5,.5])
        row["flags"]=[0,2]
    assert reconstruct(p,method) is None
    q=patch(1,[1.2,1.3,1.4],lambda *p:[1,2,3])
    if method=="centred": q["cells"][0]["velocity"]=[np.nan]*3
    else: next(r for r in q["faces"][0] if r["position"]==[1,.5,.5])["value"]=np.nan
    assert reconstruct(q,method) is None


def test_exact_support_ignores_zero_weight_solid_and_rejects_extrapolation():
    rows=[dict(position=list(p),value=7.,flag=1 if p==(1,1,1) else 0) for p in product([0,1,2],repeat=3)]
    assert interpolate(rows,[1,1,1],field="value",valid=lambda r:r["flag"]==1)==7
    assert interpolate(rows,[3,1,1],field="value",valid=lambda r:True) is None
    assert interpolate(rows,[np.nextafter(1.,2),1,1],field="value",valid=lambda r:r["flag"]==1) is None


def test_low_speed_budget_and_invalid_points():
    assert difference([.1,0,0],[.2,0,0])["within_budget"]
    assert not difference([1,0,0],[2,0,0])["within_budget"]
    assert not difference(None,[2,0,0])["within_budget"]
