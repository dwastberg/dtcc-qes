"""Float64 independent oracle for the actual research spectral implementation."""
from pathlib import Path
import os
import subprocess
import numpy as np
import pytest

ROOT=Path(os.environ['DTCC_QES_RESEARCH_ROOT'])

@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    binary=tmp_path_factory.mktemp('limiter')/'probe'
    subprocess.run(['c++','-std=c++17','-O2','-I'+str(ROOT/'src/qes_core'),
        str(Path(__file__).with_name('covariance_limiter_probe.cpp')),'-o',str(binary)],check=True)
    def run(tensors,bounds):
        inputs=np.column_stack((tensors,bounds)).astype(np.float32)
        payload='\n'.join(' '.join(format(float(v),'.9g') for v in row) for row in inputs)+'\n'
        result=subprocess.run([str(binary)],input=payload,text=True,capture_output=True,check=True)
        return np.fromstring(result.stdout,sep=' ').reshape(-1,7)
    return run


def pack(t):return t[:,(0,0,0,1,1,2),(0,1,2,1,2,2)]
def matrices(t):return t[:,(0,1,2,1,3,4,2,4,5)].reshape(-1,3,3).astype(float)


def test_native_against_numpy_rotation_repeated_eigenvalues_scales_and_edges(probe):
    rng=np.random.default_rng(20261111)
    q,_=np.linalg.qr(rng.normal(size=(240,3,3)))
    eigen=np.tile([1.,1.+1e-7,2.],(240,1))
    eigen[::3,0]=-np.finfo(np.float32).eps
    eigen[1::3,0]=-1e-3
    tensor=q@(np.eye(3)[None,:,:]*eigen[:,None,:])@q.transpose(0,2,1)
    scale=np.geomspace(1e-30,1e30,len(tensor))
    packed=(pack(tensor)*scale[:,None]).astype(np.float32)
    bound=(scale*.7).astype(np.float32)
    outcome=probe(packed,bound)
    radius=np.max(np.abs(np.linalg.eigvalsh(matrices(packed))),axis=1)
    alpha=np.minimum(1,bound.astype(float)/radius)
    np.testing.assert_allclose(outcome[:,0],alpha,rtol=2e-12)
    np.testing.assert_allclose(outcome[:,1:],(packed.astype(float)*alpha[:,None]).astype(np.float32),rtol=2e-6,atol=0)
    rotation,_=np.linalg.qr(rng.normal(size=(3,3)))
    rotated=pack(rotation@matrices(packed)@rotation.T).astype(np.float32)
    actual=matrices(probe(rotated,bound)[:,1:])
    expected=rotation@matrices(outcome[:,1:])@rotation.T
    np.testing.assert_allclose(actual/scale[:,None,None],expected/scale[:,None,None],atol=4e-7,rtol=2e-6)


def test_exact_row_sum_boundary_and_calm(probe):
    tensors=np.array([[1,.25,0,1,0,.5],[0,0,0,0,0,0],[1,0,0,1,0,1]],np.float32)
    bound=np.array([1.25,0,1],np.float32)
    output=probe(tensors,bound)
    np.testing.assert_array_equal(output[:,0],1)
    np.testing.assert_array_equal(output[:,1:],tensors)
    active=probe(tensors[:1],np.nextafter(bound[:1],np.float32(0)))
    assert active[0,0]<1


def test_native_zero_length_and_supported_zero_energy_branches(tmp_path):
    source=tmp_path/'zero.cpp'
    source.write_text('''#include "dtcc/api/covariance_model.h"
#include <cassert>
int main() {
 using namespace dtcc_qes;
 assert(uncapped_energy(0,0)==0);
 assert(production_scale(0,0)==1);
 assert(!std::isfinite(uncapped_energy(1,0)));
 assert(std::isnan(production_scale(0,uncapped_energy(1,0))));
 StressTensor strain{};
 const auto invalid=consistent_constitutive(strain,1,uncapped_energy(1,0),0);
 assert(!stress_validity(invalid).valid);
 StressTensor zero{};
 assert(spectral_limit(zero,0)==1 && stress_validity(zero).valid);
}''')
    binary=tmp_path/'zero'
    subprocess.run(['c++','-std=c++17','-O2','-I'+str(ROOT/'src/qes_core'),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
