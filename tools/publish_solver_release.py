"""Publish compact S9 evidence; keep binaries/full matrices in the build record."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

from audit_solver_release import audit,digest,read,validate_summary
from benchmark_prepared_wind import write

ROOT=Path(__file__).resolve().parents[1]


def publish(study,destination):
    validation=read(study/'validation.json');scope=read(ROOT/'docs/data/solver-control-s9/scope.json')
    validate_summary(validation,scope)
    destination.mkdir(parents=True,exist_ok=True)
    if any(p.name!='scope.json' for p in destination.iterdir()):raise ValueError('Refusing to replace published S9 evidence')
    for p in study.iterdir():
        if p.is_file() and (p.suffix in ('.json','.xml') or p.name.endswith('-sources.tar.gz') or p.name=='sources.tar.gz'):
            shutil.copyfile(p,destination/p.name)
    for directory in ['logs','policy','parity']:
        for p in (study/directory).iterdir():
            if not p.is_file() or p.suffix not in ('.json','.log','.npz'):continue
            if directory=='parity' and p.suffix=='.npz':continue
            target=destination/directory/p.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(p,target)
    for backend in ['openmp','serial','sanitizers']:
        target=destination/'builds'/backend;target.mkdir(parents=True)
        for name in ['CMakeCache.txt','solver-policy-identity.txt','ctest.xml']:
            shutil.copyfile(study/backend/name,target/name)
        compiler=list((study/backend/'CMakeFiles').glob('*/CMakeCXXCompiler.cmake'))
        if len(compiler)!=1:raise ValueError('Compiler metadata missing')
        shutil.copyfile(compiler[0],target/'CMakeCXXCompiler.cmake')
    campaigns={}
    for name in ['first','reuse','repair']:
        folder=study/('campaign-'+name);target=destination/'campaign'/name;target.mkdir(parents=True)
        for file in ['campaign.json','builds.json','results.json','results.txt']:
            shutil.copyfile(folder/file,target/file)
        shutil.copyfile(folder/'fixtures/protocol.json',target/'fixtures-protocol.json')
        # Bind every prior outcome, including independently measured raw rows.
        campaigns[name]={p.relative_to(folder).as_posix():digest(p) for p in folder.rglob('*') if p.is_file()}
    write(destination/'campaign/outcome-files.json',campaigns)
    write(destination/'executables.json',dict(
        openmp=digest(next((study/'openmp').glob('_qes*.so'))),serial=digest(next((study/'serial').glob('_qes*.so'))),
        policy_revision=validation['native_policy_revision'],
        artifacts=validation['checks']['artifacts'],
        retained_full_matrices=str(study/'parity'),retained_packages=str(study/'artifacts')))
    for name in ['audit_solver_release.py','validate_solver_release.py','publish_solver_release.py','wheel_runtime_smoke.py']:
        shutil.copyfile(ROOT/'tools'/name,destination/name)
    for name in ['benchmark_prepared_wind.py','compare_native_builds.py','profile_solver_baseline.py']:
        shutil.copyfile(ROOT/'tools'/name,destination/name)
    source_members={}
    for p in destination.glob('*sources.tar.gz'):
        with tarfile.open(p) as a:
            source_members[p.name]={m.name:hashlib.sha256(a.extractfile(m).read()).hexdigest() for m in a.getmembers() if m.isfile()}
    files={p.relative_to(destination).as_posix():digest(p) for p in sorted(destination.rglob('*'))
           if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    write(destination/'manifest.json',dict(stage='S9',schema='solver-control-release-v1',files=files,sources=source_members,
        scope='qualified pedestrian solver-control refactor; S8b explicitly deferred',
        full_volume_artifacts='Raw default NPZ matrices and distribution files retained under recorded build paths; portable evidence retains every numerical member fingerprint and artifact SHA.'))
    result=audit(destination,ROOT/'docs/data');print(json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();publish(args.study.resolve(),args.output.resolve())
