"""Offline capture support; no research runtime dependencies."""
import gzip
import json
from pathlib import Path
from itertools import product
import numpy as np


def read(path):
    path=Path(path)
    return json.loads(path.read_text() if path.exists() else gzip.decompress(path.with_suffix('.json.gz').read_bytes()))


def run_folder(campaign,name):
    folder=campaign/name
    return folder if folder.exists() else campaign/'raw'/name


def stencil(occupancy,points):
    """Positive-weight cell-centred linear support, including exact-centre collapse."""
    points=np.asarray(points,float);axes=occupancy['axes'];solid=occupancy['solid']
    lows=[];highs=[];fractions=[];supported=np.ones(len(points),bool)
    for dim,axis in enumerate(axes):
        values=points[:,dim];hi=np.clip(np.searchsorted(axis,values),0,len(axis)-1)
        lo=np.clip(hi-1,0,len(axis)-1);lo=np.where(values==axis[hi],hi,lo)
        f=np.divide(values-axis[lo],axis[hi]-axis[lo],out=np.zeros(len(points)),where=hi!=lo)
        supported &= (values>=axis[0])&(values<=axis[-1])
        lows.append(lo);highs.append(hi);fractions.append(f)
    indices=[];weights=[]
    for corner in product((0,1),repeat=3):
        xyz=[highs[d] if high else lows[d] for d,high in enumerate(corner)]
        w=np.ones(len(points))
        for d,high in enumerate(corner):
            w*=fractions[d] if high else 1-fractions[d]
        indices.append(np.column_stack(xyz[::-1]));weights.append(np.where(supported,w,0.))
    indices=np.stack(indices,axis=1);weights=np.stack(weights,axis=1)
    active=weights>0
    touched=solid[tuple(indices.transpose(2,0,1))]
    solid_weight=np.sum(weights*touched,axis=1)
    wall=np.zeros_like(active);opposed=np.zeros((*active.shape,3),bool)
    for dim,n in enumerate(solid.shape):
        neighbours=[]
        for sign in (-1,1):
            at=indices.copy();at[:,:,dim]+=sign
            inside=(at[:,:,dim]>=0)&(at[:,:,dim]<n)
            at[:,:,dim]=np.clip(at[:,:,dim],0,n-1)
            value=inside&solid[tuple(at.transpose(2,0,1))]
            # The removed flat-ground ghost is solid and has an active wall treatment.
            if dim==0 and sign==-1:value |= indices[:,:,0]==0
            neighbours.append(value);wall |= value
        opposed[:,:,dim]=neighbours[0]&neighbours[1]
    # TURBGeneralData computes the interior, excluding lateral and highest shells.
    computed=~touched
    for dim,n in enumerate(solid.shape):
        computed &= indices[:,:,dim] < n-1
        if dim!=0:computed &= indices[:,:,dim]>0
    return dict(indices=indices,weights=weights,active=active,supported=supported,
        valid=supported&~np.any(active&touched,axis=1),
        covered=supported&~np.any(active&~computed,axis=1),
        solid_weight=solid_weight,solid_contributors=np.sum(active&touched,axis=1),
        contributors=np.sum(active,axis=1),
        wall_weight=np.sum(weights*wall*~touched,axis=1),
        opposing_x_weight=np.sum(weights*opposed[:,:,2]*~touched,axis=1),
        opposing_y_weight=np.sum(weights*opposed[:,:,1]*~touched,axis=1))
