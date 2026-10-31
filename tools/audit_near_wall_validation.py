"""Audit archived raw-face diagnostics without retained build executables.

Load the frozen analysis sources, verify raw face-to-centre arithmetic and
incident-cell flags independently, and reproduce the saved summary exactly.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np


def check_patch(patch):
    cells={tuple(r["position"]):r for r in patch["cells"]}
    axes=[sorted({p[d] for p in cells}) for d in range(3)]
    count=0
    for component,rows in enumerate(patch["faces"]):
        faces={tuple(r["position"]):r for r in rows}
        if len(faces)!=len(rows): raise ValueError("Duplicate native face")
        normal=sorted({p[component] for p in faces})
        for p,cell in cells.items():
            hi=int(np.searchsorted(normal,p[component]))
            if hi==0 or hi==len(normal): raise ValueError("Missing centring face")
            pair=[]
            for value in normal[hi-1:hi+1]:
                key=list(p); key[component]=value
                pair.append(faces[tuple(key)]["value"])
            expected=float(np.float32(.5)*(np.float32(pair[0])+np.float32(pair[1])))
            if expected != cell["velocity"][component]:
                raise ValueError("Native face averaging does not reproduce cell component")
            count+=1
        for p,face in faces.items():
            hi=int(np.searchsorted(axes[component],p[component]))
            for index,side in ((hi-1,0),(hi,1)):
                if 0<=index<len(axes[component]):
                    key=list(p); key[component]=axes[component][index]
                    if tuple(key) in cells and cells[tuple(key)]["flag"]!=face["flags"][side]:
                        raise ValueError("Incident-cell face flag disagrees with native cell")
    return count


def audit(output):
    # Isolated CLI process imports only snapshotted study helpers. The artifact
    # audit remains usable after active source changes or removal of build/.
    sys.path.insert(0,str((output/"sources/tools").resolve()))
    import run_near_wall_validation as study
    old=study.read(output/"summary.json")
    # Recompute without replacing the evidence being checked.
    writer=study.atomic_json
    study.atomic_json=lambda *_args, **_kwargs: None
    try:
        current=study.summarize(output)
    finally:
        study.atomic_json=writer
    if current!=old: raise ValueError("Saved summary differs from frozen analysis")
    manifest=study.read(output/"manifest.json")
    checks=0
    for task in manifest["tasks"]:
        saved=study.read(output/"cases"/(task["id"]+".json.gz"))
        for stage in saved["run"]["stages"].values():
            for patch in stage["patches"]: checks+=check_patch(patch)
    result=dict(complete=current["complete"],cases=current["cases"],native_component_checks=checks,
        summary_sha256=study.digest(output/"summary.json"),manifest_sha256=study.digest(output/"manifest.json"),
        audit_source_sha256=study.digest(__file__),requires_worker_executable=False,
        cpu_initial_fields_exact=all(r["initial_exact"] for r in current["cross_backend"]),
        max_cpu_final_vector_difference_over_Uref=max(r["max_final_vector_difference_over_Uref"] for r in current["cross_backend"]),
        max_archive_plane_difference=max(r["max_plane_difference"] for r in current["parity"]),
        max_patch_reconstruction_difference=max(r["max_patch_reconstruction_difference"] for r in current["parity"]))
    study.atomic_json(output/"audit.json",result)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("docs/data/near-wall-validation"))
    audit(parser.parse_args().output)
