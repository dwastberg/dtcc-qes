"""Public turbulence fields, analytic statistics and conservative stress sampling."""

from dataclasses import FrozenInstanceError, replace
import json

import numpy as np
import pytest
from dtcc_qes import _qes, wind
from dtcc_qes import result as result_module

from city_cases import city_case
from fixtures.cases import FLAT, ONE_BUILDING
from fixtures.turbulence_cases import CASES as TURBULENCE_CASES
from test_sampling import manufactured

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def solve(case=ONE_BUILDING, **options):
    city,condition,grid,solver = city_case(case)
    return wind.run(city, **(condition | grid | solver | dict(turbulence=True) | options))


def synthetic():
    result = manufactured()
    shape = result.cell_flags.shape
    stress = np.zeros((*shape,6),dtype=np.float32)
    stress[...,0],stress[...,3],stress[...,5] = 4,2,1
    fields = wind.TurbulenceFields(stress,np.ones(shape,dtype=np.float32),
        np.ones(shape,dtype=np.float32),np.ones(shape,dtype=np.float32),
        np.ones(shape,dtype=bool),np.zeros(shape,dtype=bool),np.ones(shape,dtype=bool),
        .2,5,10,.1,0)
    return replace(result,turbulence=fields)


def uniform_synthetic():
    source = synthetic()
    nz = len(source.z)
    return replace(source, z=np.arange(nz,dtype=np.float32)+.5,
                   z_faces=np.arange(nz+1,dtype=np.float32))


def test_to_dtcc_adds_turbulence_fields():
    source = uniform_synthetic()
    fields = source.turbulence
    weights = 1+np.arange(fields.computed.size,dtype=np.float32).reshape(fields.computed.shape)/100
    fields.stress[:] *= weights[...,None]
    fields.tke[:] = weights
    k,j,i = 2,1,3
    covariance = np.array([[9,1,.5],[1,4,-.25],[.5,-.25,1]],dtype=np.float32)
    fields.stress[k,j,i] = covariance[(0,0,0,1,1,2),(0,1,2,1,2,2)]
    fields.tke[k,j,i] = 12.5  # QES TKE is independent of the stress trace.
    source.velocity[k,j,i] = [2,3,6]
    grid = source.to_dtcc()
    exported = {field.name:field for field in grid.fields}
    expected = dict(stress=("m^2/s^2",6),tke=("m^2/s^2",1),streamwise_std=("m/s",1),
                    turbulence_intensity=("1",1),stress_valid=("1",1))
    assert set(exported) == {"velocity","speed","cell_flags",*expected}
    for name,(unit,dim) in expected.items():
        field = exported[name]
        assert (field.unit,field.dim,field.association) == (unit,dim,"cell")
        assert field.values.shape == ((fields.computed.size,6) if dim == 6 else (fields.computed.size,))
        assert "screening" in field.description.lower()
        assert "not validated for pedestrian gusts" in field.description
    assert "xx, xy, xz, yy, yz, zz" in exported["stress"].description
    assert "raw" in exported["stress"].description.lower()
    assert "32" in exported["stress_valid"].description
    nz,ny,nx = fields.computed.shape
    index = (j*nx+i)*nz+k
    np.testing.assert_array_equal(exported["stress"].values[index],fields.stress[k,j,i])
    assert exported["tke"].values[index] == 12.5
    direction = np.array([2,3,6])/7
    sigma = np.sqrt(direction@covariance@direction)
    assert exported["streamwise_std"].values[index] == pytest.approx(sigma,rel=1e-14)
    assert exported["turbulence_intensity"].values[index] == pytest.approx(sigma/7,rel=1e-14)
    assert exported["stress_valid"].values.dtype == np.uint8
    assert exported["stress_valid"].values[index] == 1
    # Compare all cells with explicit axis traversal, independently of transpose.
    np.testing.assert_array_equal(exported["stress"].values,
        [fields.stress[z,y,x] for y in range(ny) for x in range(nx) for z in range(nz)])
    np.testing.assert_array_equal(exported["tke"].values,
        [fields.tke[z,y,x] for y in range(ny) for x in range(nx) for z in range(nz)])
    for name in expected:
        raw = getattr(fields,name,None)
        if raw is not None:
            assert not np.shares_memory(exported[name].values,raw)


