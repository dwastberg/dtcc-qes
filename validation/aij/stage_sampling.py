"""Capture the exact cells needed by the canonical linear/fallback sampler.

Containing-cell stage values can be poor substitutes for interpolated probes
near walls. This adapter captures all linear contributors and the canonical
nearest-fluid neighbourhood, then calls the *same* sampler at every stage.
"""
from dataclasses import replace
from itertools import product
import numpy as np
from dtcc_qes import wind
from .sampling import probe_sample,_offsets


class StageSampler:
    def __init__(self,xyz):
        self.xyz=np.array(xyz,dtype=float,copy=True)
        if self.xyz.ndim != 2 or self.xyz.shape[1] != 3 or not np.isfinite(self.xyz).all():
            raise ValueError('Stage probes must be finite coordinates shaped (n, 3)')
        self.cells=None

    def __call__(self,geometry,prepared):
        nz,ny,nx=prepared.domain['shape']; h=prepared.resolution
        axes=[(np.arange(nx)+.5)*h,(np.arange(ny)+.5)*h,wind._layer_heights(prepared)]
        points=self.xyz-np.asarray(prepared.origin)
        queries=np.concatenate([points+offset for offset in _offsets(h,h*np.sqrt(2))])
        brackets=[]
        for dim,axis in enumerate(axes):
            hi=np.clip(np.searchsorted(axis,queries[:,dim]),0,len(axis)-1)
            lo=np.maximum(hi-1,0)
            # Include both linear contributors and every nearest candidate;
            # duplicate cells are removed before asking native code to copy.
            brackets.append((lo,hi))
        cells=np.concatenate([np.column_stack([brackets[d][corner[d]] for d in range(3)])
                              for corner in product((0,1),repeat=3)])
        self.cells=np.unique(cells,axis=0)
        return self.cells.tolist()

    def sample(self,result):
        if self.cells is None: raise ValueError('Prepare stage contributors before sampling')
        e=result.metadata['experiment']; ijk=self.cells
        stages=e['stages']
        if len(set(stages)) != len(stages) or 'projection' not in stages:
            raise ValueError('Captured stages must be unique and include projection')
        if (np.shape(e['stage_velocity']) != (len(stages),len(ijk),3)
                or np.shape(e['stage_flags']) != (len(stages),len(ijk))):
            raise ValueError('Captured stage arrays do not match stages and contributors')
        if 'stage_cells' in e and not np.array_equal(ijk,e['stage_cells']):
            raise ValueError('Captured stage contributors differ from requested cells')
        dense=np.full_like(result.velocity,np.nan); flags=np.zeros_like(result.cell_flags)
        keys=tuple(ijk[:,d] for d in (2,1,0))
        view=replace(result,velocity=dense,cell_flags=flags,turbulence=None)
        samples=[]
        for velocity,stage_flags in zip(e['stage_velocity'],e['stage_flags']):
            dense[keys]=velocity; flags[keys]=stage_flags
            samples.append(probe_sample(view,self.xyz))
        final=probe_sample(result,self.xyz)
        index=e['stages'].index('projection')
        if not np.array_equal(samples[index]['velocity'],final['velocity'],equal_nan=True):
            raise ValueError('Stage projection does not reproduce canonical final receptor vectors')
        if not np.array_equal(samples[index]['method'],final['method']):
            raise ValueError('Stage projection changed canonical interpolation/fallback methods')
        return dict(stages=e['stages'],velocity=np.stack([s['velocity'] for s in samples]),
            speed=np.stack([s['speed'] for s in samples]),method=np.stack([s['method'] for s in samples]),
            cells=self.cells,final_bitwise_parity=True,
            scope='Canonical aij.sampling.probe_sample on exact captured contributors at every native stage')
