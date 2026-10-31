"""S5b: finite residual/hotspot and independent-zero-start reference study.

Run: .venv/bin/python tools/run_solver_numerics.py --output build/numerics-s5b
Builds a frozen S4 tree with ONLY the S5b diagnostic additions. Each native
worker is limited to 30 s; six-worker shards have 180 s total limits. Failed
qualification stays failed; there are no automatic larger-budget retries.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/data/solver-control-s4/sources.tar.gz'
BASE_SHA = 'b2d4cd6e8708a4058187a8284195a67805f78b226e156a3f13981b903a8d63fe'
OVERLAYS = ['src/qes_core/solver/solver.h', 'src/qes_core/solver/solver.cpp',
            'tools/solver_numerics_probe.cpp', 'tests/native/check_equation_residual.cpp']
CMAKE_ADDITION = '''
add_executable(check_equation_residual tests/native/check_equation_residual.cpp $<TARGET_OBJECTS:qesbridge>)
target_link_libraries(check_equation_residual PRIVATE dtcc_qes_internal)
add_test(NAME equation_residual COMMAND check_equation_residual)
set_tests_properties(equation_residual PROPERTIES TIMEOUT 60)
add_executable(solver_numerics_probe tools/solver_numerics_probe.cpp $<TARGET_OBJECTS:qesbridge>)
target_link_libraries(solver_numerics_probe PRIVATE dtcc_qes_internal)
'''

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def affordable_cases():
    def case(name, buildings, roi, receptors):
        return dict(name=name, expected_shape=[32,80,80], solver_dz=[2.]*32,
                    resolution=2., buildings=buildings, roi=roi, receptors=receptors)
    def box(x,y,w,h,height):
        return dict(vertices=[[x,y],[x,y+h],[x+w,y+h],[x+w,y],[x,y]],height=height)
    tower=case('tower_2m', [box(x,y,12,12,h) for x,y,h in
               [(22,22,7.9),(42,22,7.9),(22,42,7.9),(42,42,23.7)]],
               [0,80,0,80], [[27,21],[21,23],[51,35],[15,47],[15,29]])
    canyon=case('passages_2m', [box(36+20*i,30+22*j,12,14,10+4*((i+j)%4))
                    for j in range(5) for i in range(4)],
                    [20,130,20,145], [[32,37],[52,59],[72,81],[92,103],[112,125]])
    return [tower,canyon]


def stdin_for(case, row):
    nz,ny,nx=case['expected_shape']
    tokens=[nx,ny,nz,case['resolution'],5,row['direction'],10,row['iterations'],row['cadence'],row.get('street_canyon',1)]
    tokens+=case['solver_dz'];tokens+=[len(case['buildings'])]
    for b in case['buildings']:
        v=b['vertices']
        if v[0]!=v[-1]: v=v+[v[0]]
        tokens += [len(v),b['height']]+[x for p in v for x in p]
    tokens+=case['roi']+[len(case['receptors'])]+[x for p in case['receptors'] for x in p]
    return ' '.join(map(str,tokens))+'\n'


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    assert digest(BASE)==BASE_SHA, 'Changed S4 baseline archive'
    tree=output/'tree';tree.mkdir()
    with tarfile.open(BASE) as archive: archive.extractall(tree,filter='data')
    for name in OVERLAYS:
        p=tree/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    with (tree/'CMakeLists.txt').open('a') as f: f.write(CMAKE_ADDITION)
    # Freeze analysis independently of later workspace edits.
    shutil.copyfile(Path(__file__),output/'run_solver_numerics.py')
    source_index={p.relative_to(tree).as_posix():digest(p) for p in tree.rglob('*') if p.is_file()}
    write(output/'source-index.json',source_index)
    with tarfile.open(output/'sources.tar.gz','w:gz') as archive:
        for name in sorted(source_index): archive.add(tree/name,arcname=name,recursive=False)
    matrix=[];cases={}
    core=ROOT/'build/urban-benchmarks/20261030T113701Z-fb78576f/fixtures/cases'
    pilot=ROOT/'build/urban-benchmarks/20261030T113311Z-44150a27/fixtures/cases'
    for tier,folder in [('core',core),('pilot',pilot)]:
        for name in ['mixed_downtown','perimeter_neighbourhood']:
            spec=json.loads((folder/f'{name}.json').read_text());spec['name']=f'{name}_{tier}'
            cases[spec['name']]=spec
    for name,directions in [('mixed_downtown_core',[225,270,315]),('perimeter_neighbourhood_core',[225])]:
        for direction in directions:
            matrix.append(dict(case=name,direction=direction,precision='float32',iterations=2000,cadence=500,locate=True,purpose='historical_hotspot'))
    for name in ['mixed_downtown_pilot','perimeter_neighbourhood_pilot']:
        for precision in ['float32','float64']:
            matrix.append(dict(case=name,direction=225,precision=precision,iterations=2000,cadence=500,locate=True,purpose='precision_control'))
        matrix.append(dict(case=name,direction=225,precision='float32',iterations=2000,cadence=500,locate=True,street_canyon=0,purpose='counterfactual_canyon_off'))
    for case in affordable_cases():
        cases[case['name']]=case
        for n in [500,1000,2000]:
            matrix.append(dict(case=case['name'],direction=270,precision='float64',iterations=n,cadence=25,locate=False,purpose='reference_triple'))
    for i,row in enumerate(matrix):row.update(id=f'{i:02d}',shard=i//6)
    for name,spec in cases.items():write(output/f'cases/{name}.json',spec)
    protocol=dict(stage='S5b',base_source_sha256=BASE_SHA,source_sha256=digest(output/'sources.tar.gz'),
        overlay_sha256={n:digest(tree/n) for n in OVERLAYS},
        matrix=matrix,workers=len(matrix),worker_seconds=30,shard_seconds=180,threads=4,
        normalization=dict(maximum_floor=1e-30,rms_floor=1e-30,units='native RHS; no row scaling; initial lambda=0'),
        reference_gate=dict(length_m=23.7,uref_mps=5.,scaled_mass_maximum=1e-3,scaled_mass_rms=1e-4,
                            successive_vector_maximum_over_uref=1e-3,successive_vector_p95_over_uref=5e-4,
                            unchanged_validity=True,all_three_mass_checks=True,both_successive_pairs=True),
        reference_scope='New same-grid 2m calibration scope; not the historical 0.5m/92-layer tower or urban core. L=23.7m declared before measurements, reused for both cases.',
        history='Stream every declared checkpoint from 0, max 81 frames per triple worker. Production monitor ring remains 4.',
        policy='No acceptance implementation. Unqualified triples produce iterate differences, never reference errors.',
        platform=platform.platform(),inputs_sha256={p.name:digest(p) for p in (output/'cases').iterdir()},
        driver_sha256=digest(output/'run_solver_numerics.py'))
    inventory=dict(existing=[
        dict(path='docs/data/generated-grid-pilot/raw.json.gz', sha256=digest(ROOT/'docs/data/generated-grid-pilot/raw.json.gz'),
             disposition='Not compatible with new 2m calibration cases or urban core',
             reasons=['historical tower 0.5m/92 layers versus new 2m/uniform32',
                      'source/method/order differs; archived serial trajectory',
                      'same complete initial fields/condition flags not established']),
        dict(path='docs/data/finest-reference/manifest.json',
             disposition='No accepted finest reference; stopped runtime escalation retained'),
        dict(path='build/urban-benchmarks/core-2000-20261030-clean/results.json',
             sha256=digest(ROOT/'build/urban-benchmarks/core-2000-20261030-clean/results.json'),
             disposition='Compatible geometry/grid benchmark evidence only; 2000 is not a reference')],
        new_scope='Two explicitly new 2m geometries. Same frozen source, initial fields/flags and sampling within each triple; no transfer to large-grid hotspots.',
        no_adaptive_budget_expansion=True)
    write(output/'reference-inventory.json',inventory)
    write(output/'protocol.json',protocol)
    for row in matrix:(output/f"{row['id']}.stdin").write_text(stdin_for(cases[row['case']],row))
    return protocol


def compare_samples(a,b,plane_points):
    if a.shape!=b.shape or a.ndim!=2 or a.shape[1]!=4 or len(a)<2*plane_points:
        raise ValueError('Incompatible sample support')
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Nonfinite sample evidence')
    valid=a[:,3].astype(bool)&b[:,3].astype(bool)
    result=[]
    # Separate the two heights; receptors are the tail, interleaved by height.
    for h in range(2):
        idx=np.r_[np.arange(h*plane_points,(h+1)*plane_points),np.arange(2*plane_points+h,len(a),2)]
        common=idx[valid[idx]];delta=np.linalg.norm(a[common,:3]-b[common,:3],axis=1)/5
        required=idx[idx>=2*plane_points]
        result.append(dict(common_valid=len(common),validity_changes=int(np.count_nonzero(a[idx,3]!=b[idx,3])),
            required_valid=bool(np.all(a[required,3]) and np.all(b[required,3])),
            p95=float(np.percentile(delta,95)) if len(delta) else None,
            maximum=float(np.max(delta)) if len(delta) else None))
    return result


def qualify(rows, output):
    groups={}
    for row in rows:
        if row['request']['purpose']=='reference_triple':groups.setdefault(row['request']['case'],[]).append(row)
    result=[]
    for name,group in groups.items():
        group=sorted(group,key=lambda r:r['request']['iterations'])
        budgets=[r['request']['iterations'] for r in group]
        complete=(len(group)==3 and budgets==[budgets[0]*m for m in (1,2,4)]
                  and all(r['status']=='completed' for r in group))
        record=dict(case=name,accepted=False,complete=complete,pairs=[],mass_checks=[])
        if complete:
            arrays=[]
            for r in group:
                with np.load(output/f"{r['request']['id']}.npz") as values: arrays.append(values['samples'][-1])
                mass=r['result']['checkpoints'][-1]['mass'];record['mass_checks'].append(dict(
                    maximum=mass['maximum']*23.7/5,rms=mass['rms']*23.7/5,
                    passed=mass['maximum']*23.7/5<=1e-3 and mass['rms']*23.7/5<=1e-4))
            same_initial=len({tuple(r['result']['initial_hashes']) for r in group})==1
            record['same_initial_fields_and_flags']=same_initial
            for a,b in zip(arrays,arrays[1:]):record['pairs'].append(compare_samples(a,b,group[0]['result']['plane_points']))
            record['accepted']=bool(same_initial and all(m['passed'] for m in record['mass_checks']) and all(
                h['p95'] is not None and h['maximum']<=1e-3 and h['p95']<=5e-4 and h['validity_changes']==0 and h['required_valid']
                for pair in record['pairs'] for h in pair))
        record['label']='qualified_same_grid_reference' if record['accepted'] else 'unqualified_iterate_differences_only'
        result.append(record)
    return result


def run(output, protocol):
    build=output/'native'
    for label,cmd,limit in [
        ('configure',['cmake','-S',str(output/'tree'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}', '-DDTCC_QES_BUILD_TESTS=ON','-DDTCC_QES_OPENMP=ON'],120),
        ('build',['cmake','--build',str(build),'-j8'],180),
        ('tests',['ctest','--test-dir',str(build),'--output-on-failure','-j1'],120)]:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=limit)
        (output/f'{label}.log').write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
    executable=build/'solver_numerics_probe';write(output/'execution.json',dict(
        executable_sha256=digest(executable),cmake_cache_sha256=digest(build/'CMakeCache.txt'),
        protocol_sha256=digest(output/'protocol.json'),environment={'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'}))
    rows=[];shard=None;started=0
    for request in protocol['matrix']:
        if request['shard']!=shard:shard=request['shard'];started=time.monotonic()
        row=dict(request=request);ident=request['id'];remaining=180-(time.monotonic()-started)
        print(f"[{int(ident)+1}/{len(protocol['matrix'])}] {request['case']} {request['direction']} {request['precision']} {request['iterations']}",flush=True)
        try:
            if remaining<=0:raise subprocess.TimeoutExpired('shard',180)
            proc=subprocess.run([str(executable),request['precision'],str(output/f'{ident}.bin'),str(int(request['locate']))],
                input=(output/f'{ident}.stdin').read_text(),capture_output=True,text=True,timeout=min(30,remaining),
                env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
            (output/f'{ident}.log').write_text(proc.stdout+'\n'+proc.stderr);proc.check_returncode()
            value=json.loads(proc.stdout)
            if value['team']!=4 or value['checkpoints'][-1]['iteration']!=request['iterations']:raise ValueError('Wrong team/work')
            n=value['checkpoints'][0]['samples'];frames=np.fromfile(output/f'{ident}.bin',dtype=np.float64).reshape(len(value['checkpoints']),n,4)
            np.savez_compressed(output/f'{ident}.npz',samples=frames,iterations=[c['iteration'] for c in value['checkpoints']])
            (output/f'{ident}.bin').unlink()
            row.update(status='completed',result=value)
        except (subprocess.SubprocessError,ValueError) as exc:
            row.update(status='failed',error=str(exc))
            if isinstance(exc,subprocess.TimeoutExpired):
                (output/f'{ident}.log').write_bytes((exc.stdout or b'')+(exc.stderr or b''))
        rows.append(row);write(output/'results.json',dict(rows=rows))
    summary=dict(completed=all(r['status']=='completed' for r in rows),rows=rows,references=qualify(rows,output))
    write(output/'results.json',summary)
    # Residuals/mass vs work/time are present for every frame. Only label errors
    # when the independent triple passed the unchanged reference gate.
    curves=[]
    for ref in summary['references']:
        group=[r for r in rows if r['request']['case']==ref['case'] and r['status']=='completed']
        if len(group)!=3:continue
        longest=max(group,key=lambda r:r['request']['iterations']);n=longest['result']['plane_points']
        with np.load(output/f"{longest['request']['id']}.npz") as v:frames=v['samples'].copy()
        for frame,checkpoint in zip(frames,longest['result']['checkpoints']):
            curves.append(dict(case=ref['case'],iteration=checkpoint['iteration'],sweep_seconds=checkpoint['sweep_seconds'],
                elapsed_seconds=checkpoint['elapsed_seconds'],residual=checkpoint['residual'],mass=checkpoint['mass'],
                comparison_label='reference_error' if ref['accepted'] else 'difference_to_unqualified_2000_iterate',
                heights=compare_samples(frame,frames[-1],n)))
    write(output/'cost-error-curves.json',dict(curves=curves))
    files={p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file() and 'tree' not in p.relative_to(output).parts and 'native' not in p.relative_to(output).parts and p.name!='manifest.json'}
    write(output/'manifest.json',dict(stage='S5b',files=files))
    print(json.dumps(dict(completed=summary['completed'],workers=len(rows),references=summary['references'],output=str(output)),indent=2))
    return summary['completed']


def audit(output):
    manifest=json.loads((output/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if digest(output/name)!=sha:raise ValueError(f'Changed evidence: {name}')
    index=json.loads((output/'source-index.json').read_text())
    with tarfile.open(output/'sources.tar.gz') as archive:
        for name,sha in index.items():
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=sha:raise ValueError(f'Changed source: {name}')
    results=json.loads((output/'results.json').read_text())
    if results['references']!=qualify(results['rows'],output):raise ValueError('Qualification replay changed')
    return dict(passed=True,files=len(manifest['files']),sources=len(index),workers=len(results['rows']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--audit',action='store_true')
    args=p.parse_args();output=args.output.resolve()
    if args.audit:print(json.dumps(audit(output)));return
    protocol=prepare(output)
    if not run(output,protocol):raise SystemExit(1)

if __name__=='__main__':main()