@pytest.mark.parametrize("velocity", [[1,0,0],[1,-1,0]])
def test_to_dtcc_preserves_raw_invalid_stress_and_masks_statistics(velocity):
    source = uniform_synthetic()
    fields = source.turbulence
    invalid, uncovered, calm = (2,1,3),(1,0,2),(3,2,1)
    fields.stress[invalid] = [1,2,0,1,0,1]
    fields.capped[invalid] = True
    source.velocity[invalid] = velocity
    fields.computed[uncovered] = False  # Finite edited raw data must be hidden here.
    source.velocity[calm] = 0
    assert fields.stress_valid.all()  # Deliberately stale validity snapshot.
    raw = fields.stress.copy()
    energy = fields.tke.copy()
    exported = {field.name:field for field in source.to_dtcc().fields}
    nz,_,nx = fields.computed.shape
    def index(cell):
        z,y,x = cell
        return (y*nx+x)*nz+z
    bad,missing,zero = map(index,(invalid,uncovered,calm))
    np.testing.assert_array_equal(exported["stress"].values[bad],raw[invalid])
    assert exported["tke"].values[bad] == energy[invalid]
    assert exported["stress_valid"].values[bad] == 0
    for name in ("streamwise_std","turbulence_intensity"):
        assert np.isnan(exported[name].values[[bad,missing,zero]]).all()
    for name in ("stress","tke"):
        assert np.isnan(exported[name].values[missing]).all()
    assert exported["stress_valid"].values[missing] == 0
    assert exported["stress_valid"].values[zero] == 1  # Covariance validity is independent of direction.
    np.testing.assert_array_equal(fields.stress,raw)
    np.testing.assert_array_equal(fields.tke,energy)
    assert fields.stress_valid.all()  # Export never rewrites original snapshots.


def test_to_dtcc_without_turbulence_unchanged():
    source = replace(uniform_synthetic(),turbulence=None)
    fields = {field.name:field for field in source.to_dtcc().fields}
    assert set(fields) == {"velocity","speed","cell_flags"}
    nz,ny,nx = source.cell_flags.shape
    velocity = np.array([source.velocity[z,y,x] for y in range(ny) for x in range(nx) for z in range(nz)])
    np.testing.assert_array_equal(fields["velocity"].values,velocity)
    np.testing.assert_array_equal(fields["speed"].values,np.linalg.norm(velocity.astype(float),axis=-1))
    assert all(field.association == "cell" for field in fields.values())


def test_to_dtcc_turbulence_rejects_nonuniform_layers():
    with pytest.raises(ValueError,match="Nonuniform vertical layers"):
        synthetic().to_dtcc()


@pytest.mark.parametrize("velocity", [[0,0,0],[np.nan,1,0],[np.inf,1,0]])
def test_to_dtcc_covariance_validity_is_independent_of_mean_direction(velocity):
    source = uniform_synthetic()
    source.velocity[:] = velocity
    source.turbulence.stress_valid[:] = False
    fields = {field.name:field for field in source.to_dtcc().fields}
    assert (fields["stress_valid"].values == 1).all()
    assert np.isnan(fields["streamwise_std"].values).all()
    assert np.isnan(fields["turbulence_intensity"].values).all()
    assert not source.turbulence.stress_valid.any()


