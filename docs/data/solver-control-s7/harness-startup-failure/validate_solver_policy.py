"""Frozen S7 online API workers and held-out error audit (no Python stop loop)."""
from __future__ import annotations
import argparse
from dataclasses import asdict,replace
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import tarfile
import time
import numpy as np
from run_solver_numerics import digest,write
from run_solver_policy_study import compare
from compare_native_builds import stage_package


def snapshot(out):
    if (out/'online-protocol.json').exists():raise ValueError('Online protocol already frozen; no overwrites')
    tree=out/'tree';index={f.relative_to(tree).as_posix():digest(f) for f in tree.rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    write(out/'source-index.json',index)
    with tarfile.open(out/'sources.tar.gz','w:gz') as a:
        for name in sorted(index):a.add(tree/name,arcname=name,recursive=False)
    stage_package(tree,next((out/'native').glob('_qes*.so')),out/'package')
    for name in ['validate_solver_policy.py','run_solver_policy_study.py','solver_policy_replay.py','run_solver_numerics.py']:
        shutil.copyfile(Path(__file__).parent/name,out/name)
    base=json.loads((out/'draft2-protocol.json').read_text());rows=[]
    for rep in range(3):
        for name in base['validation']:
            rows.append(dict(case=name,variant='adaptive',rep=rep,threads=4,budget=5.,iterations=2000))
    for name in base['validation']:rows.append(dict(case=name,variant='legacy',rep=0,threads=4,budget=5.,iterations=2000))
    # Fixed finite controls, not replacements for the held-out runs.
    for budget in [.05,.15,1e-12]:
        for name in ['val_staggered_240','val_courtyards_315']:
            rows.append(dict(case=name,variant='adaptive',rep=0,threads=4,budget=budget,iterations=2000))
    for variant in ['invalid_receptor','unqualified_profile','unqualified_precision','early_limit','legacy_converged_unaccepted']:
        rows.append(dict(case='val_staggered_240',variant=variant,rep=0,threads=4,budget=5.,iterations=1 if variant in ['early_limit','legacy_converged_unaccepted'] else 2000))
    for team in [1,2]:
        for name in ['val_staggered_240','val_staggered_graded_150']:
            rows.append(dict(case=name,variant='adaptive',rep=0,threads=team,budget=5.,iterations=2000))
    for i,row in enumerate(rows):row['id']=f'online-{i:02}'
    p=dict(policy_freeze_sha256=digest(out/'policy-freeze.json'),scope_restriction_sha256=digest(out/'scope-restriction.json'),
        sources_sha256=digest(out/'sources.tar.gz'),extension_sha256=digest(next((out/'native').glob('_qes*.so'))),
        zero_false_acceptances_required=True,worker_seconds=30,shard_seconds=180,rows=rows,
        platform=platform.platform(),timing='Full wind.run API including extraction, preparation, solve, finalization and NumPy conversion. Separate City load/sampling/hash; process wall recorded by supervisor. No warm-up solve.')
    write(out/'online-protocol.json',p);return p


def worker(out,request,package,output):
    from dtcc_qes import wind,_qes
    import dtcc_qes
    from dtcc_core.model import City,Building,Surface,GeometryType
    if not Path(_qes.__file__).resolve().is_relative_to(package):raise ValueError('Wrong package')
    spec=json.loads((out/f"cases/{request['case']}.json").read_text())
    city=City()
    for i,item in enumerate(spec['buildings']):
        b=Building(id=str(i));b.measured_height=item['height'];vertices=np.c_[np.asarray(item['vertices']),np.zeros(len(item['vertices']))]
        b.add_geometry(Surface(vertices=vertices),GeometryType.LOD0);city.add_building(b)
    dz=np.array(spec['solver_dz'],dtype=float)
    if request['variant']=='unqualified_profile':dz[:2]=[.9,1.5]
    nz,ny,nx=spec['expected_shape']
    options=dict(bounds=(0,0,0,nx*2,ny*2,float(dz.sum())),resolution=2.,max_cells=400000,
                 max_iterations=request['iterations'],tolerance=.1 if request['variant']=='legacy_converged_unaccepted' else 1e-5)
    if not np.all(dz==2):options['vertical_grid']=wind.VerticalGrid.from_faces(np.r_[0,np.cumsum(dz)])
    if request['variant']=='unqualified_precision':options['solver_precision']='float64'
    receptors=tuple(wind.Receptor(f'r{i}-h{h}',x,y,h) for i,(x,y) in enumerate(spec['receptors']) for h in [1.5,1.75])
    if request['variant']=='invalid_receptor':
        x,y=spec['buildings'][0]['vertices'][0];receptors=(wind.Receptor('solid',x+4,y+4,1.5),)+receptors
    if request['variant']!='legacy':
        monitor=wind.MonitorSpec(tuple(spec['roi']),receptors=receptors,history_limit=16)
        options['solver_control']=wind.SolverControl(request['budget'],monitor,mode='adaptive')
    started=time.perf_counter()
    try:
        result=wind.run(city,spec['speed'],spec['direction'],**options)
    except (wind.BudgetExhaustedError,wind.NumericalFailureError) as e:
        write(output,dict(request=request,status='budget_exhausted' if isinstance(e,wind.BudgetExhaustedError) else 'numerical_failure',
                          api_seconds=time.perf_counter()-started,control=e.record));return
    api=time.perf_counter()-started
    samples=[];planes=[];nplane=0
    for h in [1.5,1.75]:
        plane=result.sample(h,method='linear');planes.append(plane);r=spec['roi']
        x=(plane.x>=r[0])&(plane.x<r[1]);y=(plane.y>=r[2])&(plane.y<r[3]);v=plane.velocity[y][:,x];valid=plane.valid[y][:,x]
        nplane=int(valid.size);samples.extend(np.c_[v.reshape(-1,3),valid.ravel()])
    def point(plane,x,y):
        axes=[plane.x.astype(float),plane.y.astype(float)];supports=[]
        for axis,p in zip(axes,[x,y]):
            hi=int(np.searchsorted(axis,p))
            if hi==len(axis) or p<axis[0]:return [np.nan,np.nan,np.nan,0]
            if axis[hi]==p:supports.append([(hi,1.)])
            else:
                t=(p-axis[hi-1])/(axis[hi]-axis[hi-1]);supports.append([(hi-1,1-t),(hi,t)])
        v=np.zeros(3)
        for i,wx in supports[0]:
            for j,wy in supports[1]:
                if not plane.valid[j,i]:return [np.nan,np.nan,np.nan,0]
                v+=wx*wy*plane.velocity[j,i]
        return [*v,1]
    for x,y in spec['receptors']:
        for plane in planes:samples.append(point(plane,x,y))
    np.savez_compressed(output.with_suffix('.npz'),samples=np.asarray(samples))
    fields={name:hashlib.sha256(getattr(result,name).tobytes()).hexdigest() for name in ['velocity','cell_flags','x','y','z','z_faces']}
    write(output,dict(request=request,status='completed',api_seconds=api,diagnostics=asdict(result.diagnostics),
        control=result.control,shape=list(result.cell_flags.shape),plane_points=nplane,field_hashes=fields,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        native_build=result.metadata['versions']['native_build'],extension_sha256=digest(_qes.__file__),
        transfer_included=True,owned_outputs=result.velocity.flags.owndata and result.cell_flags.flags.owndata))


def analyze(out):
    refs=json.loads((out/'all-reference-qualification.json').read_text());qualified={r['case']:r['qualified'] for r in refs}
    fixed=json.loads((out/'validation-fixed-results.json').read_text())['rows']
    rows=json.loads((out/'online-results.json').read_text())['rows'];records=[]
    for row in rows:
        req=row['request'];case=json.loads((out/f"cases/{req['case']}.json").read_text());accepted=bool(row.get('control') and row['control']['accepted'])
        record=dict(id=req['id'],case=req['case'],variant=req['variant'],accepted=accepted,
                    reference_qualified=qualified[req['case']],false_acceptance=False,missed_acceptance=False)
        if row['status']=='completed' and qualified[req['case']] and req['variant'] not in ['unqualified_profile']:
            ref=next(r for r in fixed if r['request']['case']==req['case'] and r['request']['purpose']=='reference' and r['request']['iterations']==2000)
            with np.load(out/f"{ref['request']['id']}.npz") as a, np.load(out/f"{req['id']}.npz") as b:
                heights=compare(a['samples'][-1],b['samples'],row['plane_points'],case['speed'])
            actual_pass=all(h['maximum'] is not None and h['maximum']<=1e-3 and h['p95']<=5e-4 and h['required_valid'] and not h['validity_changes'] for h in heights)
            record.update(heights=heights,actual_observable_target=actual_pass,false_acceptance=accepted and not actual_pass,
                          missed_acceptance=not accepted and actual_pass and req['variant']=='adaptive' and req['budget']==5.)
        if accepted and not qualified[req['case']]:record['false_acceptance']=True
        records.append(record)
    useful=[r for r in rows if r['request']['variant']=='adaptive' and r['request']['budget']==5. and r['request']['threads']==4]
    summary=dict(policy='pedestrian-v1',workers=len(rows),false_acceptances=sum(r['false_acceptance'] for r in records),
                 missed_acceptances=sum(r['missed_acceptance'] for r in records),records=records,
                 release_candidates=len(useful),accepted_candidates=sum(bool(r.get('control') and r['control']['accepted']) for r in useful))
    write(out/'online-summary.json',summary);return summary


def run(out):
    p=snapshot(out);rows=[];started=time.monotonic()
    for i,req in enumerate(p['rows']):
        print(f"[{i+1}/{len(p['rows'])}] {req['variant']} {req['case']} rep={req['rep']} team={req['threads']} budget={req['budget']}",flush=True)
        t=time.monotonic();path=out/f"{req['id']}.json"
        r=subprocess.run([sys.executable,str(out/'validate_solver_policy.py'),'--worker',str(out),'--request',json.dumps(req),'--package',str(out/'package'),'--output',str(path)],
            text=True,capture_output=True,timeout=30,env=os.environ|{'PYTHONPATH':str(out/'package'),'OMP_NUM_THREADS':str(req['threads']),'OMP_DYNAMIC':'FALSE','PYTHONDONTWRITEBYTECODE':'1'})
        (out/f"{req['id']}.log").write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError(f"Worker failed: {req['id']}\n{r.stderr[-3000:]}")
        row=json.loads(path.read_text());row['process_seconds']=time.monotonic()-t;rows.append(row)
        write(out/'online-results.json',dict(rows=rows))
        if time.monotonic()-started>600:raise ValueError('Online cap exhausted; no retry')
    print(json.dumps(analyze(out),indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path);p.add_argument('--analyze',type=Path)
    p.add_argument('--worker',type=Path);p.add_argument('--request');p.add_argument('--package',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.worker:worker(a.worker,json.loads(a.request),a.package.resolve(),a.output)
    elif a.analyze:print(json.dumps(analyze(a.analyze.resolve()),indent=2))
    elif a.study:run(a.study.resolve())
    else:p.error('--study, --analyze or --worker required')
if __name__=='__main__':main()
