"""Replay existing native captures, launching zero wind solves.

Usage: python tools/replay_geometry_v2.py ARCHIVE_ROOT --output receipt.json
ARCHIVE_ROOT contains A---2m/capture, B---2m/capture, D---2m/capture,
and E-after-2m/capture from the closed coarse-geometry campaign.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np
from dtcc_qes.geometry import _polygons, _slice


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=[]
    for name in ('A---2m','B---2m','D---2m','E-after-2m'):
        folder=args.archive/name/'capture'
        recipe=folder/'recipe.txt';mask=folder/'native-mask.bin'
        lines=recipe.read_text().splitlines()
        arrays=[np.fromstring(line,sep=' ')[1:] for line in lines[3:10]]
        dz,vertices,offsets,ids,roofs,bases,ring_offsets=arrays
        prepared=SimpleNamespace(arrays=dict(vertices=vertices.reshape(-1,2),offsets=offsets.astype(int),
            heights=roofs,base_heights=bases))
        if ring_offsets.size:prepared.arrays['ring_offsets']=ring_offsets.astype(int)
        with mask.open('rb') as stream:
            shape=tuple(np.fromfile(stream,np.uint32,count=3).astype(int))
            faces=np.fromfile(stream,np.float32,count=shape[0]+1)
            solid=np.fromfile(stream,np.uint8).reshape(shape)
        spacing=float(lines[0].split()[3]);nz,ny,nx=shape
        grid=SimpleNamespace(x=(np.arange(nx,dtype=np.float32)+.5)*spacing,
            y=(np.arange(ny,dtype=np.float32)+.5)*spacing,z=(faces[:-1]+faces[1:])*.5,
            z_faces=faces,resolution=spacing)
        started=time.monotonic()
        row=_slice(_polygons(prepared),bases,roofs,[[str(int(i))] for i in ids],grid,1.5,
            np.empty((0,2)),np.empty((0,2,2)),np.where(solid,0,1),started+30,4096)
        rows.append(dict(name=name,recipe_sha256=hashlib.sha256(recipe.read_bytes()).hexdigest(),
            mask_sha256=hashlib.sha256(mask.read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-started,
            result=row))
    payload=dict(schema_version=1,new_wind_solves=0,rows=rows)
    args.output.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')
    print([(r['name'],r['result']['status'],r['result']['reason'],len(r['result']['witnesses'])) for r in rows])

if __name__=='__main__':main()
