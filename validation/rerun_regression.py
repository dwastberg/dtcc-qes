"""Matched current/initial AIJ regression run; preserves the original archive.

Build an isolated copy of the initial-validation revision first. All timing
workers are fresh processes; three repetitions alternate implementation order.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'validation')]
os.environ['OMP_NUM_THREADS']='4'
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    from aij.runner import _clean
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(_clean(value),indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def activate(package):
    """Prevent the installed editable hook from substituting the other build."""
    package=package.resolve()
    if 'dtcc_qes' in sys.modules:raise RuntimeError('Select the implementation before importing dtcc_qes')
    sys.meta_path[:]=[f for f in sys.meta_path if not any(
        k=='dtcc_qes' or k.startswith('dtcc_qes.') for k in getattr(f,'known_source_files',{}))]
    sys.path.insert(0,str(package.parent))
    import dtcc_qes
    from dtcc_qes import _qes
    if not Path(dtcc_qes.__file__).resolve().is_relative_to(package) or not Path(_qes.__file__).resolve().is_relative_to(package):
        raise RuntimeError('Implementation isolation failed')
    return _qes


def freeze_current(destination):
    import dtcc_qes
    from dtcc_qes import _qes
    shutil.copytree(Path(dtcc_qes.__file__).parent,destination,
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.so','*.pyd'))
    shutil.copy2(_qes.__file__,destination/Path(_qes.__file__).name)


def build_baseline(source,destination,log):
    build=source/'regression-build'
    with log.open('w') as output:
        for command in ([shutil.which('cmake'),'-S',str(source),'-B',str(build),'-G','Unix Makefiles',
            '-DCMAKE_BUILD_TYPE=Release','-DDTCC_QES_OPENMP=ON',f'-DPython_EXECUTABLE={sys.executable}'],
            [shutil.which('cmake'),'--build',str(build),'-j','2']):
            subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(source/'src/dtcc_qes',destination,
        ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.so','*.pyd'))
    binaries=list(build.glob('_qes*.so'))+list(build.glob('_qes*.pyd'))
    if len(binaries)!=1:raise RuntimeError('Expected one isolated native extension')
    shutil.copy2(binaries[0],destination/binaries[0].name)


def package_identity(package):
    return {str(p.relative_to(package)):sha(p) for p in sorted(package.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}


def claim_attempt(folder):
    try:folder.mkdir(parents=True,exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError(f'Preserve the incomplete/live attempt in {folder}; choose a fresh campaign') from error


def worker(descriptor,package,output):
    native=activate(package)
    from experiments.tools.workers import event,configure_worker_diagnostics
    configure_worker_diagnostics();event('begin',label=descriptor['name'])
    from aij.runspec import RunSpec
    from aij.runner import run,write as save,_peak_rss
    spec=RunSpec.from_dict(descriptor['spec']);started=time.perf_counter()
    record,arrays=run(spec)
    record['regression']=dict(descriptor=descriptor,package=str(package.resolve()),
        native_sha256=sha(native.__file__),compiler_id=native.compiler_id,
        compiler_version=native.compiler_version,build_type=native.build_type,
        fp_contract=native.fp_contract,openmp_enabled=native.openmp_enabled)
    save(record,arrays,output/spec.case)
    write(output/'worker.json',dict(complete=True,key=spec.key,seconds=time.perf_counter()-started,
        peak_rss_bytes=_peak_rss(),native_sha256=sha(native.__file__)))
    event('done',label=descriptor['name'],seconds=time.perf_counter()-started)


def equal_values(a,b):
    import numpy as np
    if isinstance(a,dict) or isinstance(b,dict):
        return isinstance(a,dict) and isinstance(b,dict) and set(a)==set(b) and all(equal_values(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)) or isinstance(b,(list,tuple)):
        try:return bool(np.array_equal(np.asarray(a,dtype=float),np.asarray(b,dtype=float),equal_nan=True))
        except (ValueError,TypeError):return a==b
    return a==b or (isinstance(a,float) and isinstance(b,float) and np.isnan(a) and np.isnan(b))


def accuracy(current,parent,current_plane,parent_plane):
    import numpy as np
    checks={k:equal_values(current[k],parent[k]) for k in ('spec','grid','profile','probes','diagnostics')}
    with np.load(current_plane) as a,np.load(parent_plane) as b:
        checks['plane_fields']=set(a.files)==set(b.files) and all(np.array_equal(a[k],b[k],equal_nan=True) for k in a.files)
    checks['input_city']=current['provenance']['city_digest']==parent['provenance']['city_digest']
    checks['measurement_file']=current['provenance']['xls_sha256']==parent['provenance']['xls_sha256']
    return dict(passed=all(checks.values()),checks=checks)


def performance(pairs):
    import numpy as np
    from collections import defaultdict
    grouped=defaultdict(list)
    for row in pairs:grouped[row['key']].append(row)
    if len(grouped)!=35 or any(len(v)!=3 for v in grouped.values()):
        return dict(assessed=False,passed=False,reason='Three paired repetitions on all 35 conditions required')
    ratios={key:float(np.median([r['current_seconds'] for r in rows])/np.median([r['parent_seconds'] for r in rows]))
        for key,rows in grouped.items()}
    all_ratios=np.array([r['current_seconds']/r['parent_seconds'] for r in pairs])
    values=np.array(list(ratios.values()));rng=np.random.default_rng(20261104)
    bootstrap=np.median(rng.choice(values,size=(2000,len(values)),replace=True),axis=1)
    interval=np.percentile(bootstrap,[2.5,97.5])
    rss=max(r['current_rss']/r['parent_rss'] for r in pairs)
    checks=dict(condition_medians=bool(values.max()<=1.05),
        pooled_median=bool(np.median(all_ratios)<=1.05),upper_interval=bool(interval[1]<=1.05),
        p95_paired_ratio=bool(np.percentile(all_ratios,95)<=1.10),peak_memory_ratio=rss<=1.10,
        absolute_memory=all(r['current_rss']<=2*2**30 for r in pairs),
        answer_deadlines=all(r['current_seconds']<=(20. if r['case']=='D' else 60.) for r in pairs))
    return dict(assessed=True,passed=all(checks.values()),checks=checks,condition_median_ratios=ratios,
        paired_ratio_median=float(np.median(all_ratios)),paired_ratio_p95=float(np.percentile(all_ratios,95)),
        paired_ratio_max=float(all_ratios.max()),median_ratio_95_interval=interval,
        maximum_peak_memory_ratio=rss,
        scope='Measured cold 2 m AIJ workflows, four native threads, same dependencies; 5% median/10% p95 noninferiority margins')


def assess(directory,descriptors,archived):
    from aij.runspec import RunSpec
    pairs=[];comparisons=[];missing=[]
    by_case={}
    for d in descriptors:
        spec=RunSpec.from_dict(d['spec']);folder=directory/d['name'];outcome=folder/'outcome.json'
        result=json.loads(outcome.read_text()) if outcome.exists() else {}
        path=folder/spec.case/(spec.key+'.json')
        if not result.get('complete') or not path.exists():missing.append(d['name']);continue
        record=json.loads(path.read_text())
        by_case[d['repetition'],spec.key,d['implementation']]=(record,path,result)
    for repetition,key,implementation in sorted(by_case):
        if implementation!='current' or (repetition,key,'initial') not in by_case:continue
        current,cp,co=by_case[repetition,key,'current'];parent,pp,po=by_case[repetition,key,'initial']
        cw=json.loads((cp.parent.parent/'worker.json').read_text())
        pw=json.loads((pp.parent.parent/'worker.json').read_text())
        checks=accuracy(current,parent,cp.with_suffix('.npz'),pp.with_suffix('.npz'))
        old=archived/current['spec']['case']/(key+'.json')
        if not old.exists():raise ValueError('Original validation archive is incomplete')
        historical=accuracy(current,json.loads(old.read_text()),cp.with_suffix('.npz'),old.with_suffix('.npz'))
        comparisons.append(dict(repetition=repetition,key=key,initial_vs_current=checks,historical_vs_current=historical))
        pairs.append(dict(key=key,case=current['spec']['case'],repetition=repetition,
            current_seconds=co['wall_seconds'],parent_seconds=po['wall_seconds'],
            current_rss=max(cw['peak_rss_bytes'],co['sampled_peak_rss_bytes']),
            parent_rss=max(pw['peak_rss_bytes'],po['sampled_peak_rss_bytes'])))
    complete=not missing and len(comparisons)==105
    return dict(complete=complete,missing=missing,comparisons=comparisons,performance_pairs=pairs,
        accuracy_passed=complete and all(r['initial_vs_current']['passed'] and r['historical_vs_current']['passed'] for r in comparisons),
        performance=performance(pairs))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'validation/output/regression/current-vs-initial-v1')
    p.add_argument('--baseline-source',type=Path,default=Path('/private/tmp/qes-aij-baseline-6e205c0'))
    p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--worker',action='store_true');p.add_argument('--descriptor');p.add_argument('--package',type=Path)
    args=p.parse_args()
    if args.worker:worker(json.loads(args.descriptor),args.package,args.output);return
    from aij.campaigns import baseline
    packages=args.output/'packages';manifest_path=args.output/'manifest.json'
    if manifest_path.exists():
        if not args.resume:p.error('Use a fresh output or resume an unchanged manifest')
        manifest=json.loads(manifest_path.read_text())
    else:
        args.output.mkdir(parents=True,exist_ok=False);packages.mkdir()
        freeze_current(packages/'current/dtcc_qes')
        descriptors=[]
        for repetition in range(3):
            for i,spec in enumerate(baseline()):
                arms=('initial','current') if (repetition+i)%2==0 else ('current','initial')
                for arm in arms:descriptors.append(dict(name=f'r{repetition+1}-{i:02}-{arm}',implementation=arm,
                    repetition=repetition,spec=spec.to_dict()))
        manifest=dict(schema='aij-regression-v1',initial_revision='6e205c003cd44ec0ad8a785c0dbd0c402940ed19',
            descriptors=descriptors,current_package=package_identity(packages/'current/dtcc_qes'),
            protocol=dict(repetitions=3,threads=4,blas_threads=1,paired_order='alternating',
                accuracy='Bitwise probes/planes/diagnostics and identical inputs versus fresh initial and historical archive',
                time_median_margin=1.05,time_p95_margin=1.10,memory_margin=1.10,
                deadline_D=20.,deadline_E=60.,rss_bytes=2*2**30),
            driver_sha256=sha(__file__),baseline_source=str(args.baseline_source.resolve()),
            initial_source_revision=json.loads((args.baseline_source/'baseline-revision.json').read_text()))
        write(manifest_path,manifest)
    if sha(__file__)!=manifest['driver_sha256'] or package_identity(packages/'current/dtcc_qes')!=manifest['current_package']:
        p.error('Preserve evidence; implementation changed')
    if args.prepare_only:print(manifest_path);return
    if not (packages/'initial/dtcc_qes').exists():
        build_baseline(args.baseline_source,packages/'initial/dtcc_qes',args.output/'baseline-build.log')
        manifest['initial_package']=package_identity(packages/'initial/dtcc_qes');write(manifest_path,manifest)
    if package_identity(packages/'initial/dtcc_qes')!=manifest['initial_package']:p.error('Initial package changed')
    for arm in ('initial','current'):
        subprocess.run([sys.executable,'-m','compileall','-q',str(packages/arm)],check=True)
    from experiments.tools.workers import run_worker
    reason=None
    try:
        for d in manifest['descriptors']:
            folder=args.output/d['name'];out=folder/'outcome.json'
            if out.exists():continue
            print(d['name'],flush=True)
            claim_attempt(folder)
            outcome=run_worker([sys.executable,str(Path(__file__).resolve()),'--worker','--descriptor',json.dumps(d),
                '--package',str(packages/d['implementation']/'dtcc_qes'),'--output',str(folder)],folder/'stderr.log',
                deadline=20. if d['spec']['case']=='D' else 60.,rss_limit=2*2**30)
            write(out,outcome)
            if not outcome['complete']:raise RuntimeError('Validation worker failed; preserve the attempt')
    except (RuntimeError,KeyboardInterrupt,OSError) as error:reason=str(error) or 'Interrupted'
    report=assess(args.output,manifest['descriptors'],ROOT/'validation/output/runs')
    report.update(termination_reason=reason,manifest_sha256=sha(manifest_path))
    write(args.output/'regression.json',report)
    print(args.output/'regression.json',flush=True)
    if not report['accuracy_passed'] or not report['performance']['passed']:raise SystemExit(1)


if __name__=='__main__':main()
