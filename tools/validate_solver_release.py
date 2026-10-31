"""Stage and validate the scoped S9 release without altering prior outcomes.

Run with --output NEW_DIRECTORY. Checks can also be selected individually after
staging; every command attempt has its own log and retained result record.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import time
import uuid
import xml.etree.ElementTree as ET

from audit_solver_release import digest,read,require,REQUIRED
from benchmark_prepared_wind import write,comparable
from compare_native_builds import stage_package,evaluate,compare_results

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE','PYTHONDONTWRITEBYTECODE':'1'}


def command(out,name,cmd,*,env=None,cwd=None,timeout=240):
    logs=out/'logs';logs.mkdir(exist_ok=True)
    log=logs/f'{name}-{uuid.uuid4().hex[:8]}.log';started=time.monotonic()
    print(name,flush=True)
    with log.open('w') as stream:
        try:
            r=subprocess.run([str(v) for v in cmd],cwd=cwd,env=env or ENV,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            code=r.returncode
        except subprocess.TimeoutExpired:code=124
    path=out/'commands.json';rows=read(path) if path.exists() else []
    rows.append(dict(name=name,command=[str(v) for v in cmd],cwd=str(cwd or ROOT),timeout_seconds=timeout,
        elapsed_seconds=time.monotonic()-started,returncode=code,log=log.relative_to(out).as_posix()))
    write(path,rows)
    if code:raise RuntimeError(f'{name} failed ({code}); see {log}')
    return log


def stage(out):
    out.mkdir(parents=True,exist_ok=False);tree=out/'tree';tree.mkdir()
    parent=ROOT/'docs/data/solver-control-s8a/sources.tar.gz'
    expected=read(ROOT/'docs/data/solver-control-s8a/manifest.json')['files']['sources.tar.gz']
    require(digest(parent)==expected,'Changed S8a parent sources')
    with tarfile.open(parent) as a:a.extractall(tree,filter='data')
    # Native/Python runtime is exactly the frozen parent. Only provenance text
    # changes; reject unrelated moving runtime sources rather than absorbing them.
    for p in (tree/'src').rglob('*'):
        rel=p.relative_to(tree)
        if p.is_file() and p.suffix in ('.h','.cpp','.py'):
            require(p.read_bytes()==(ROOT/rel).read_bytes(),'Unreviewed runtime change: '+str(rel))
    overlays=[]
    for directory in ['tests','tools','examples','demo']:
        for p in (ROOT/directory).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
            rel=p.relative_to(ROOT);target=tree/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target);overlays.append(rel.as_posix())
    for p in sorted((ROOT/'docs').glob('*.md')):
        shutil.copyfile(p,tree/'docs'/p.name);overlays.append('docs/'+p.name)
    for rel in ['README.md','DYNAMIC_VERTICAL_GRID.md','SOLVER_CONTROL_REFACTOR.md','pyproject.toml','uv.lock','src/qes_core/PROVENANCE.md']:
        shutil.copyfile(ROOT/rel,tree/rel);overlays.append(rel)
    scope=tree/'docs/data/solver-control-s9/scope.json';scope.parent.mkdir(parents=True)
    shutil.copyfile(ROOT/'docs/data/solver-control-s9/scope.json',scope)
    write(out/'source-parent.json',dict(parent_archive_sha256=expected,runtime_changes=[],reviewed_overlays=sorted(overlays),
        excluded=['unrelated root architecture proposals','live data/','build/','.venv/','reference-only QES-Public/']))
    # Source snapshot excludes the large immutable evidence bundles; packaging
    # below materializes them separately and records every original manifest.
    index={p.relative_to(tree).as_posix():digest(p) for p in tree.rglob('*') if p.is_file()}
    write(out/'source-index.json',index)
    with tarfile.open(out/'sources.tar.gz','w:gz') as a:
        for rel in sorted(index):a.add(tree/rel,arcname=rel,recursive=False)
    # Read-only hard-linked evidence inputs avoid another 1.4GB copy. No check
    # mutates these paths; all workers/results use fresh output directories.
    for p in (ROOT/'docs/data').iterdir():
        if p.name=='solver-control-s9':continue
        if p.is_dir():shutil.copytree(p,tree/'docs/data'/p.name,copy_function=os.link,
            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        elif p.is_file():os.link(p,tree/'docs/data'/p.name)
    prior={p.parent.name:dict(manifest_sha256=digest(p)) for p in sorted((ROOT/'docs/data').glob('solver-control-*/manifest.json')) if p.parent.name!='solver-control-s9'}
    write(out/'prior-evidence.json',prior)
    write(out/'environment.json',dict(python=sys.version,soabi=sysconfig.get_config_var('SOABI'),machine=platform.machine(),platform=platform.platform(),
        numpy=__import__('numpy').__version__,builds='Release; AppleClang/host compiler identities retained per CMake build',utc=datetime.now(timezone.utc).isoformat()))
    write(out/'validation.json',dict(checks={},native_policy_revision=read(ROOT/'docs/data/solver-control-s9/scope.json')['policy']['native_revision']))


def native(out):
    tree=out/'tree'
    for backend,flag in [('openmp','ON'),('serial','OFF'),('sanitizers','OFF')]:
        folder=out/backend
        cmd=['cmake','-S',tree,'-B',folder,'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}',
             '-DDTCC_QES_BUILD_TESTS=ON',f'-DDTCC_QES_OPENMP={flag}']
        if backend=='sanitizers':cmd.append('-DDTCC_QES_ENABLE_SANITIZERS=ON')
        command(out,backend+'-configure',cmd)
        targets=['--target','check_runner','check_monitor','check_solver_control','check_equation_residual','check_solver_phases','check_pedestrian_policy'] if backend=='sanitizers' else []
        command(out,backend+'-build',['cmake','--build',folder,*targets,'-j8'])
        test=['ctest','--test-dir',folder,'--output-on-failure','--output-junit',folder/'ctest.xml','-j1']
        if backend=='sanitizers':test+=['-R','^(runner_lifecycle|solver_monitor|solver_control|equation_residual|solver_phases|pedestrian_policy)$']
        command(out,backend+'-tests',test,timeout=300)
        if backend!='sanitizers':
            command(out,backend+'-symbols',['cmake','--build',folder,'--target','check_native_symbols'])
            stage_package(tree,next(folder.glob('_qes*.so')),out/(backend+'-package'))
    counts={b:len(ET.parse(out/b/'ctest.xml').findall('.//testcase')) for b in ['openmp','serial','sanitizers']}
    identities={b:digest(out/b/'solver-policy-identity.txt') for b in ['openmp','serial','sanitizers']}
    require(identities['openmp']==read(out/'validation.json')['native_policy_revision'],'Release native identity changed')
    return dict(passed=True,test_counts=counts,policy_identity=identities)


def python(out):
    package=out/'openmp-package'
    command(out,'full-python',[sys.executable,'-m','pytest',out/'tree/tests','-q','--junitxml',out/'python.xml'],
        cwd=out/'tree',env=ENV|{'PYTHONPATH':str(package),
            'DTCC_QES_NATIVE_TEST':str(out/'openmp/check_safety'),
            'DTCC_QES_RUNNER_TEST':str(out/'openmp/check_runner'),
            'DTCC_QES_PHYSICS_TEST':str(out/'openmp/check_physics'),
            'DTCC_QES_MONITOR_EXECUTABLE':str(out/'openmp/check_monitor'),
            'DTCC_QES_STUDY_EXECUTABLE':str(out/'openmp/vertical_grid_study')},timeout=1200)
    suite=ET.parse(out/'python.xml').getroot().find('testsuite')
    require(int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0,'Python suite failed')
    return dict(passed=True,tests=int(suite.attrib['tests']),skipped=int(suite.attrib['skipped']))


def parity(out):
    target=out/'parity';target.mkdir(exist_ok=False)
    baseline=ROOT/'build/solver-control-s7/default-parity/results'
    # Use the previously frozen exact S5c matrices when locally retained. A
    # fresh checkout rebuilds both revisions with the original comparator.
    names=[f'archive-f138616b7796-{b}-{n}threads.npz' for b,teams in [('openmp',[1,2,4,8]),('serial',[1])] for n in teams]
    fresh_baseline=not all((baseline/name).exists() for name in names)
    if fresh_baseline:
        command(out,'full-default-parity',[sys.executable,out/'tree/tools/compare_native_builds.py','--baseline-archive',ROOT/'docs/data/solver-control-s5/sources.tar.gz',
            '--candidate-archive',out/'sources.tar.gz','--thread-counts','1','2','4','8','--require-backend-parity','--report',target/'report.json','--work-dir',target/'full'],timeout=1200)
        baseline=target/'full/results'
    report=dict(passed=True,baseline_revision='sha256:'+digest(ROOT/'docs/data/solver-control-s5/sources.tar.gz'),candidate='sha256:'+digest(out/'sources.tar.gz'),comparisons=[])
    results={};fingerprints={};normalized={}
    import numpy as np
    for backend,teams in [('openmp',[1,2,4,8]),('serial',[1])]:
        for team in teams:
            path=target/f'{backend}-{team}.npz'
            if fresh_baseline:
                os.link(baseline/f"archive-{digest(out/'sources.tar.gz')[:12]}-{backend}-{team}threads.npz",path)
                cases=429
            else:cases=evaluate(out/(backend+'-package'),path,team)
            require(cases==429,'Incomplete default matrix')
            base=baseline/f'archive-f138616b7796-{backend}-{team}threads.npz'
            diffs,records=compare_results(base,path)
            require(not diffs,'Default field/diagnostic/metadata differences: '+str(diffs[:3]))
            report['comparisons'].append(dict(kind='revision',backend=backend,threads=team,cases=cases,records=records,differences=diffs,required=True))
            results[backend,team]=path
            with np.load(path,allow_pickle=False) as data:
                fingerprints[path.name]={k:dict(dtype=data[k].dtype.str,shape=list(data[k].shape),sha256=hashlib.sha256(data[k].tobytes()).hexdigest()) for k in data.files}
                normalized[path.name]={}
                for key in data.files:
                    if key=='_module':continue
                    array=data[key]
                    if key.endswith('/metadata/versions/native_build/scalars') or key.endswith('/metadata/model/scalars'):
                        scalar=json.loads(str(array));scalar.pop('openmp_enabled' if key.endswith('/metadata/versions/native_build/scalars') else 'backend',None)
                        array=np.array(json.dumps(scalar,sort_keys=True))
                    normalized[path.name][key]=dict(dtype=array.dtype.str,shape=list(array.shape),sha256=hashlib.sha256(array.tobytes()).hexdigest())
        if backend=='openmp':
            for team in teams[1:]:
                diffs,records=compare_results(results[backend,1],results[backend,team]);require(not diffs,'Team parity failed')
                report['comparisons'].append(dict(kind='team',threads=[1,team],records=records,differences=diffs))
    for team in [1,2,4,8]:
        diffs,records=compare_results(results['serial',1],results['openmp',team],backend_pair=True);require(not diffs,'Backend parity failed')
        report['comparisons'].append(dict(kind='backend',threads=team,records=records,differences=diffs))
    write(target/'report.json',report);write(target/'array-fingerprints.json',fingerprints)
    write(target/'backend-independent-fingerprints.json',normalized)
    shutil.copyfile(ROOT/'docs/data/solver-control-s7/validation/default-array-fingerprints.json',target/'baseline-array-fingerprints.json')
    shutil.copyfile(ROOT/'docs/data/solver-control-s7/manifest.json',target/'s7-manifest.json')
    write(target/'baseline-files.json',{name:digest(baseline/name) for name in names})
    return dict(passed=True,comparisons=len(report['comparisons']),cases=429,baseline='unchanged frozen S5c arrays; original S7 manifest records per-array identities')


def policy(out):
    target=out/'policy';target.mkdir(exist_ok=False)
    evidence=ROOT/'docs/data/solver-control-s7'
    protocol=read(evidence/'release-online-protocol.json');expected=read(evidence/'release-online-results.json')['rows'];actual=[]
    write(target/'protocol.json',protocol)
    for req,old in zip(protocol['rows'],expected):
        package=out/('serial-package' if req.get('backend')=='serial' else 'openmp-package')
        path=target/(req['id']+'.json')
        command(out,req['id'],[sys.executable,out/'tree/tools/validate_solver_policy.py','--worker',evidence,'--request',json.dumps(req),'--package',package,'--output',path],
            env=ENV|{'PYTHONPATH':str(package),'OMP_NUM_THREADS':str(req['threads'])},timeout=30)
        row=read(path)
        require(row['field_hashes']==old['field_hashes'] and row['diagnostics']==old['diagnostics'],'Policy fields/diagnostics differ')
        for key in ['accepted','accuracy_status','assessment_reason','assessment','assessment_history','checkpoint_history','method','policy_revision','monitor']:
            if row.get('control') is not None:
                require(comparable(row['control'].get(key))==comparable(old['control'].get(key)),'Policy decision differs: '+key)
        actual.append(row)
    result=dict(passed=True,workers=len(actual),exact_workers=len(actual),frozen_policy_manifest_sha256=digest(evidence/'manifest.json'))
    write(target/'summary.json',result);return result


def campaign(out):
    archive=out/'sources.tar.gz';cache=out/'campaign-cache';folders=[]
    common=[sys.executable,out/'tree/tools/run_urban_benchmarks.py','--tier','smoke','--candidate-archive',archive,
        '--baseline-archive',ROOT/'docs/data/solver-control-s5/s1a-matched-mask-sources.tar.gz','--cache-dir',cache]
    original_outcomes=None
    for name in ['first','reuse','repair']:
        folder=out/('campaign-'+name)
        if name=='repair':
            builds=read(folders[0]/'builds.json');package=Path(builds['builds']['candidate']['package']) if 'builds' in builds else Path(builds['candidate']['package'])
            # Damage only a generated cached package; prior outcomes untouched.
            (package/'dtcc_qes/_qes_revision.txt').write_text('damaged cached package\n')
        command(out,'campaign-'+name,[*common,'--output',folder],timeout=600);folders.append(folder)
        if original_outcomes is None:
            original_outcomes={p.relative_to(folder).as_posix():digest(p) for p in folder.rglob('*') if p.is_file()}
        else:
            require(original_outcomes=={p.relative_to(folders[0]).as_posix():digest(p) for p in folders[0].rglob('*') if p.is_file()},'Prior campaign outcome changed')
    decisions=[read(p/'campaign.json')['build_cache'] for p in folders]
    require(all(r['reused'] for r in decisions[1].values()),'Same-input build not reused')
    require(not decisions[2]['candidate']['reused'] and decisions[2]['baseline']['reused'],'Damaged package not rebuilt independently')
    fixture_protocols=[p/'fixtures/protocol.json' for p in folders]
    require(all(p.exists() for p in fixture_protocols) and len({digest(p) for p in fixture_protocols})==3,'Fixtures were reused rather than prepared fresh')
    write(out/'campaign-original-outcomes.json',original_outcomes)
    return dict(passed=True,reused=True,damaged_package_rebuilt=True,fresh_results=True,
        campaigns=[str(p) for p in folders],cache_matrix='Full Python tests additionally vary source/toolchain/backend/ABI/runtime/manifest and failed builds.')


def artifacts(out):
    attempt=uuid.uuid4().hex[:8]
    target=out/'artifact-attempts'/attempt;target.mkdir(parents=True,exist_ok=False);tree=out/'tree'
    build_env=ENV|{'CMAKE_GENERATOR':os.environ.get('CMAKE_GENERATOR','Unix Makefiles'),'CMAKE_BUILD_PARALLEL_LEVEL':'8'}
    command(out,'build-sdist',[sys.executable,'-m','build','--sdist','--no-isolation','--outdir',target],cwd=tree,timeout=600)
    sdist=next(target.glob('*.tar.gz'));extracted=out/'sdist-attempts'/attempt;extracted.mkdir(parents=True)
    with tarfile.open(sdist) as a:a.extractall(extracted,filter='data')
    source=next(p for p in extracted.iterdir() if p.is_dir())
    command(out,'wheel-from-sdist',[sys.executable,'-m','build','--wheel','--no-isolation','--outdir',target],cwd=source,env=build_env,timeout=600)
    wheel=next(target.glob('*.whl'))
    command(out,'artifact-content',[sys.executable,tree/'tools/check_artifacts.py',sdist,wheel],timeout=300)
    envdir=out/'wheel-envs'/attempt
    command(out,'wheel-venv',[sys.executable,'-m','venv',envdir])
    executable=envdir/'bin/python'
    command(out,'wheel-install',[executable,'-m','pip','install','--no-index','--no-deps',wheel])
    site=next((envdir/'lib').glob('python*/site-packages'))
    # Depend on the existing project environment without installing editable QES.
    (site/'release-test-dependencies.pth').write_text(sysconfig.get_path('purelib')+'\n')
    command(out,'wheel-runtime',[executable,tree/'tools/wheel_runtime_smoke.py','--expected-package',site/'dtcc_qes'])
    return dict(passed=True,sdist=dict(name=sdist.name,path=str(sdist),sha256=digest(sdist),bytes=sdist.stat().st_size),wheel=dict(name=wheel.name,path=str(wheel),sha256=digest(wheel),bytes=wheel.stat().st_size),wheel_built_from_sdist=True,installed_wheel_runtime=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--checks',nargs='+',choices=sorted(REQUIRED),default=['native','python','parity','policy','campaign','artifacts'])
    ap.add_argument('--stage-only',action='store_true')
    args=ap.parse_args();out=args.output.resolve()
    if not out.exists():stage(out)
    if args.stage_only:return
    functions=dict(native=native,python=python,parity=parity,policy=policy,campaign=campaign,artifacts=artifacts)
    for name in args.checks:
        validation=read(out/'validation.json')
        if name in validation['checks'] and validation['checks'][name]['passed']:raise ValueError('Check already passed; use a fresh output for a new validation: '+name)
        try:result=functions[name](out)
        except Exception as e:
            validation['checks'][name]=dict(passed=False,error=str(e));write(out/'validation.json',validation);raise
        validation['checks'][name]=result;write(out/'validation.json',validation)
    print(json.dumps(read(out/'validation.json'),indent=2))


if __name__=='__main__':main()
