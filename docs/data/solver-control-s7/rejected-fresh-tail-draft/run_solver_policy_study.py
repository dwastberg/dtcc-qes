"""S7 finite calibration/qualification; held-out workers require a frozen policy.

prepare/calibrate uses only development conditions. validate is implemented
against the separately frozen native/API implementation, never a Python stop loop.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import numpy as np
from run_solver_numerics import affordable_cases,compare_samples,digest,stdin_for,write
from solver_policy_replay import TARGET,replay,METHOD,POLICY
ROOT=Path(__file__).resolve().parents[1]
PARENT='3fd915c91de4dda94c56fa44c1c81f3b961e5fdf7f4f297fea1b1984615d5f63'


def cases():
    def box(x,y,w,d,h):return dict(vertices=[[x,y],[x,y+d],[x+w,y+d],[x+w,y],[x,y]],height=h)
    def city(name,buildings,receptors,**kw):
        return dict(name=name,expected_shape=[32,80,80],solver_dz=[2.]*32,resolution=2.,buildings=buildings,
                    roi=[8,152,8,152],receptors=receptors,direction=270,speed=5.,split='validation',**kw)
    tower,passage=affordable_cases()
    for c in [tower,passage]:c.update(direction=270,speed=5.,split='calibration')
    graded=json.loads(json.dumps(passage));graded.update(name='cal_passages_graded',direction=225)
    graded['solver_dz']=[1.2*1.03**k for k in range(32)]
    staggered=city('val_staggered_240',
        [box(25+23*i+(5 if j%2 else 0),25+24*j,10+2*(i%2),12+2*(j%2),8+4*((i+2*j)%4)) for j in range(4) for i in range(5)],
        [[19,31],[44,53],[69,77],[94,101],[125,125]])
    staggered['direction']=240
    courtyard=city('val_courtyards_315',
        [box(x+18*i,y+18*j,10,10,8+4*((i+j+c)%4)) for c,(x,y) in enumerate([(23,23),(91,23),(57,91)])
         for j in range(3) for i in range(3) if (i,j)!=(1,1)],
        [[46,46],[114,46],[80,114],[19,83],[135,83]])
    courtyard['direction']=315
    mixed=city('val_mixed_195',
        [box(25+23*i,25+23*j,10+2*(i%2),12+2*(j%2),8+4*((3*i+j)%5)) for j in range(5) for i in range(5)],
        [[19,31],[42,54],[65,77],[88,100],[111,123]])
    mixed['direction']=195
    sg=json.loads(json.dumps(staggered));sg.update(name='val_staggered_graded_150',direction=150,solver_dz=graded['solver_dz'])
    mg=json.loads(json.dumps(mixed));mg.update(name='val_mixed_graded_domain_300',direction=300,solver_dz=graded['solver_dz'],expected_shape=[32,80,96])
    scaling=[]
    for speed in [2.,10.]:
        c=json.loads(json.dumps(courtyard));c.update(name=f'val_courtyards_210_u{int(speed)}',direction=210,speed=speed);scaling.append(c)
    return [tower,passage,graded,staggered,courtyard,mixed,sg,mg]+scaling


def protocol(out):
    out.mkdir(parents=True,exist_ok=False)
    for case in cases():write(out/f"cases/{case['name']}.json",case)
    values=[dict(safety_factor=s,minimum_iterations=n,maximum_ratio=q)
            for s,n,q in itertools.product([2.,4.,8.],[150,200],[.8,.9])]
    p=dict(stage='S7',policy=POLICY,method=METHOD,parent_source_sha256=PARENT,
        target=TARGET,calibration_parameters=values,
        calibration_selection='Zero false acceptances over all calibration histories; all qualified calibration cases must accept. Minimize mean first-accept iteration, ties prefer larger safety, larger minimum work, smaller ratio cap. No selection after looking at validation.',
        calibration=[c['name'] for c in cases() if c['split']=='calibration'],
        validation=[c['name'] for c in cases() if c['split']=='validation'],
        reference=dict(precision='float64',omega=1.78,budgets=[500,1000,2000],
            gates=dict(scaled_mass_maximum=1e-3,scaled_mass_rms=1e-4,vector_maximum=1e-3,vector_p95=5e-4),
            independent_zero_starts=True,require_both_successive_pairs=True),
        scope=dict(horizontal_spacing=2.,horizontal_cells=[80,96],vertical_cells=32,
            layers='uniform 2m or graded 1.2*1.03^k (k=0..31)',precision='float32',reference_height=10.,roughness_length=.1,
            speed=[2.,10.],buildings=[4,32],building_heights=[4.,24.],
            geometry='flat-base axis-aligned rectangles, footprint sides 8..16m, at least 12m domain margin',
            models='default flags only; wind without turbulence',heights=[1.5,1.75],
            receptors='1..16 receptors, at least one required receptor at each height',
            arithmetic='AppleClang 17 arm64, fp_contract=on; serial or OpenMP teams 1..4'),
        predictor='Positive finite short/long vector and speed p95/max ratios (25/100 sweeps), 0.02<=q<cap, ratios within factor two; safety*max(delta25*q/(1-q),delta100*q^4/(1-q^4)). Every required receptor and both moving peaks checked. Three consecutive candidate checkpoints after warm-up.',
        safeguards='Fresh global and each compiled region: L/Uref scaled interior mass max<=1e-3,RMS<=1e-4; completed-iterate residual max<=1e-3,RMS<=1e-4 using global RHS normalization. Preserve separately reported top band/highest-shell limitations.',
        failures='Zero allowed false acceptances in the declared held-out release scope; unsupported/unqualified configurations bounded and unaccepted. Failed held-out scope requires explicit restriction or a new policy with new unseen validation; no threshold tuning on these cases.',
        bounded=dict(worker_seconds=30,shard_seconds=180,total_worker_limit=100,total_seconds=600),
        online=dict(repetitions=3,max_iterations=2000,seconds=5.,checkpoint_interval=25),
        followups=['Full API cost and output transfer','50/150ms budget misses','invalid receptor/empty support','scope rejection: grids/models/turbulence/precision/size/builds','deadline precedence injected clock','plateau and slow/unstable decay','method cache/reuse/reset','serial/team parity'],
        qualification='Numerical empirical pedestrian ROI/receptor scope only. Not full-volume, turbulence, grid independence, physical comfort or gust validation.')
    write(out/'protocol.json',p)
    tree=out/'calibration-tree';tree.mkdir()
    parent=ROOT/'docs/data/solver-control-s6/sources.tar.gz'
    if digest(parent)!=PARENT:raise ValueError('Changed S6 implementation')
    shutil.copyfile(parent,out/'parent-sources.tar.gz')
    with tarfile.open(parent) as a:a.extractall(tree,filter='data')
    for rel in ['tools/solver_numerics_probe.cpp','tools/solver_policy_study_json.h']:
        shutil.copyfile(ROOT/rel,tree/rel)
    for rel in ['tools/run_solver_policy_study.py','tools/solver_policy_replay.py','tools/run_solver_numerics.py']:
        shutil.copyfile(ROOT/rel,out/Path(rel).name)
    index={f.relative_to(tree).as_posix():digest(f) for f in tree.rglob('*') if f.is_file()}
    write(out/'calibration-source-index.json',index)
    with tarfile.open(out/'calibration-sources.tar.gz','w:gz') as a:
        for name in sorted(index):a.add(tree/name,arcname=name,recursive=False)
    for label,cmd in [
        ('configure',['cmake','-S',str(tree),'-B',str(out/'calibration-native'),'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}','-DDTCC_QES_BUILD_TESTS=ON','-DDTCC_QES_OPENMP=ON']),
        ('build',['cmake','--build',str(out/'calibration-native'),'--target','solver_numerics_probe','-j8'])]:
        r=subprocess.run(cmd,text=True,capture_output=True,timeout=180);(out/f'calibration-{label}.log').write_text(r.stdout+r.stderr);r.check_returncode()
    write(out/'calibration-execution.json',dict(executable_sha256=digest(out/'calibration-native/solver_numerics_probe'),
        protocol_sha256=digest(out/'protocol.json'),source_sha256=digest(out/'calibration-sources.tar.gz')))
    return p


def compare(a,b,n,speed):
    values=compare_samples(a,b,n)
    for h in values:
        for key in ['p95','maximum']:
            if h[key] is not None:h[key]*=5/speed
    return values


def qualify(rows,folder):
    groups={}
    for r in rows:
        if r['request']['purpose']=='reference':groups.setdefault(r['request']['case'],[]).append(r)
    records=[]
    for name,group in groups.items():
        group=sorted(group,key=lambda r:r['request']['iterations']);spec=json.loads((folder/f'cases/{name}.json').read_text())
        accepted=len(group)==3 and [r['request']['iterations'] for r in group]==[500,1000,2000] and all(r['status']=='completed' for r in group)
        record=dict(case=name,qualified=False,pairs=[],mass=[])
        if accepted:
            arrays=[]
            for r in group:
                with np.load(folder/f"{r['request']['id']}.npz") as a:arrays.append(a['samples'][-1])
                md=r['result']['checkpoints'][-1]['mass'];scale=23.7/spec['speed']
                record['mass'].append(dict(maximum=md['maximum']*scale,rms=md['rms']*scale))
            record['pairs']=[compare(a,b,group[0]['result']['plane_points'],spec['speed']) for a,b in zip(arrays,arrays[1:])]
            accepted=(len({tuple(r['result']['initial_hashes']) for r in group})==1
                and all(m['maximum']<=1e-3 and m['rms']<=1e-4 for m in record['mass'])
                and all(h['maximum'] is not None and h['maximum']<=1e-3 and h['p95']<=5e-4
                        and h['validity_changes']==0 and h['required_valid'] for pair in record['pairs'] for h in pair))
        record['qualified']=bool(accepted);records.append(record)
    return records


def oracle(row,folder,ref):
    spec=json.loads((folder/f"cases/{row['request']['case']}.json").read_text())
    with np.load(folder/f"{ref['request']['id']}.npz") as v:reference=v['samples'][-1]
    with np.load(folder/f"{row['request']['id']}.npz") as v:samples=v['samples']
    result=[]
    for sample in samples:
        heights=compare(sample,reference,row['result']['plane_points'],spec['speed'])
        result.append(dict(heights=heights,passed=all(h['maximum'] is not None and h['maximum']<=1e-3 and h['p95']<=5e-4
                          and h['required_valid'] and not h['validity_changes'] for h in heights)))
    return result


def fixed_worker(out,case,purpose,iterations,rows):
    request=dict(id=f'fixed-{len(rows):02}',case=case['name'],purpose=purpose,iterations=iterations,cadence=25,
                 direction=case['direction'],precision='float64' if purpose=='reference' else 'float32',omega=1.78 if purpose=='reference' else 1.90)
    row=dict(request=request);ident=request['id'];tokens=stdin_for(case,request).split();tokens[4]=str(case['speed']);data=' '.join(tokens)+'\n'
    (out/f'{ident}.stdin').write_text(data)
    print(ident,case['name'],purpose,iterations,flush=True)
    try:
        r=subprocess.run([str(out/'calibration-native/solver_numerics_probe'),request['precision'],str(out/f'{ident}.bin'),'0',str(request['omega']),'0','1'],
            input=data,text=True,capture_output=True,timeout=30,env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
        (out/f'{ident}.log').write_text(r.stdout+'\n'+r.stderr);r.check_returncode();value=json.loads(r.stdout)
        if value['team']!=4 or value['checkpoints'][-1]['iteration']!=iterations:raise ValueError('Wrong work/team')
        a=np.fromfile(out/f'{ident}.bin',np.float64).reshape(len(value['checkpoints']),value['checkpoints'][0]['samples'],4)
        np.savez_compressed(out/f'{ident}.npz',samples=a,iterations=[c['iteration'] for c in value['checkpoints']]);(out/f'{ident}.bin').unlink()
        row.update(status='completed',result=value)
    except (subprocess.SubprocessError,ValueError) as e:row.update(status='failed',error=str(e))
    rows.append(row);write(out/'fixed-results.json',dict(rows=rows));return row


def calibrate(out):
    p=protocol(out);rows=[];start=time.monotonic()
    for name in p['calibration']:
        case=json.loads((out/f'cases/{name}.json').read_text())
        for n in [500,1000,2000]:fixed_worker(out,case,'reference',n,rows)
        fixed_worker(out,case,'calibration',2000,rows)
        if time.monotonic()-start>180:raise ValueError('Calibration shard exhausted; no retry')
    refs=qualify(rows,out);write(out/'calibration-references.json',refs)
    if len(refs)!=3 or not all(r['qualified'] for r in refs):raise ValueError('Calibration references unqualified; policy remains unreleased')
    histories=[r for r in rows if r['request']['purpose']=='calibration'];trials=[]
    for params in p['calibration_parameters']:
        records=[]
        for row in histories:
            case=json.loads((out/f"cases/{row['request']['case']}.json").read_text())
            ref=next(r for r in rows if r['request']['case']==case['name'] and r['request']['purpose']=='reference' and r['request']['iterations']==2000)
            truth=oracle(row,out,ref);estimated=replay(row['result']['checkpoints'],params,case['speed'])
            false=[e['iteration'] for e,t in zip(estimated,truth) if e['accepted'] and not t['passed']]
            hits=[e['iteration'] for e in estimated if e['accepted']]
            records.append(dict(case=case['name'],false_acceptances=false,first_accept=hits[0] if hits else None))
        eligible=all(not r['false_acceptances'] and r['first_accept'] is not None for r in records)
        trials.append(dict(parameters=params,records=records,eligible=eligible,
                           cost=sum(r['first_accept'] for r in records)/len(records) if eligible else None))
    feasible=[r for r in trials if r['eligible']]
    write(out/'calibration-trials.json',trials)
    if not feasible:raise ValueError('No calibrated candidate; policy remains unreleased')
    selected=min(feasible,key=lambda r:(r['cost'],-r['parameters']['safety_factor'],-r['parameters']['minimum_iterations'],r['parameters']['maximum_ratio']))
    write(out/'policy-freeze.json',dict(policy=POLICY,method=METHOD,parameters=selected['parameters'],selection=selected,
        protocol_sha256=digest(out/'protocol.json'),calibration_results_sha256=digest(out/'fixed-results.json'),
        validation_started=False,scope=p['scope'],target=TARGET))
    print(json.dumps(selected,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--calibrate',type=Path,required=True)
    a=p.parse_args();calibrate(a.calibrate.resolve())
if __name__=='__main__':main()