@pytest.mark.parametrize("method", ["height","wall_distance"])
def test_to_dtcc_native_turbulence_roundtrip_and_provenance(method):
    source = solve(direction=225,turbulence=wind.Turbulence(method))
    grid = source.to_dtcc()
    original = {field.name:field for field in grid.fields}
    restored = type(grid)()
    restored.from_proto(grid.to_proto())
    exported = {field.name:field for field in restored.fields}
    assert set(exported) == set(original)
    for name,field in original.items():
        np.testing.assert_array_equal(exported[name].values,field.values)
        assert (exported[name].unit,exported[name].dim,exported[name].association,
                exported[name].description) == (field.unit,field.dim,field.association,field.description)
    for name in ("stress","tke","streamwise_std","turbulence_intensity","stress_valid"):
        description = exported[name].description
        assert f"mixing_length={method}" in description
        assert source.metadata["turbulence"]["numerics_version"] in description
        assert _qes.qes_revision in description
    computed = source.turbulence.computed
    invalid = computed & ~source.turbulence.stress_valid
    assert invalid.any()
    nz,ny,nx = computed.shape
    for z,y,x in np.argwhere(invalid):
        index = (y*nx+x)*nz+z
        np.testing.assert_array_equal(exported["stress"].values[index],source.turbulence.stress[z,y,x])
        assert exported["stress_valid"].values[index] == 0
        assert np.isnan(exported["streamwise_std"].values[index])
        assert np.isnan(exported["turbulence_intensity"].values[index])


@pytest.mark.parametrize("method", ["height","wall_distance"])
@pytest.mark.parametrize("precision", ["float32","float64"])
def test_run_returns_wind_and_turbulence_in_one_call(method,precision,monkeypatch):
    original = _qes.WindRunner
    calls = []
    class TrackedRunner:
        def __init__(self): self.runner = original()
        def prepare(self,*args,**kwargs):
            calls.append("prepare")
            self.runner.prepare(*args,**kwargs)
        def solve(self,*args,**kwargs):
            calls.append("solve")
            return self.runner.solve(*args,**kwargs)
    monkeypatch.setattr(_qes,"WindRunner",TrackedRunner)
    actual = solve(turbulence=wind.Turbulence(mixing_length=method),solver_precision=precision)
    assert calls == ["prepare","solve"]
    baseline = solve(turbulence=False,solver_precision=precision)
    np.testing.assert_array_equal(actual.velocity,baseline.velocity)
    np.testing.assert_array_equal(actual.cell_flags,baseline.cell_flags)
    assert actual.diagnostics == baseline.diagnostics
    fields = actual.turbulence
    assert isinstance(fields,wind.TurbulenceFields)
    for name in ("stress","tke","co_eps","mixing_length","computed","capped","stress_valid"):
        array = getattr(fields,name)
        expected_shape = (*actual.cell_flags.shape,6) if name == "stress" else actual.cell_flags.shape
        assert array.shape == expected_shape
        assert array.dtype == (bool if name in ("computed","capped","stress_valid") else np.float32)
        assert array.flags.c_contiguous and array.flags.owndata
    assert actual.streamwise_std.dtype == actual.turbulence_intensity.dtype == np.float64


def test_non_computed_cells_are_nan():
    result = solve()
    fields = result.turbulence
    uncomputed = ~fields.computed
    assert uncomputed[-1].all() and uncomputed[:,(0,-1),:].all() and uncomputed[:,:,(0,-1)].all()
    assert uncomputed[result.solid_mask].all()
    for name in ("stress","tke","co_eps","mixing_length"):
        assert np.isnan(getattr(fields,name)[uncomputed]).all()
    assert not fields.stress_valid[uncomputed].any()
    assert np.isnan(result.streamwise_std[uncomputed]).all()
    assert np.isnan(result.turbulence_intensity[uncomputed]).all()


@pytest.mark.parametrize("speed", [0,1e-20,1e-10])
def test_calm_wind_turbulence_is_zero(speed):
    result = solve(FLAT,speed=speed)
    fields = result.turbulence
    computed = fields.computed
    assert not fields.capped.any()
    assert fields.stress_valid[computed].all()
    assert (fields.mixing_length[computed] > 0).all()
    for name in ("stress","tke","co_eps"):
        assert np.isfinite(getattr(fields,name)[computed]).all()
        if speed == 0:
            assert (getattr(fields,name)[computed] == 0).all()
    for array in (result.streamwise_std,result.turbulence_intensity):
        assert not np.isinf(array).any()
        if speed == 0:
            assert np.isnan(array).all()
    if speed == 0:
        assert result.metadata["turbulence"]["validity"]["zero_speed_cells"] == int(computed.sum())


