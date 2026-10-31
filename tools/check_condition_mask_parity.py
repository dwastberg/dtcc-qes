"""S5c: require exact unaffected outputs and tie every changed case to a mask guard.

A counter in isolated builds records attempted solid relabeling. It never
changes a numerical expression or production source. Complete 429-case data
are saved, and candidate teams/backends must remain strictly bitwise equal.
"""
from __future__ import annotations
import argparse
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import numpy as np
import compare_native_builds as native
from run_solver_numerics import digest,write
ROOT=Path(__file__).resolve().parents[1]


def collect(out, *, targeted=False):
    from dtcc_qes import _qes
    values={"qes_revision":np.array(_qes.qes_revision)};counts={}
    runs=targeted_runs() if targeted else itertools.chain(native.public_runs(),native.native_runs())
    for name,result in runs:
        native.store(values,name,result);counts[name]=_qes._s5_mask_attempts()
    np.savez_compressed(out,**values);write(out.with_suffix('.counts.json'),counts)
    print(json.dumps(dict(cases=len(counts),guard_cases=sum(v>0 for v in counts.values()),module=_qes.__file__)))


def instrument(tree):
    canyon=tree/'src/qes_core/winds/StreetCanyon.cpp';s=canyon.read_text()
    pos=s.index('void PolyBuilding::streetCanyon')
    s=s[:pos]+'std::size_t dtcc_s5_mask_attempts=0;\n'+s[pos:]
    # The current and previous canyon have the same write site and geometry cell.
    needle='''                if ((WGD->icellflag[icell_cent] != 7)'''
    if needle not in s:needle='''                // Condition labels classify existing fluid;'''
    assert s.count(needle)==1
    s=s.replace(needle,'''                if (WGD->icellflag[icell_cent]==0 || WGD->icellflag[icell_cent]==2) ++dtcc_s5_mask_attempts;
'''+needle);canyon.write_text(s)
    runner=tree/'src/qes_core/dtcc/wind_runner.cpp';s=runner.read_text()
    needle='namespace dtcc_qes {';s=s.replace(needle,'extern std::size_t dtcc_s5_mask_attempts;\n'+needle,1)
    needle='  state.inputs.set_condition(condition);';assert s.count(needle)==1;s=s.replace(needle,'  dtcc_s5_mask_attempts=0;\n'+needle);runner.write_text(s)
    binding=tree/'src/cpp/bindings.cpp';s=binding.read_text();needle='NB_MODULE(_qes, m)';assert needle in s
    s=s.replace(needle,'extern std::size_t dtcc_s5_mask_attempts;\n'+needle)
    needle='  m.attr("fp_contract")';pos=s.index(needle);s=s[:pos]+'  m.def("_s5_mask_attempts", [] {return dtcc_s5_mask_attempts;});\n'+s[pos:];binding.write_text(s)


def analyze(out, *, supplement=False):
    builds=json.loads((out/'builds.json').read_text());revisions=[];unchanged_cases=set();changed_cases=set()
    prefix='targeted-' if supplement else ''
    for backend in ['openmp','serial']:
        old=out/f'{prefix}baseline-{backend}-1.npz';new=out/f'{prefix}candidate-{backend}-1.npz'
        hits_old=json.loads(old.with_suffix('.counts.json').read_text());hits_new=json.loads(new.with_suffix('.counts.json').read_text())
        allowed={k for k in hits_old if hits_old[k] or hits_new[k]}
        changed=[];unchanged=[]
        with np.load(old) as a,np.load(new) as b:
            assert set(a.files)==set(b.files)
            for case in hits_old:
                keys=[k for k in a.files if k.startswith(case+'/')]
                differences=[k for k in keys if a[k].dtype!=b[k].dtype or a[k].shape!=b[k].shape or a[k].tobytes()!=b[k].tobytes()]
                if differences:
                    if case not in allowed:raise ValueError(f'Unexplained changed case: {case}')
                    # Coordinate arrays and metadata must remain exact. Only
                    # physical fields and numerical diagnostics may differ.
                    if any('/metadata/' in k or k.rsplit('/',1)[-1] in ('x','y','z','z_faces') for k in differences):
                        raise ValueError(f'Changed geometry/provenance outside correction: {case}')
                    changed.append(dict(case=case,differences=differences,baseline_guard_hits=hits_old[case],candidate_guard_hits=hits_new[case]))
                else:unchanged.append(case)
        if len(hits_old)!=(12 if supplement else 429):raise ValueError('Incomplete declared matrix')
        revisions.append(dict(backend=backend,cases=len(hits_old),unchanged=unchanged,changed=changed,guard_hit_cases=sorted(allowed)))
        if backend=='openmp':changed_cases={r['case'] for r in changed};unchanged_cases=set(unchanged)
        elif changed_cases!={r['case'] for r in changed}:raise ValueError('Changed case set depends on backend')
    parity=[]
    for t in [2,4,8]:
        a=out/f'{prefix}candidate-openmp-1.npz';b=out/f'{prefix}candidate-openmp-{t}.npz';diffs,n=native.compare_results(a,b)
        parity.append(dict(kind='team',threads=t,records=n,differences=diffs))
    for t in [1,2,4,8]:
        diffs,n=native.compare_results(out/f'{prefix}candidate-serial-1.npz',out/f'{prefix}candidate-openmp-{t}.npz',backend_pair=True)
        parity.append(dict(kind='backend',threads=t,records=n,differences=diffs))
    passed=all(not p['differences'] for p in parity)
    report=dict(passed=passed,revisions=revisions,parity=parity,changed_cases=len(changed_cases),unchanged_cases=len(unchanged_cases),
        source_and_executable_identities=builds,
        rule='Every unaffected case exact. Every changed case has measured attempted solid relabeling, unchanged geometry/metadata, and an explicit per-record difference list. All candidate team/backend comparisons exact.')
    if supplement and not changed_cases:raise ValueError('Targeted regression did not exercise the correction')
    write(out/(prefix+'parity.json'),report)
    print(json.dumps(dict(passed=passed,changed_cases=len(changed_cases),unchanged_cases=len(unchanged_cases),strict_team_backend_comparisons=len(parity))))
    if not passed:raise ValueError('Candidate team/backend parity failed')


