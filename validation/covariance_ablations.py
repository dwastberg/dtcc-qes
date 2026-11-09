"""Frozen one-way 2x2x2 covariance ablations; no fitted coefficients."""
from itertools import product
import numpy as np

from dtcc_qes._statistics import _stress_validity

ARMS=tuple(f'P{p}A{a}C{c}' for p,a,c in product((0,1),repeat=3))


def matrices(raw):
    raw=np.asarray(raw,float)
    return raw[..., (0,1,2,1,3,4,2,4,5)].reshape(*raw.shape[:-1],3,3)


def components(matrix):
    return np.asarray(matrix)[..., (0,0,0,1,1,2),(0,1,2,1,2,2)]


def rotations(orientations):
    c,s=np.asarray(orientations,float)[:,:2].T
    q=np.zeros((len(c),3,3));q[:,0,0]=q[:,1,1]=c;q[:,1,0]=s;q[:,0,1]=-s;q[:,2,2]=1
    return q


def anisotropy(raw,orientations,congruence):
    q=rotations(orientations);t=matrices(raw);tw=q.transpose(0,2,1)@t@q
    factors=np.asarray(orientations,float)[:,2:]
    if congruence:
        scale=np.sqrt(factors);tw=tw*scale[:,:,None]*scale[:,None,:]
    else:
        for j in range(3):tw[:,j,j]=np.abs(factors[:,j]*tw[:,j,j])
    return components(q@tw@q.transpose(0,2,1)).astype(np.float32)


def spectral_bound(raw,bounds):
    raw=np.asarray(raw,np.float32);finite=np.isfinite(raw).all(axis=1)
    out=raw.copy();radius=np.full(len(raw),np.nan)
    radius[finite]=np.max(np.abs(np.linalg.eigvalsh(matrices(raw[finite]))),axis=1)
    scale=np.minimum(1,np.divide(bounds,radius,out=np.ones(len(raw)),where=radius>0))
    out[finite]=(raw[finite].astype(float)*scale[finite,None]).astype(np.float32)
    return out


def arms(trace):
    found=np.all(trace['tensor_found'].astype(bool),axis=0)
    valid=found&np.isfinite(trace['orientations']).all(axis=1)
    props=trace['properties'];bounds=props[:,13];result={}
    reconstruction=np.full_like(trace['tensors'][1],np.nan)
    reconstruction[valid]=anisotropy(trace['tensors'][0,valid],trace['orientations'][valid],False)
    # Native stored tensors anchor the observed legacy path exactly.
    for name in ARMS:
        p,a,c=(int(name[i]) for i in (1,3,5))
        if name=='P0A0C0':
            result[name]=trace['tensors'][2].copy();continue
        if p==0 and a==0:
            t=trace['tensors'][1].copy()
        else:
            pre=trace['tensors'][0].copy()
            if p:
                ratio=np.minimum(1,np.divide(props[:,11],props[:,12],out=np.ones(len(props)),where=props[:,12]>0))
                pre=(trace['uncapped_constitutive_reconstruction'].astype(float)*ratio[:,None]).astype(np.float32)
            t=np.full_like(pre,np.nan);t[valid]=anisotropy(pre[valid],trace['orientations'][valid],bool(a))
        result[name]=spectral_bound(t,bounds) if c else np.clip(t,-bounds[:,None],bounds[:,None])
    error=np.abs(reconstruction.astype(float)-trace['tensors'][1].astype(float))
    scale=np.maximum(1,np.max(np.abs(trace['tensors'][1]),axis=1))
    relative=np.max(error,axis=1)/scale
    return result,dict(compared=int(valid.sum()),maximum_scaled_error=float(np.max(relative[valid])) if valid.any() else None,
        maximum_absolute_error=float(np.max(error[valid])) if valid.any() else None,
        validity_disagreements=int(np.count_nonzero(_stress_validity(reconstruction[valid])[0]!=_stress_validity(trace['tensors'][1,valid])[0])))


def interpolate(raw,trace,points,axes):
    """Positive-weight component interpolation; never fill missing/invalid sources."""
    from frozen_stress_support import stencil
    support=stencil(dict(axes=axes,solid=np.zeros(tuple(len(a) for a in axes[::-1]),bool)),points)
    lookup={tuple(c):i for i,c in enumerate(trace['tensor_cells'])}
    tensors=np.full((len(points),6),np.nan);valid=np.zeros(len(points),bool);covered=np.zeros(len(points),bool)
    cell_valid=_stress_validity(raw)[0];computed=np.all(trace['tensor_found'].astype(bool),axis=0)
    for i,(at,weights) in enumerate(zip(support['indices'],support['weights'])):
        take=weights>0
        if not support['supported'][i]:continue
        indices=np.array([lookup[tuple(c)] for c in at[take,::-1]])
        if not computed[indices].all():continue
        covered[i]=True;tensors[i]=np.sum(raw[indices].astype(float)*weights[take,None],axis=0)
        valid[i]=cell_valid[indices].all() and _stress_validity(tensors[i:i+1])[0][0]
    return tensors,valid,covered