@pytest.mark.parametrize("direction", [270,240,225,0])
def test_flat_streamwise_std_matches_surface_layer_relation(direction):
    result = solve(FLAT,direction=direction)
    speed = np.linalg.norm(result.velocity.astype(float),axis=-1)
    gradient = (speed[2:,10,10]-speed[:-2,10,10])/(result.z[2:].astype(float)-result.z[:-2])
    expected = 2.5*.4*result.z[1:-1].astype(float)*np.abs(gradient)
    np.testing.assert_allclose(result.streamwise_std[1:-1,10,10],expected,rtol=1e-5,atol=1e-7)
    # Independent full covariance in streamwise/crosswind/vertical dyads.
    k=4
    n=result.velocity[k,10,10].astype(float)
    n/=np.linalg.norm(n)
    m,z=np.array([-n[1],n[0],0]),np.array([0,0,1])
    length=.4*float(result.z[k])
    g=gradient[k-1]
    covariance=((2.5*length*g)**2*np.outer(n,n)+(2*length*g)**2*np.outer(m,m)
                +(1.3*length*g)**2*np.outer(z,z)-length**2*g**2*(np.outer(n,z)+np.outer(z,n)))
    np.testing.assert_allclose(result.turbulence.stress[k,10,10],
        covariance[(0,0,0,1,1,2),(0,1,2,1,2,2)],rtol=1e-5,atol=1e-7)


def test_stretched_grid_matches_nonuniform_gradient():
    faces = np.r_[0.,np.cumsum([.125,.375,.75,1.25]*20)]
    result = solve(FLAT,direction=225,vertical_grid=wind.VerticalGrid.from_faces(faces),
                   bounds=(0,0,0,80,60,float(faces[-1])))
    speed = np.linalg.norm(result.velocity[:,10,10].astype(float),axis=-1)
    z = result.z.astype(float)
    hm,hp = z[1:-1]-z[:-2],z[2:]-z[1:-1]
    gradient = (hm/hp*(speed[2:]-speed[1:-1])+hp/hm*(speed[1:-1]-speed[:-2]))/(hp+hm)
    np.testing.assert_allclose(result.streamwise_std[1:-1,10,10],2.5*.4*z[1:-1]*np.abs(gradient),rtol=1e-4,atol=1e-7)


def test_speed_scaling():
    a,b = solve(speed=5,tolerance=1e-5),solve(speed=10,tolerance=2e-5)
    np.testing.assert_allclose(b.streamwise_std,2*a.streamwise_std,rtol=1e-4,atol=1e-7,equal_nan=True)
    np.testing.assert_allclose(b.turbulence_intensity,a.turbulence_intensity,rtol=1e-4,atol=1e-7,equal_nan=True)


def test_sample_includes_stress():
    result = synthetic()
    result.turbulence.stress[2] *= 2
    sample = result.sample(1.5,"linear")
    lo,hi=1,2
    weight = (1.5-float(result.z[lo]))/(float(result.z[hi])-float(result.z[lo]))
    expected = result.turbulence.stress[lo].astype(float)*(1-weight)+result.turbulence.stress[hi].astype(float)*weight
    np.testing.assert_allclose(sample.stress,expected,rtol=0,atol=1e-15)
    assert sample.stress.dtype == np.float64 and sample.stress.flags.owndata
    assert sample.stress_valid.dtype == bool and sample.stress_valid.all()
    assert not np.shares_memory(sample.stress,result.turbulence.stress)
    for name in ("streamwise_std","turbulence_intensity"):
        assert np.isfinite(getattr(sample,name)).all()


@pytest.mark.parametrize("raw", [[1,2,0,1,0,1],[1,np.nan,0,1,0,1],[1,np.inf,0,1,0,1]])
def test_invalid_raw_stress_is_preserved_but_statistics_are_nan(raw):
    result = synthetic()
    result.turbulence.stress[1,0,0] = raw
    before = result.turbulence.stress.copy()
    assert np.isnan(result.streamwise_std[1,0,0]) and np.isnan(result.turbulence_intensity[1,0,0])
    np.testing.assert_array_equal(result.turbulence.stress,before)


def test_positive_projection_does_not_hide_indefinite_tensor():
    result = synthetic()
    result.velocity[:] = [1,0,0]
    result.turbulence.stress[:] = [1,2,0,1,0,1]
    assert np.isnan(result.streamwise_std).all()


