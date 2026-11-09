import numpy as np

from covariance_ablations import anisotropy,components,matrices,spectral_bound
from dtcc_qes._statistics import _stress_validity


def test_spectral_bounding_preserves_psd_and_is_rotation_equivariant():
    t=np.array([[3.,2.2,.1,2.7,-.03,1.]],np.float32)
    theta=.73;q=np.array([[np.cos(theta),-np.sin(theta),0],[np.sin(theta),np.cos(theta),0],[0,0,1]])
    a=spectral_bound(t,np.array([1.7]))
    b=spectral_bound(components(q@matrices(t)@q.T),np.array([1.7]))
    assert _stress_validity(a)[0].all()
    np.testing.assert_allclose(matrices(b),q@matrices(a)@q.T,rtol=3e-7,atol=2e-7)
    assert np.linalg.eigvalsh(matrices(a)).max()<=1.7+1e-6


def test_congruence_changes_cross_covariances_and_preserves_psd():
    raw=np.array([[1.,0,.8,1.,0,1.]],np.float32)
    orientation=np.array([[1,0,2.,1.,.5]])
    result=anisotropy(raw,orientation,True)
    assert _stress_validity(result)[0].all()
    np.testing.assert_allclose(result[0,[0,3,5]],[2,1,.5])
    assert result[0,2]==np.float32(.8)


def test_tensor_cap_does_not_rehabilitate_an_indefinite_input_and_handles_zero():
    raw=np.array([[1,2,0,1,0,1],[0,0,0,0,0,0]],np.float32)
    result=spectral_bound(raw,np.array([.5,.5]))
    assert _stress_validity(result)[0].tolist()==[False,True]
    assert np.max(np.abs(result[0]))<=.5
    np.testing.assert_array_equal(result[1],0)


def test_native_default_diagonal_scaling_has_a_positive_schur_multiplier():
    multipliers=np.array([2.8359377,1.815,.7668375])
    multiplier=np.ones((3,3));np.fill_diagonal(multiplier,multipliers)
    assert np.linalg.eigvalsh(multiplier).min()>.1
    rng=np.random.default_rng(611)
    vectors=rng.normal(size=(100,3))
    raw=components(vectors[:,:,None]*vectors[:,None,:]).astype(np.float32)
    theta=np.linspace(0,2*np.pi,100)
    orientations=np.c_[np.cos(theta),np.sin(theta),np.tile(multipliers,(100,1))]
    assert _stress_validity(anisotropy(raw,orientations,False))[0].all()


def test_coupled_production_limit_preserves_psd_for_general_strain_and_zero():
    rng=np.random.default_rng(20261107)
    gradient=rng.normal(size=(300,3,3));strain=.5*(gradient+gradient.transpose(0,2,1))
    strain[0]=0
    length=np.exp(rng.uniform(-3,3,len(strain)))
    norm=np.linalg.norm(strain,axis=(1,2));nu=length**2*np.sqrt(2)*norm
    energy=2*length**2*norm**2/.55**2
    bound=np.exp(rng.uniform(-5,2,len(strain)));limited=np.minimum(energy,bound)
    ratio=np.divide(limited,energy,out=np.ones(len(strain)),where=energy>0)
    uncapped=(2/3)*energy[:,None,None]*np.eye(3)-2*nu[:,None,None]*strain
    raw=components(uncapped*ratio[:,None,None]).astype(np.float32)
    assert np.isfinite(raw).all() and _stress_validity(raw)[0].all()
    np.testing.assert_array_equal(raw[0],0)


def test_component_clipping_can_destroy_an_initially_valid_covariance():
    vector=np.array([2.,2.,.2])
    raw=components(np.outer(vector,vector))[None,:].astype(np.float32)
    assert _stress_validity(raw)[0].all()
    # Unequal normal saturation invalidates this rank-one tensor.
    assert not _stress_validity(np.clip(raw,-1,1))[0].all()
    assert _stress_validity(spectral_bound(raw,np.array([1.])))[0].all()
