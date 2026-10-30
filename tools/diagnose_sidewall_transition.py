"""Exploratory source-based explanation of one fixed near-wall initial stencil.

Reproduce Sidewall.cpp's branches for the 7.9 m, 12 m wide block at x=22,
y=22 and 270-degree wind. This is not a replacement physical model or solve.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from run_joint_grid_verification import atomic_json, read


def scales():
    # Preserve the native float storage at each assigned geometric scale.
    h=np.float32(7.9); width=np.float32(12)
    scale=np.float32(float(h)**(2/3)*float(width)**(1/3))
    length=np.float32(.9*float(scale)); half_width=np.float32(.11*float(scale))
    pref=np.float32(float(half_width)/np.sqrt(.5*float(length)))
    x=np.float32(5)  # fixed point x=27, building leading edge x=22
    shell_factor=np.float32(1-((.5*float(length)-float(x))/(.5*float(length)))**2)
    shell=np.float32(float(half_width)*np.sqrt(float(shell_factor)))
    internal=np.float32(float(pref)*np.sqrt(float(x)))
    return dict(shell=float(shell),internal=float(internal),half_width=float(half_width),roughness=.1)


def initialized_ratio(distance, constants=None):
    c=scales() if constants is None else constants
    eta=abs(distance)
    if eta<=c["shell"]:
        return -(c["shell"]-eta)/c["half_width"]
    if eta<=c["internal"]:
        return np.log((eta+c["roughness"])/c["roughness"])/np.log((c["internal"]+c["roughness"])/c["roughness"])
    return 1.


def main():
    root=Path("docs/data/near-wall-validation")
    rows=[]; hashes={}
    for resolution in (1,.5,.25):
        path=root/"cases/openmp/auto/270"/f"{resolution:g}/0/0.json.gz"
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        run=read(path)["run"]
        initial=run["stages"]["initial"]["patches"][0]
        profile={tuple(r["position"]):r["value"] for r in run["stages"]["profile"]["patches"][0]["faces"][0]}
        # At z=1.5 (an actual auto-grid centre), retain native u faces x=27
        # surrounding the 1 m wall distance. Coordinates include origin +40.
        for face in initial["faces"][0]:
            x,y,z=face["position"]
            if x!=67 or z!=1.5 or not .4<=62-y<=1.6: continue
            observed=face["value"]/profile[tuple(face["position"])]
            predicted=initialized_ratio(62-y)
            rows.append(dict(resolution=resolution,distance_from_wall=62-y,
                initialized_u_over_profile_u=observed,source_formula_ratio=float(predicted),difference=float(observed-predicted)))
    maximum=max(abs(r["difference"]) for r in rows)
    if maximum>2e-6: raise ValueError("Source branch reconstruction does not match exported native faces")
    c=scales()
    result=dict(scope="exploratory initialization explanation at (27,21); not a solved refinement or accuracy criterion",
        geometry=dict(height=7.9,width=12,streamwise_distance=5,wall_distance=1),scales=c,
        raw_face_checks=rows,max_ratio_disagreement=maximum,
        shell_outer_limit_ratio=float(np.log((c["shell"]+.1)/.1)/np.log((c["internal"]+.1)/.1)),
        shell_inner_limit_ratio=0.,point_to_shell_distance=1-c["shell"],
        spacing_to_keep_this_aligned_stencil_outside_shell=2*(1-c["shell"]),
        exact_branch_ratio_at_point=float(initialized_ratio(1)),
        input_sha256=hashes,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__),Path("QES-Public/src/winds/Sidewall.cpp"))})
    atomic_json(root/"sidewall-transition.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("raw_face_checks","input_sha256","source_sha256")},indent=2))


if __name__=="__main__":
    main()