@pytest.mark.parametrize("scale", [1e-30,1,1e30])
def test_validity_roundoff_tolerance_scales_with_speed(scale):
    result = synthetic()
    result.velocity[:] = [1,0,0]
    eps = np.finfo(np.float32).eps
    result.turbulence.stress[:] = np.float32([-eps,0,0,1,0,2])*scale
    np.testing.assert_array_equal(result.streamwise_std,0)
    result.turbulence.stress[:] = np.float32([-1e-3,0,0,1,0,2])*scale
    assert np.isnan(result.streamwise_std).all()


def test_sample_preserves_invalid_contributor_and_zero_speed_masks():
    result = synthetic()
    result.velocity[1] = [5,0,0]
    result.velocity[2] = [-5,0,0]
    midpoint = .5*(float(result.z[1])+float(result.z[2]))
    result.turbulence.stress[1,0,0] = [1,2,0,1,0,1]
    result.turbulence.stress[2,0,0] = [3,-2,0,3,0,3]
    sample = result.sample(midpoint,"linear")
    # The interpolated tensor is PSD; the invalid contributor still disqualifies it.
    np.testing.assert_array_equal(sample.stress[0,0],[2,0,0,2,0,2])
    assert not sample.stress_valid[0,0]
    assert np.isnan(sample.streamwise_std).all()  # Mean directions cancel.
    result.velocity[2] = [5,0,0]
    sample = result.sample(midpoint,"linear")
    assert np.isnan(sample.streamwise_std[0,0])
    assert np.isfinite(sample.streamwise_std[1:,1:]).all()
    result.turbulence.computed[1,1,1] = False
    sample = result.sample(midpoint,"linear")
    assert np.isnan(sample.stress[1,1]).all() and not sample.stress_valid[1,1]
    # Exact-centre selection must ignore the bad/uncomputed adjacent layer.
    exact = result.sample(float(result.z[2]),"linear")
    assert exact.stress_valid.all()


def test_derived_statistics_recheck_edited_stress():
    result = synthetic()
    expected = result.streamwise_std.copy()
    result.turbulence.stress_valid[:] = False  # Native snapshot can become stale.
    np.testing.assert_array_equal(result.streamwise_std,expected)
    result.turbulence.stress[:] = [1,2,0,1,0,1]
    assert np.isnan(result.streamwise_std).all()
    result.turbulence.stress[:] = [4,0,0,2,0,1]
    sample = result.sample(1.5,"linear")
    assert sample.stress_valid.all()
    sample.stress[:] = [1,2,0,1,0,1]
    assert np.isnan(sample.streamwise_std).all()


@pytest.mark.parametrize("method", ["height","wall_distance"])
@pytest.mark.parametrize("precision", ["float32","float64"])
def test_python_validity_matches_native_extraction(method,precision):
    result = solve(turbulence=wind.Turbulence(method),solver_precision=precision)
    valid,tolerance = result_module._stress_validity(result.turbulence.stress)
    np.testing.assert_array_equal(valid,result.turbulence.stress_valid)
    assert (tolerance[result.turbulence.computed] >= 0).all()


def test_metadata_records_reference_and_cap():
    result = solve()
    t,meta=result.turbulence,result.metadata["turbulence"]
    assert meta["mixing_length"] == "height" and meta["qes_method"] == 0 and meta["numerics_version"]
    assert meta["reference"]["height"] == t.reference_height == 24
    assert meta["reference"]["basis"] == "3 × mean building height"
    assert meta["reference"]["friction_velocity"] == t.friction_velocity
    assert meta["constants"]["c0"] == 5.7 and meta["constants"]["upper_bound"] == 20
    assert meta["cap"]["computed_cells"] == int(t.computed.sum())
    assert meta["cap"]["capped_cells"] == int(t.capped.sum())
    assert meta["validity"]["invalid_stress_cells"] == int((t.computed & ~t.stress_valid).sum())
    assert meta["validity"]["policy"] == "raw_and_mask" and meta["limitations"]
    assert meta["domain_top"] == result.metadata["domain"]["turbulence"]
    json.dumps(result.metadata,allow_nan=False)


