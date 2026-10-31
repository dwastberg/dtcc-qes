"""Exploratory source reconstruction of the two new initialization hotspots.

Reconstruct only the selected outer upwind-cavity branch; do not change the
model or certify rejected solutions. Freeze sources separately from the main
predeclared study, because this diagnosis follows the observed local failure.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys

import numpy as np

SOURCES=('tools/diagnose_vertical_initialization.py',
    'QES-Public/src/winds/UpwindCavity.cpp',
    'QES-Public/src/winds/WINDSGeneralData.cpp',
    'QES-Public/src/winds/WindProfilerSensorType.cpp')


def scales():
    height=np.float32(7.9)
    return np.float32(18/(1+.8*12/float(height))),np.float32(np.float32(.6)*height)


def profile(z):
    rough=np.float32(.1)
    return np.float32(5/np.log(float(np.float32((np.float32(10)+rough)/rough)))*
        np.log(float(np.float32((np.float32(z)+rough)/rough))))


def face_value(x,y,z,building_y):
    length,height=scales()
    streamwise=np.float32(x-22);lateral=np.float32(y-building_y-6)
    radius=np.float32(float(length)*np.sqrt((1-float(np.float32(lateral/np.float32(6)))**2)*
                                           (1-float(np.float32(z/height))**2)))
    if not -streamwise>np.float32(.4*radius):
        raise ValueError('Selected reconstruction reached the inner vortex branch')
    return np.float32(profile(z)*np.float32(.4)) if -streamwise<=radius else profile(z)


def predicted_K(faces,height,point):
    f=np.asarray(faces,np.float32);centres=np.float32(.5)*(f[:-1]+f[1:])
    hi=int(np.searchsorted(centres,height));lo=hi if centres[hi]==height else hi-1
    weight=0 if lo==hi else (height-float(centres[lo]))/float(centres[hi]-centres[lo])
    total=0.;building_y=42 if point[1]==47 else 22
    for k,w in ((lo,1-weight),(hi,weight)):
        for x in (point[0]-.25,point[0]+.25):
            for y in (point[1]-.25,point[1]+.25):
                left=face_value(x-.25,y,centres[k],building_y)
                right=face_value(x+.25,y,centres[k],building_y)
                total+=w*.25*float(np.float32(.5)*np.float32(left+right))
    return total/5


def vector(study,run,height,point,stage):
    p=study.audit_point(run,height,point,stage)
    if not p['valid']:raise ValueError('Diagnostic point has invalid support')
    return sum((c['weight']*np.asarray(c['velocity']) for c in p['corners']),np.zeros(3))


def analyze(root):
    sys.path.insert(0,str((root/'sources/tools').resolve()))
    import run_vertical_refinement as study
    manifest=study.read(root/'manifest.json')
    refs,_=study.reference_data(manifest['references_sha256'])
    raw=study.read(root/'raw.json.gz')
    runs={'base':refs['openmp']['base']}
    inputs=[root/'manifest.json',root/'raw.json.gz',study.PILOT/'raw.json.gz']
    for family in study.FAMILIES:
        paths=sorted((root/'openmp/checkpoints/vertical'/family/'160/270/0.5').glob('*.json.gz'))
        if not paths:raise ValueError('Missing initialized field for declared family')
        inputs.append(paths[0]);runs[family]=study.read(paths[0])['run']
    checks=[]
    for family,run in runs.items():
        for h in study.HEIGHTS:
            for point in ([15,47],[15,29]):
                actual=study.audit_point(run,h,point,'initial')['K']
                predicted=predicted_K(manifest['configurations'][family]['expected_faces'],h,point)
                checks.append(dict(family=family,height=h,point=point,initialized_K=actual,
                    source_formula_K=predicted,difference=predicted-actual))
    maximum=max(abs(c['difference']) for c in checks)
    if maximum>2e-6:raise ValueError('Source reconstruction disagrees with archived initialized fields')
    accepted={r['task']['family']:r for r in raw['openmp']['runs'] if study.gate(r)['accepted']}
    decompositions=[];base=refs['openmp']['base']
    for family,run in accepted.items():
        for h in study.HEIGHTS:
            for point in ([15,47],[15,29]):
                profile_delta=vector(study,run,h,point,'profile')-vector(study,base,h,point,'profile')
                initial_delta=vector(study,run,h,point,'initial')-vector(study,base,h,point,'initial')
                final_delta=vector(study,run,h,point,'final')-vector(study,base,h,point,'final')
                correction_delta=final_delta-initial_delta
                decompositions.append(dict(family=family,height=h,point=point,
                    profile_vector_delta=profile_delta.tolist(),initial_vector_delta=initial_delta.tolist(),
                    projection_correction_delta=correction_delta.tolist(),final_vector_delta=final_delta.tolist(),
                    interpretation='new minus base; vector identity, not sole-local-causality proof'))
    length,height=scales();boundaries=[]
    for lateral in (-1.25,-.75):
        radius=float(length)*np.sqrt(1-(lateral/6)**2)
        z=float(height)*np.sqrt(1-(7.5/radius)**2)
        boundaries.append(dict(world_face_x=14.5,world_face_y=48+lateral,outer_boundary_height=z))
    return dict(scope='Exploratory source-branch diagnosis after observed base-to-2 failures; no acceptance changes or physical validation',
        source_sha256={name:study.digest(root/'initialization-sources'/name) for name in SOURCES},
        input_sha256={str(p):study.digest(p) for p in inputs},
        scales=dict(cavity_length=float(length),cavity_height=float(height),inside_profile_factor=float(np.float32(.4)),outside_profile_factor=1.),
        outer_boundaries=boundaries,initialized_checks=checks,max_initialized_K_disagreement=maximum,
        accepted_final_decompositions=decompositions,uncertified_finals_used=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('docs/data/vertical-refinement'))
    parser.add_argument('--freeze-sources',action='store_true')
    parser.add_argument('--audit',action='store_true')
    args=parser.parse_args();root=args.output
    if args.freeze_sources:
        for name in SOURCES:
            target=root/'initialization-sources'/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(name,target)
    import json
    report=analyze(root)
    path=root/'initialization.json'
    if args.audit:
        saved=json.loads(path.read_text())
        own=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if own!=saved['source_sha256'][SOURCES[0]] or report!=saved:
            raise ValueError('Initialization diagnosis differs from frozen sources or inputs')
    else:
        from run_joint_grid_verification import atomic_json
        atomic_json(path,report)
    print(json.dumps(dict(checks=len(report['initialized_checks']),max_K_disagreement=report['max_initialized_K_disagreement'],
        accepted_final_decompositions=len(report['accepted_final_decompositions']),audit=args.audit),indent=2))


if __name__=='__main__':main()