def run(out):
    out.mkdir(parents=True,exist_ok=False);builds={}
    write(out/'protocol.json',dict(cases=429,teams=[1,2,4,8],backends=['openmp','serial'],worker_seconds=180,
        expected_changes='Only cases with actual attempted solid relabeling may change physical fields/diagnostics. All coordinates, metadata and unaffected cases stay exact.',
        baseline=digest(ROOT/'docs/data/solver-control-s5b/implementation-sources.tar.gz'),candidate=digest(ROOT/'build/solver-control-s5c/study/sources.tar.gz')))
    for label,archive in [('baseline',ROOT/'docs/data/solver-control-s5b/implementation-sources.tar.gz'),('candidate',ROOT/'build/solver-control-s5c/study/sources.tar.gz')]:
        tree=out/f'{label}-tree';tree.mkdir()
        with tarfile.open(archive) as a:a.extractall(tree,filter='data')
        instrument(tree)
        with tarfile.open(out/f'{label}-instrumented-sources.tar.gz','w:gz') as a:
            for f in sorted(tree.rglob('*')):
                if f.is_file():a.add(f,arcname=f.relative_to(tree).as_posix(),recursive=False)
        for backend in ['openmp','serial']:
            build=out/f'{label}-{backend}-build';module=native.build(tree,build,backend);package=out/f'{label}-{backend}-package';native.stage_package(tree,module,package)
            builds[f'{label}-{backend}']=dict(module_sha256=digest(module),instrumented_archive_sha256=digest(out/f'{label}-instrumented-sources.tar.gz'),cmake_cache_sha256=digest(build/'CMakeCache.txt'))
            for threads in ([1,2,4,8] if label=='candidate' and backend=='openmp' else [1]):
                result=out/f'{label}-{backend}-{threads}.npz'
                p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--collect',str(result)],capture_output=True,text=True,timeout=180,
                    env=os.environ|{'PYTHONPATH':str(package),'OMP_NUM_THREADS':str(threads),'OMP_DYNAMIC':'FALSE'})
                (out/f'{label}-{backend}-{threads}.log').write_text(p.stdout+p.stderr);p.check_returncode();print(p.stdout.strip(),flush=True)
    write(out/'builds.json',builds);analyze(out)


def targeted_runs():
    from dtcc_qes import _qes
    blocks=[(24,24,23,19,31),(53,24,17,18,24),(24,53,21,20,13),(53,53,22,22,18)]
    for stretched in [False,True]:
        for precision in ['float32','float64']:
            for direction in [225.,315.,270.]:
                grid,arrays=native.native_inputs(blocks,nx=48,ny=48,nz=32)
                if stretched:arrays['dz_layers']=np.r_[np.ones(16),np.full(16,3.)]
                model=native.native_model(rooftop_flag=0,upwind_cavity_flag=0,street_canyon_flag=1,wake_flag=1,sidewall_flag=0,high_rise_flag=0)
                runner=_qes.WindRunner();runner.prepare(grid,model,**arrays)
                yield f'targeted/{stretched}/{precision}/{direction}',native.native_solve(runner,5.,direction,60,precision)


def supplement(out):
    write(out/'targeted-protocol.json',dict(cases=12,precisions=['float32','float64'],grids=['uniform2m','stretched1m_3m'],directions=[225,315,270],
        geometry='Four unequal-height buildings cropped from the S5b corner, translated to local 96m square; 32 layers and 60 sweeps.',
        reason='The historical 429-case matrix has zero solid-relabel attempts and remains exact; these added cases must exercise the correction.',worker_seconds=180))
    for label in ['baseline','candidate']:
        for backend in ['openmp','serial']:
            package=out/f'{label}-{backend}-package'
            for team in ([1,2,4,8] if label=='candidate' and backend=='openmp' else [1]):
                result=out/f'targeted-{label}-{backend}-{team}.npz'
                p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--collect-targeted',str(result)],capture_output=True,text=True,timeout=180,
                    env=os.environ|{'PYTHONPATH':str(package),'OMP_NUM_THREADS':str(team),'OMP_DYNAMIC':'FALSE'})
                (out/f'targeted-{label}-{backend}-{team}.log').write_text(p.stdout+p.stderr);p.check_returncode();print(p.stdout.strip(),flush=True)
    analyze(out,supplement=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--collect',type=Path);p.add_argument('--analyze',action='store_true');p.add_argument('--supplement',action='store_true');p.add_argument('--collect-targeted',type=Path);a=p.parse_args()
    if a.collect:collect(a.collect);return
    if a.collect_targeted:collect(a.collect_targeted,targeted=True);return
    if not a.output:p.error('--output is required')
    if a.supplement:supplement(a.output.resolve())
    elif a.analyze:analyze(a.output.resolve())
    else:run(a.output.resolve())

if __name__=='__main__':main()