@pytest.mark.parametrize("value", [None,1,"height",{},np.bool_(True)])
def test_invalid_turbulence_argument(value,monkeypatch):
    monkeypatch.setattr(_qes,"WindRunner",lambda:pytest.fail("Allocated native fields"))
    city,_,grid,_=city_case(ONE_BUILDING)
    for call in (lambda:wind.run(city,5,270,**grid,turbulence=value),
                 lambda:wind.preview_grid(city,**grid,turbulence=value)):
        with pytest.raises(ValueError,match="turbulence must be"):
            call()


def test_turbulence_spec_is_validated_and_immutable():
    spec = wind.Turbulence()
    assert spec.mixing_length == "height" and spec.qes_method == 0
    assert wind.Turbulence("wall_distance").qes_method == 1
    with pytest.raises(FrozenInstanceError):
        spec.mixing_length = "wall_distance"
    for value in (None,0,"unknown",[],np.array(["height"])):
        with pytest.raises(ValueError,match="mixing_length"):
            wind.Turbulence(value)


def test_wall_distance_mixing_length_not_longer_than_height():
    height,wall=solve(),solve(turbulence=wind.Turbulence("wall_distance"))
    np.testing.assert_array_equal(height.velocity,wall.velocity)
    computed=height.turbulence.computed & wall.turbulence.computed
    assert (wall.turbulence.mixing_length[computed] <= height.turbulence.mixing_length[computed]).all()
    assert (wall.turbulence.mixing_length[computed] < height.turbulence.mixing_length[computed]).any()


def test_turbulence_false_metadata_unchanged():
    city,condition,grid,solver=city_case(ONE_BUILDING)
    original=wind.run(city,**condition,**grid,**solver)
    disabled=wind.run(city,**condition,**grid,**solver,turbulence=False)
    assert original.turbulence is disabled.turbulence is None
    assert original.metadata == disabled.metadata and "turbulence" not in disabled.metadata
    assert original.sample(1.5).stress is None and original.sample(1.5).stress_valid is None
    for result in (original,original.sample(1.5)):
        with pytest.raises(ValueError,match="turbulence"):
            _=result.streamwise_std
        with pytest.raises(ValueError,match="turbulence"):
            _=result.turbulence_intensity


def test_automatic_preview_spec_matches_public_solve():
    city,condition,_,solver=city_case(ONE_BUILDING)
    spec=wind.Turbulence("wall_distance")
    preview=wind.preview_grid(city,turbulence=spec,vertical_grid=wind.VerticalGrid.auto())
    result=wind.run(city,**condition,**solver,turbulence=spec,vertical_grid=wind.VerticalGrid.auto())
    assert result.metadata["domain"] == preview.domain
    assert result.metadata["turbulence"]["qes_method"] == 1
    np.testing.assert_array_equal(result.z_faces,preview.z_faces)


def test_sample_boundaries_and_noncomputed_contributors():
    result=solve()
    top=result.sample(float(result.z[-1]),"linear")
    assert top.valid.any() and np.isnan(top.stress).all() and not top.stress_valid.any()
    assert np.isnan(top.streamwise_std).all()
    outside=result.sample(0,"linear")
    assert np.isnan(outside.stress).all() and not outside.stress_valid.any()
    source=synthetic()
    source.turbulence.computed[0]=False
    exact=source.sample(float(source.z[1]),"linear")
    assert exact.stress_valid.all()
    adjacent=source.sample(np.nextafter(float(source.z[1]),0),"linear")
    assert np.isnan(adjacent.stress).all()


def test_sample_edits_recheck_current_tensor_and_retain_contributor_evidence():
    source=synthetic()
    sample=source.sample(1.5,"linear")
    expected=sample.streamwise_std.copy()
    sample.stress_valid[:]=False
    np.testing.assert_array_equal(sample.streamwise_std,expected)
    sample.stress[:]=[1,2,0,1,0,1]
    assert np.isnan(sample.streamwise_std).all()
    sample.stress[:]=[4,0,0,2,0,1]
    np.testing.assert_array_equal(sample.streamwise_std,expected)
    source.turbulence.stress[1,0,0]=[1,2,0,1,0,1]
    bad=source.sample(1.5,"linear")
    bad.stress[:]=[4,0,0,2,0,1]
    bad.stress_valid[:]=True
    assert np.isnan(bad.streamwise_std[0,0])


