"""Publish S7 inputs, compact outputs, source identities and verification logs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from run_solver_numerics import digest,write
from audit_solver_policy import audit


def fingerprints(out):
    report=json.loads((out/'final-default-parity.json').read_text());names=set()
    # The comparator names the archive by its source SHA prefix.
    for sha in [report['baseline_revision'].split(':')[1],report['candidate'].split(':')[1]]:
        for backend,teams in [('openmp',[1,2,4,8]),('serial',[1])]:
            for team in teams:names.add(f'archive-{sha[:12]}-{backend}-{team}threads.npz')
    result={}
    for name in sorted(names):
        path=out/'default-parity/results'/name
        with np.load(path,allow_pickle=False) as v:
            members={};normalized={}
            for key in v.files:
                array=v[key]
                members[key]=dict(shape=list(array.shape),dtype=array.dtype.str,sha256=hashlib.sha256(array.tobytes()).hexdigest())
                if key=='_module':continue
                if key.endswith('/metadata/versions/native_build/scalars') or key.endswith('/metadata/model/scalars'):
                    scalar=json.loads(str(array));scalar.pop('openmp_enabled' if key.endswith('/metadata/versions/native_build/scalars') else 'backend',None)
                    array=np.array(json.dumps(scalar,sort_keys=True))
                normalized[key]=dict(shape=list(array.shape),dtype=array.dtype.str,sha256=hashlib.sha256(array.tobytes()).hexdigest())
        result[name]=dict(archive_sha256=digest(path),members=members,backend_independent_members=normalized)
    return result


def publish(out,destination):
    if destination.exists() or out==destination or out in destination.parents:raise ValueError('Publication requires a fresh destination outside the study')
    destination.mkdir(parents=True)
    skip={'tree','calibration-tree','calibration-native','native','serial','sanitizers','package','package-final',
          'release-package','release-serial-package','default-parity','legacy-study-compatibility','__pycache__'}
    for path in out.rglob('*'):
        rel=path.relative_to(out)
        if not path.is_file() or rel.parts[0] in skip or '__pycache__' in rel.parts or path.suffix=='.pyc':continue
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    validation=destination/'validation';validation.mkdir(exist_ok=True)
    shutil.copyfile(out/'final-default-parity.json',validation/'default-parity.json')
    write(validation/'default-array-fingerprints.json',fingerprints(out))
    shutil.copyfile(out/'native/solver-policy-identity.txt',validation/'solver-policy-identity.txt')
    for backend in ['native','serial','sanitizers']:
        target=validation/backend;target.mkdir(exist_ok=True)
        for name in ['CMakeCache.txt','solver-policy-identity.txt']:
            shutil.copyfile(out/backend/name,target/name)
        compiler=list((out/backend/'CMakeFiles').glob('*/CMakeCXXCompiler.cmake'))
        if len(compiler)!=1:raise ValueError('Compiler record missing')
        shutil.copyfile(compiler[0],target/'CMakeCXXCompiler.cmake')
    # Every worker independently recorded the imported binary SHA. Bind these
    # to the retained build/compiler context without shipping platform binaries.
    write(validation/'executables.json',dict(
        openmp=digest(next((out/'native').glob('_qes*.so'))),serial=digest(next((out/'serial').glob('_qes*.so'))),
        calibration_probe=digest(out/'calibration-native/solver_numerics_probe')))
    root=Path(__file__).resolve().parents[1]
    for name in ['audit_solver_policy.py','publish_solver_policy.py','run_solver_policy_study.py','validate_solver_policy.py','calibrate_solver_policy.py','run_solver_numerics.py','reproduce_solver_policy.py','compare_native_builds.py']:
        shutil.copyfile(root/'tools'/name,destination/name)
    # Preserve the exact frozen prediction source, rather than a later live edit.
    shutil.copyfile(out/'solver_policy_replay.py',destination/'solver_policy_replay.py')
    for path in sorted(root.glob('build/solver-control-s7-*.log')):
        shutil.copyfile(path,validation/path.name)
    summary=audit(destination,verify_manifest=False);write(destination/'summary.json',summary)
    files={p.relative_to(destination).as_posix():digest(p) for p in destination.rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(destination/'manifest.json',dict(stage='S7',files=files,
        limitation='Full default fields retained in original build/ study; portable default parity uses per-array hashes. Full compact planes/receptors retained for numerical error and policy replay.'))
    audit(destination)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['records','budgets']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();publish(a.study.resolve(),a.output.resolve())
