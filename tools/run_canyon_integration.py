"""Fresh 74-answer engineering comparison against a frozen canyon AIJ archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'validation')]
import numpy as np
from aij import campaigns,runner,compare,metrics
from aij.canyon import CanyonSession,native_mass,mass_gate
from aij.evidence import file_hash,write_json
from aij.workers import run_worker
from rerun_regression import accuracy,equal_values
import report_validation as reports

MODELS=('legacy','joined_v1')
def specs():return campaigns.ab_baseline()+campaigns.baseline()
def array_hash(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def record(root,spec,model):return json.loads((root/model/spec.case/(spec.key+'.json')).read_text())
def worker_name(index,model):return f'{index:02}-{model}'
def identity(archive):
 from dtcc_qes import _qes
 paths=[ROOT/'CMakeLists.txt',ROOT/'pyproject.toml',ROOT/'uv.lock',Path(__file__).resolve(),
        *sorted((ROOT/'src').rglob('*.h')),*sorted((ROOT/'src').rglob('*.cpp')),
        *sorted((ROOT/'src/dtcc_qes').glob('*.py')),*sorted((ROOT/'validation/aij').glob('*.py')),
        ROOT/'validation/rerun_regression.py',ROOT/'validation/report_validation.py']
 return dict(source={str(p.relative_to(ROOT)):file_hash(p) for p in paths},
  native_sha256=file_hash(_qes.__file__),policy=_qes.solver_policy_revision,
  archive={str(p.relative_to(archive)):file_hash(p) for s in specs() for m in MODELS for p in
           [archive/m/s.case/(s.key+'.json'),archive/m/s.case/(s.key+'.npz')]})

def worker(out,index,model):
 from dtcc_qes import wind,_qes
 manifest=json.loads((out/'manifest.json').read_text());archive=Path(manifest['archive'])
 if identity(archive)!=manifest['identity']:raise ValueError('Changed source/native/archive epoch')
 s=specs()[index];name=worker_name(index,model);folder=out/'workers'/name;folder.mkdir(parents=True,exist_ok=False)
 args=runner.inputs(s);session=CanyonSession();captured=[];original=wind.run;started=perf_counter()
 def solve(city,profile,**settings):
  settings['max_cells']=int(np.iinfo(np.int32).max)
  result,stages=session.run(dict(args,city=city,profile=profile,run=settings),model=model,
                           capture=True,trace=False,baseline_turbulence=True)
  captured.append((result,stages));return result
 try:
  wind.run=solve;data,planes=runner.run(s)
 finally:wind.run=original;session.close()
 if len(captured)!=1:raise ValueError('Exactly one native answer required')
 result,stages=captured.pop();e=result.metadata['experiment']
 np.save(folder/'initial-W.npy',e['canyon_initial_w'])
 np.savez_compressed(folder/'stage-samples.npz',velocity=stages['velocity'],method=stages['method'].astype('U20'),xyz=args['probes'].xyz)
 research={k:v for k,v in e.items() if k.startswith('canyon_') and k not in ('canyon_initial_w','canyon_roof_trace')}
 research.update(model=model,actual_threads=e['actual_threads'],stage_names=stages['stages'],
  stage_parity=stages['final_bitwise_parity'],finite=bool(np.isfinite(result.velocity).all()),
  mass=native_mass(result,args['reference_speed']),boundary_area=e['boundary_flux_area'],
  full_velocity_sha256=array_hash(result.velocity),full_flags_sha256=array_hash(result.cell_flags),
  full_stress_sha256=None if result.turbulence is None else array_hash(result.turbulence.stress),initial_W_sha256=array_hash(e['canyon_initial_w']))
 data['canyon_validation']=research;path=runner.write(data,planes,out/model/s.case)
 data=json.loads(path.read_text());oldpath=archive/model/s.case/(s.key+'.json');old=json.loads(oldpath.read_text());previous=old['canyon_validation']
 checks=accuracy(data,old,path.with_suffix('.npz'),oldpath.with_suffix('.npz'))['checks']
 if s.case in 'AB':checks['centreline']=equal_values(data['centreline'],old['centreline'])
 for key in ['full_velocity_sha256','full_flags_sha256','full_stress_sha256','initial_W_sha256']:
  checks[key]=research[key]==previous[key]
 for key in ['canyon_model','canyon_spec_sha256','canyon_roof_protection_revision','canyon_qualified','canyon_fallback','canyon_changed_faces','canyon_fallback_reasons','canyon_writes','canyon_roof_changes','canyon_voxel_roof_changes','canyon_W_changes','canyon_core_u','canyon_core_v','canyon_core_w','canyon_roof_skipped','canyon_audit_zones','mass','boundary_area','stage_names']:
  checks[key]=equal_values(research[key],previous[key])
 oldstage=archive/'workers'/f'{index:02}-{s.case}-{s.state}-{s.label.replace(" ", "")}-{model}'/'stage-samples.npz'
 with np.load(folder/'stage-samples.npz') as a,np.load(oldstage) as b:
  checks['archive_stages']=set(a.files)==set(b.files) and all(a[k].dtype==b[k].dtype and a[k].shape==b[k].shape and a[k].tobytes()==b[k].tobytes() for k in a.files)
 checks.update(threads=e['actual_threads']==4,stage_parity=stages['final_bitwise_parity'],finite=research['finite'],
  roof=e['canyon_roof_changes']==0,voxel=e['canyon_voxel_roof_changes']==0,W=e['canyon_W_changes']==0,
  model=e['canyon_model']==model,hook_disabled=not hasattr(_qes.WindRunner(),'_test_canyon_failure'))
 if identity(archive)!=manifest['identity']:raise ValueError('Changed epoch after native answer')
 write_json(folder/'worker.json',dict(complete=True,passed=all(checks.values()),checks=checks,
  record_path=str(path),record_sha256=file_hash(path),planes_sha256=file_hash(path.with_suffix('.npz')),
  seconds=perf_counter()-started,peak_rss_bytes=runner._peak_rss(),experiment=research))
 print(name,'passed' if all(checks.values()) else 'gate_failed',flush=True)

def summarize(out):
 conditions=[];checks={}
 for i,s in enumerate(specs()):
  a,b=[record(out,s,m) for m in MODELS];x,y=[r['canyon_validation'] for r in (a,b)]
  mass=mass_gate(y['mass'],x['mass'],a['profile']['reference_speed'],x['boundary_area'])
  local=dict(W=x['initial_W_sha256']==y['initial_W_sha256'],roof=y['canyon_roof_changes']==y['canyon_voxel_roof_changes']==0,
   mass=all(mass.values()),sampling=equal_values(a['probes']['method'],b['probes']['method']))
  inactive=y['canyon_changed_faces']==0
  if inactive:local.update(inactive_velocity=x['full_velocity_sha256']==y['full_velocity_sha256'],inactive_stress=x['full_stress_sha256']==y['full_stress_sha256'])
  conditions.append(dict(case=s.case,state=s.state,label=s.label,key=s.key,changed_faces=y['canyon_changed_faces'],qualified=y['canyon_qualified'],checks=local,mass_guards=mass))
  for m in MODELS:
   w=json.loads((out/'workers'/worker_name(i,m)/'worker.json').read_text());checks[worker_name(i,m)]=w['passed']
 records={m:compare.load_records(out/m,specs()) for m in MODELS};scores={}
 for m in MODELS:
  comparisons=[c for case in 'AB' for c in compare.isolated(records[m],case)]+compare.case_d(records[m])+compare.case_e_comparisons(records[m])
  scores[m]={c.name:reports._comparison_summary(c) for c in comparisons}
 report=dict(complete=True,passed=all(checks.values()) and all(all(r['checks'].values()) for r in conditions),native_matrix_answers=74,
  active_conditions=sum(r['changed_faces']>0 for r in conditions),conditions=conditions,workers=checks,scores=scores,
  physical_promotion=False,numerical_scope='Matched historical fixed-work float32 answers; no tolerance-convergence or speedup claim')
 write_json(out/'summary.json',report)
 lines=['# Combined integration AIJ comparison','',f"74/74 answers completed. Engineering parity: {report['passed']}. Active conditions: {report['active_conditions']}.",'',
 '| Quantity | Legacy MAE | Joined MAE | Change |','| --- | ---: | ---: | ---: |']
 for name in scores['legacy']:
  a,b=[scores[m][name]['pooled']['mae'] for m in MODELS]
  lines.append(f'| {name} | {a:.9f} | {b:.9f} | {100*(b/a-1):+.3f}% |')
 lines+=['','Full fields, flags, stresses, W, canonical records/planes and contributor stages reproduce the post-fix archive. The known D regression remains; legacy stays the default.','',report['numerical_scope']+'.']
 (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
 if not report['passed']:raise ValueError('Engineering comparison failed; inspect immutable outputs')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path);p.add_argument('--worker',action='store_true');p.add_argument('--index',type=int);p.add_argument('--model',choices=MODELS);a=p.parse_args();out=a.output.resolve()
 if a.worker:worker(out,a.index,a.model);return
 out.mkdir(parents=True,exist_ok=False);archive=a.archive.resolve()
 assert len(specs())==37
 write_json(out/'manifest.json',dict(archive=str(archive),identity=identity(archive),specs=[s.to_dict() for s in specs()],
  matrix_attempts=74,models=MODELS,native_threads=4,blas_threads=1,memory_cap=None,deadlines_seconds=dict(A=180,B=180,D=60,E=120)))
 outcomes=[]
 for i,s in enumerate(specs()):
  for m in MODELS:
   name=worker_name(i,m);ticket=out/'tickets'/(name+'.json');ticket.parent.mkdir(exist_ok=True)
   with ticket.open('x') as f:json.dump(dict(index=i,model=m,status='started'),f)
   print(f'{len(outcomes)+1}/74 {s.case} {s.state} {s.label} {m}',flush=True)
   r=run_worker([sys.executable,'-B',str(Path(__file__).resolve()),'--output',str(out),'--worker','--index',str(i),'--model',m],out/'logs'/(name+'.log'),deadline=180 if s.case in 'AB' else 60 if s.case=='D' else 120)
   outcomes.append(dict(index=i,model=m,**r));write_json(out/'outcomes.json',outcomes)
   if not r['complete']:raise ValueError('Worker failed; preserve this campaign without replenishing attempts')
 summarize(out);print('All 74 answers reproduce the frozen post-fix archive',flush=True)
if __name__=='__main__':main()