@pytest.mark.parametrize("speed", [1e-200,1e200])
def test_direction_normalization_avoids_squaring_speed(speed):
    source=synthetic()
    velocity=np.full_like(source.velocity,speed,dtype=np.float64)
    velocity[...,2]=0
    source=replace(source,velocity=velocity)
    np.testing.assert_allclose(source.streamwise_std,np.sqrt(3),rtol=1e-14,atol=0)
    assert np.isfinite(source.turbulence_intensity).all()


@pytest.mark.parametrize("velocity", [[0,0,0],[np.nan,1,0],[np.inf,1,0]])
def test_undefined_current_mean_direction_masks_statistics(velocity):
    source=synthetic()
    source.velocity[:]=velocity
    assert np.isnan(source.streamwise_std).all()
    assert np.isnan(source.turbulence_intensity).all()


def test_metadata_counts_remain_original_solve_snapshots():
    source=solve()
    before=json.dumps(source.metadata["turbulence"],sort_keys=True,allow_nan=False)
    source.turbulence.stress[:]=[1,2,0,1,0,1]
    assert np.isnan(source.streamwise_std).all()
    assert json.dumps(source.metadata["turbulence"],sort_keys=True,allow_nan=False) == before


@pytest.mark.parametrize("scale", [1e-20,1,1e20])
def test_full_three_dimensional_projection_matches_factor_oracle(scale):
    source=synthetic()
    factor=np.array([[3,0,0],[1,2,0],[1,.5,1]],dtype=float)
    covariance=factor@factor.T
    source.turbulence.stress[:]=covariance[(0,0,0,1,1,2),(0,1,2,1,2,2)]*scale
    source.velocity[:]=[1,2,3]
    n=np.array([1,2,3])/np.sqrt(14)
    expected=np.linalg.norm(factor.T@n)*np.sqrt(scale)
    np.testing.assert_allclose(source.streamwise_std,expected,rtol=1e-6,atol=0)
    np.testing.assert_allclose(source.turbulence_intensity,expected/np.sqrt(14),rtol=1e-6,atol=0)
    sample=source.sample(1.5,"linear")
    np.testing.assert_allclose(sample.streamwise_std,expected,rtol=1e-6,atol=0)


@pytest.mark.parametrize("spec",TURBULENCE_CASES.values(),ids=TURBULENCE_CASES)
def test_public_fields_match_audited_standalone_reference(spec):
    import platform
    from test_turbulence_reference import DIRECTORY
    path=DIRECTORY/"audited"/f"{spec.case.name}.npz"
    metadata=json.loads(path.with_suffix(".json").read_text())
    toolchain=metadata["toolchain"]
    if (toolchain["compiler_id"] != _qes.compiler_id or toolchain["compiler_version"] != _qes.compiler_version
            or toolchain["build_type"] != _qes.build_type or toolchain["machine"] != platform.machine()
            or toolchain["platform"] != platform.platform() or _qes.cpu_sweep_order != "lexicographic"):
        pytest.skip("Archived exact parity requires lexicographic ordering and the recorded toolchain")
    city,condition,grid,solver=city_case(spec.case)
    options={}
    if spec.dz_layers:
        faces=np.r_[0.,np.cumsum(spec.dz_layers)]
        grid["bounds"]=(*grid["bounds"][:5],float(faces[-1]))
        options["vertical_grid"]=wind.VerticalGrid.from_faces(faces)
    result=wind.run(city,**condition,**grid,**solver,**options,
                    turbulence=wind.Turbulence("wall_distance" if spec.method else "height"))
    assert result.diagnostics.converged
    with np.load(path) as reference:
        computed=result.turbulence.computed
        np.testing.assert_array_equal(computed,reference["computed"])
        for name in ("stress","tke","co_eps","mixing_length"):
            np.testing.assert_array_equal(getattr(result.turbulence,name)[computed],reference[name][computed])
