"""Portable S7 audit. Replays references, both calibration drafts and API decisions.

Only compact output planes/receptors are retained. Default-volume parity is
replayed from per-array dtype/shape/SHA-256 records, not reconstructed volumes.
Completed-iterate residual primitives are producer diagnostics, independently
unit-tested in S5b; they cannot be recomputed from pedestrian samples alone.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tarfile
sys.dont_write_bytecode=True
import numpy as np
from run_solver_numerics import digest
from run_solver_policy_study import qualify,oracle,compare
from solver_policy_replay import TARGET,prediction,replay


def array_errors(a,b,n,uref):
    out=[]
    for h in range(2):
        ids=np.arange(h*n,(h+1)*n);required=np.arange(2*n+h,len(a),2)
        valid=(a[:,3]==1)&(b[:,3]==1)
        def norm(indices):
            indices=indices[valid[indices]]
            if not len(indices):return dict(vector_maximum=None,vector_p95=None,speed_maximum=None,speed_p95=None)
            v=np.linalg.norm(a[indices,:3]-b[indices,:3],axis=1)/uref
            s=np.abs(np.linalg.norm(a[indices,:3],axis=1)-np.linalg.norm(b[indices,:3],axis=1))/uref
            return dict(vector_maximum=float(v.max()),vector_p95=float(np.percentile(v,95)),
                        speed_maximum=float(s.max()),speed_p95=float(np.percentile(s,95)))
        roi=norm(ids);req=norm(required)
        peaks=[]
        for values in [a,b]:
            speeds=np.where(valid[ids],np.linalg.norm(values[ids,:3],axis=1),-1)
            peaks.append(int(ids[np.argmax(speeds)]))
        out.append(dict(roi=roi,required=req,moving_peaks=norm(np.array(peaks)),
            validity_changes=int(np.count_nonzero(a[np.r_[ids,required],3]!=b[np.r_[ids,required],3])),
            required_valid=bool(np.all(valid[required])),roi_valid=int(valid[ids].sum())))
    return out


def monitor_input(c):
    def window(w):
        return dict(available=w['available'],from_iteration=w['from_iteration'],to_iteration=w['to_iteration'],
            common_valid=w['common_valid'],validity_changes=w['validity_changes'],vector=w['vector_over_uref'],speed=w['speed_factor_change'],
            ratios=[w['ratios'][k] for k in ['vector_p95','vector_max','speed_p95','speed_max']],
            hotspots=[dict(present=h['present'],before_valid=h['before']['valid'],current_valid=h['current']['valid']) for h in w['hotspots']])
    return dict(iteration=c['iteration'],monitor=dict(required_valid=c['required_receptors_valid'],
        heights=[dict(valid=h['valid'],short=window(h['short_change']),long=window(h['long_change'])) for h in c['heights']],
        receptors=[dict(valid=r['sample']['valid'],required=r['required'],short=window(r['short_change']),long=window(r['long_change'])) for r in c['receptors']]))


def estimate_trace(checkpoints,params):
    # Independent transport check against the stored public monitor summaries.
    anchor=None;previous=None;out=[]
    for c in checkpoints:
        p=prediction(c,params,5);fresh=dict(p);stable=c['monitor']['required_valid'];deltas=[]
        for point in c['monitor']['heights']+[r for r in c['monitor']['receptors'] if r['required']]:
            w=point['short'];v=w['vector']['maximum'];s=w['speed']['maximum']
            stable=stable and w['available'] and not w['validity_changes'] and w['common_valid']>0 and v is not None and s is not None
            if v is not None and s is not None:deltas.append((v,s))
        if anchor:
            if not stable or previous is None or c['iteration']-previous!=25 or c['iteration']-anchor['iteration']>100:anchor=None
            else:anchor['vector']+=max(v for v,s in deltas);anchor['speed']+=max(s for v,s in deltas)
        if fresh['available'] and (anchor is None or max(fresh['vector_maximum'],fresh['speed_maximum'])<=max(anchor['vector'],anchor['speed'])):
            anchor=dict(iteration=c['iteration'],vector=fresh['vector_maximum'],speed=fresh['speed_maximum'],q_minimum=fresh['q_minimum'],q_maximum=fresh['q_maximum'])
        if anchor and anchor['iteration']!=c['iteration']:
            p.update(available=True,reason='transported_anchor',vector_p95=anchor['vector'],vector_maximum=anchor['vector'],
                speed_p95=anchor['speed'],speed_maximum=anchor['speed'],required_maximum=max(anchor['vector'],anchor['speed']),
                hotspot_maximum=max(anchor['vector'],anchor['speed']),q_minimum=anchor['q_minimum'],q_maximum=anchor['q_maximum'])
        p.update(anchor_iteration=anchor['iteration'] if anchor else None,fresh_tail_available=fresh['available'],current_tail_reason=fresh['reason'])
        previous=c['iteration'];out.append(p)
    return out


def close(a,b):
    if a is None or b is None:return a is b
    if isinstance(a,bool) or isinstance(a,str):return a==b
    return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-15+1e-12*abs(a)


def calibration(folder):
    rows=json.loads((folder/'fixed-results.json').read_text())['rows'];frozen=json.loads((folder/'policy-freeze.json').read_text())
    if len(rows)!=12 or any(r['request']['purpose'] not in ['reference','calibration'] for r in rows):raise ValueError('Calibration contaminated')
    if digest(folder/'fixed-results.json')!=frozen['calibration_results_sha256'] or digest(folder/'draft2-protocol.json')!=frozen['protocol_sha256']:
        raise ValueError('Calibration changed after freezing')
    if digest(folder/'solver_policy_replay.py')!=frozen['predictor_sha256']:raise ValueError('Predictor changed after freezing')
    spec=importlib.util.spec_from_file_location('rejected_fresh_tail',folder/'rejected-fresh-tail-draft/solver_policy_replay.py')
    first=importlib.util.module_from_spec(spec);spec.loader.exec_module(first)
    def trials(fn,protocol):
        records=[]
        for params in protocol['calibration_parameters']:
            cases=[]
            for row in rows:
                if row['request']['purpose']!='calibration':continue
                name=row['request']['case'];ref=next(r for r in rows if r['request']['case']==name and r['request']['purpose']=='reference' and r['request']['iterations']==2000)
                actual=oracle(row,folder,ref);estimated=fn(row['result']['checkpoints'],params,5)
                false=[e['iteration'] for e,t in zip(estimated,actual) if e['accepted'] and not t['passed']]
                hits=[e['iteration'] for e in estimated if e['accepted']]
                cases.append(dict(case=name,false_acceptances=false,first_accept=hits[0] if hits else None))
            eligible=all(not r['false_acceptances'] and r['first_accept'] is not None for r in cases)
            records.append(dict(parameters=params,records=cases,eligible=eligible,
                                cost=sum(r['first_accept'] for r in cases)/len(cases) if eligible else None))
        return records
    rejected=trials(first.replay,json.loads((folder/'rejected-fresh-tail-draft/protocol.json').read_text()))
    if rejected!=json.loads((folder/'rejected-fresh-tail-draft/calibration-trials.json').read_text()) or any(r['eligible'] for r in rejected):
        raise ValueError('Rejected calibration draft changed')
    candidates=trials(replay,json.loads((folder/'draft2-protocol.json').read_text()))
    if candidates!=json.loads((folder/'draft2-trials.json').read_text()):raise ValueError('Calibration replay changed')
    selected=min([r for r in candidates if r['eligible']],key=lambda r:(r['cost'],-r['parameters']['safety_factor'],-r['parameters']['minimum_iterations'],r['parameters']['maximum_ratio']))
    if selected!=frozen['selection']:raise ValueError('Selected policy changed')
    started=json.loads((folder/'validation-reference-start.json').read_text())
    if started['policy_freeze_sha256']!=digest(folder/'policy-freeze.json'):raise ValueError('Held-out data preceded frozen policy')
    return frozen


def sources(folder):
    snapshots={}
    for archive,index in [('calibration-sources.tar.gz','calibration-source-index.json'),('sources.tar.gz','source-index.json'),('release-sources.tar.gz','release-source-index.json')]:
        with tarfile.open(folder/archive) as a:
            members={m.name:a.extractfile(m).read() for m in a if m.isfile()}
        actual={k:hashlib.sha256(v).hexdigest() for k,v in members.items()}
        if actual!=json.loads((folder/index).read_text()):raise ValueError('Source member changed: '+archive)
        snapshots[archive]=members
    release=snapshots['release-sources.tar.gz']
    with tarfile.open(folder/'parent-sources.tar.gz') as a:parent={m.name:a.extractfile(m).read() for m in a if m.isfile()}
    for name,data in parent.items():
        if name.startswith(('src/qes_core/solver/','src/qes_core/winds/','src/qes_core/qes/')) or name in ['src/qes_core/dtcc/model_inputs.cpp','src/qes_core/dtcc/divergence.cpp']:
            if release[name]!=data:raise ValueError('Frozen numerical kernel/condition operator changed: '+name)
    identity=(folder/'validation/solver-policy-identity.txt').read_text();lines=identity.splitlines();revision=hashlib.sha256(identity.encode()).hexdigest()
    names=[]
    for line in lines[1:]:
        name,sha=line.rsplit(' ',1);names.append(name)
        if hashlib.sha256(release[name]).hexdigest()!=sha:raise ValueError('Qualified build identity changed: '+name)
    expected=sorted(k for k in release if ((k.startswith('src/qes_core/') or k.startswith('src/cpp/')) and k.endswith(('.cpp','.h')) and not k.endswith('/pedestrian_qualification.h')) or k in ['CMakeLists.txt','src/qes_core/CMakeLists.txt'])
    if names!=expected:raise ValueError('Incomplete policy identity dependency set')
    if revision not in release['src/qes_core/dtcc/pedestrian_qualification.h'].decode():raise ValueError('Unqualified release identity')
    return revision


def audit(folder,verify_manifest=True):
    if verify_manifest:
        manifest=json.loads((folder/'manifest.json').read_text())
        for name,sha in manifest['files'].items():
            if digest(folder/name)!=sha:raise ValueError('Changed evidence: '+name)
    frozen=calibration(folder);revision=sources(folder)
    fixed=json.loads((folder/'validation-fixed-results.json').read_text())['rows']
    references=qualify(fixed,folder)
    if references!=json.loads((folder/'all-reference-qualification.json').read_text()):raise ValueError('Reference qualification changed')
    qualified={r['case']:r['qualified'] for r in references}
    if len(references)!=10 or sum(qualified.values())!=9 or qualified['val_mixed_graded_domain_300']:
        raise ValueError('Reference scope differs from recorded restriction')
    records=[];all_rows=[];predictions=0;underestimates=0;false=0;missed=0;budget=[]
    for prefix,count in [('',43),('release-',24)]:
        protocol=json.loads((folder/f'{prefix}online-protocol.json').read_text())
        archive=protocol.get('source_archive',f'{prefix}sources.tar.gz')
        if digest(folder/archive)!=protocol['sources_sha256'] or protocol['policy_freeze_sha256']!=digest(folder/'policy-freeze.json'):
            raise ValueError('Measured implementation or policy changed')
        rows=json.loads((folder/f'{prefix}online-results.json').read_text())['rows'];all_rows+=rows
        if len(rows)!=count or [r['request'] for r in rows]!=protocol['rows']:raise ValueError('Online matrix incomplete')
        for row in rows:
            q=row['request'];c=row.get('control');name=q['case'];spec=json.loads((folder/f'cases/{name}.json').read_text())
            accepted=bool(c and c['accepted'])
            if c and c['mode']=='adaptive' and c['method'].endswith('1.90'):
                checkpoints={v['iteration']:v for v in c['checkpoint_history'] if not v['initial']}
                eligible=[v for v in c['assessment_history'] if v['iteration'] in checkpoints]
                estimated=estimate_trace([monitor_input(checkpoints[v['iteration']]) for v in eligible],frozen['parameters'])
                streak=0
                for e,p in zip(eligible,estimated):
                    for key,value in p.items():
                        if not close(value,e['prediction'][key]):raise ValueError(f"Native/replay predictor differs: {q['id']} {e['iteration']} {key}")
                    predictions+=1
                    cp=checkpoints[e['iteration']]
                    scale=23.7/spec['speed']
                    massmax=max(v['divergence']['interior_max']*scale for v in cp['mass'])
                    massrms=max(v['divergence']['interior_rms']*scale for v in cp['mass'])
                    if not close(massmax,e['scaled_mass_maximum']) or not close(massrms,e['scaled_mass_rms']):raise ValueError('Mass evidence differs')
                    numerical=(e['residual_cells']>0 and e['mass_regions']>=3 and 0<=massmax<=1e-3 and 0<=massrms<=1e-4
                        and 0<=e['relative_residual_maximum']<=1e-3 and 0<=e['relative_residual_rms']<=1e-4)
                    if e['safeguards_passed'] and not numerical:raise ValueError('Safeguard accepted failing primitive')
                    candidate=(p['available'] and all(p[k]<=TARGET[k] for k in ['vector_p95','vector_maximum','speed_p95','speed_maximum'])
                               and p['required_maximum']<=1e-3 and p['hotspot_maximum']<=1e-3 and e['safeguards_passed'])
                    streak=streak+1 if candidate else 0
                    if candidate!=e['candidate'] or streak!=e['consecutive'] or e['ready']!=(streak>=3):raise ValueError('Native policy decision differs')
                if accepted and (not eligible or not eligible[-1]['ready'] or not eligible[-1]['accepted']):raise ValueError('Acceptance without current decision')
            if accepted:
                if not qualified[name] or c['accuracy_status']!='accepted' or c['method']!='s5c-rb-sor-float-omega-v1-omega-1.90':raise ValueError('Unsupported acceptance')
                if c['timings']['solve_seconds']>=q['budget'] or c['assessment']['iteration']!=row['diagnostics']['iterations']:
                    raise ValueError('Late or stale acceptance')
                if prefix and c['policy_revision']!=revision:raise ValueError('Accepted different implementation')
                globalmass=next(v for v in c['checkpoint_history'][-1]['mass'] if c['regions'][v['region']]['name']=='global')['divergence']
                if globalmass['interior_max']!=row['diagnostics']['max_divergence'] or globalmass['interior_rms']!=row['diagnostics']['rms_divergence']:
                    raise ValueError('Assessment and returned field differ')
            record=dict(id=q['id'],case=name,accepted=accepted,reference_qualified=qualified[name])
            if row['status']=='completed' and qualified[name] and q['variant']!='unqualified_profile':
                ref=next(r for r in fixed if r['request']['case']==name and r['request']['purpose']=='reference' and r['request']['iterations']==2000)
                with np.load(folder/f"{ref['request']['id']}.npz") as a,np.load(folder/f"{q['id']}.npz") as b:
                    errors=array_errors(a['samples'][-1],b['samples'],row['plane_points'],spec['speed'])
                passed=all(h['required_valid'] and h['validity_changes']==0 and h['roi']['vector_maximum'] is not None
                    and h['roi']['vector_maximum']<=1e-3 and h['roi']['vector_p95']<=5e-4
                    and h['roi']['speed_maximum']<=1e-3 and h['roi']['speed_p95']<=5e-4
                    and h['required']['vector_maximum']<=1e-3 and h['required']['speed_maximum']<=1e-3 for h in errors)
                false+=accepted and not passed
                missed+=not accepted and passed and q['variant']=='adaptive' and q['budget']==5 and qualified[name]
                record['errors']=errors
                if accepted:
                    bounds=c['assessment']['prediction']
                    underestimates+=any(h['roi'][k]>bounds[k]+1e-12 for h in errors for k in ['vector_p95','vector_maximum','speed_p95','speed_maximum'])
            if q['budget']<1:budget.append(dict(id=q['id'],status=row['status'],accepted=accepted,iterations=(row.get('diagnostics') or {}).get('iterations'),api_seconds=row['api_seconds']))
            records.append(record)
    if false or missed:raise ValueError(f'False/missed acceptances: {false}/{missed}')
    # Final source changes add provenance guards only; exact returned fields and
    # decisions must match the first implementation on every full-work condition.
    repeatability=[]
    for row in all_rows:
        q=row['request']
        if not q['id'].startswith('release-') or q['variant'] not in ['adaptive','legacy'] or q.get('backend')=='serial':continue
        prior=next(r for r in all_rows if not r['request']['id'].startswith('release-') and r['request']['case']==q['case'] and r['request']['variant']==q['variant'] and r['request']['rep']==0 and r['request']['threads']==4 and r['request']['budget']==5)
        if row['field_hashes']!=prior['field_hashes'] or row['diagnostics']!=prior['diagnostics']:
            raise ValueError('Provenance changes altered trajectory')
        if row.get('control') and row['control']['accepted']!=prior['control']['accepted']:raise ValueError('Provenance changes altered acceptance')
        repeatability.append(q['id'])
    serial=[]
    for row in all_rows:
        q=row['request']
        if q.get('backend')!='serial':continue
        parallel=next(r for r in all_rows if r['request']['id'].startswith('release-') and r['request']['case']==q['case']
                      and r['request']['variant']=='adaptive' and r['request']['threads']==4)
        if row['field_hashes']!=parallel['field_hashes'] or row['diagnostics']!=parallel['diagnostics'] or not row['control']['accepted']:
            raise ValueError('Serial policy differs from OpenMP')
        serial.append(q['case'])
    for name in qualified:
        group=[r for r in all_rows if not r['request']['id'].startswith('release-') and r['request']['case']==name
               and r['request']['variant']=='adaptive' and r['request']['threads']==4 and r['request']['budget']==5]
        if group and len({json.dumps(r['field_hashes'],sort_keys=True) for r in group})!=1:raise ValueError('Online repetitions differ')
    parity=json.loads((folder/'validation/default-parity.json').read_text())
    if not parity['passed'] or any(c['differences'] for c in parity['comparisons']):raise ValueError('Default parity failed')
    fingerprints=json.loads((folder/'validation/default-array-fingerprints.json').read_text())
    base=next(v['backend_independent_members'] for k,v in fingerprints.items() if 'f138616b7796' in k)
    if any(v['backend_independent_members']!=base for v in fingerprints.values()):raise ValueError('Default array fingerprints differ')
    for backend in ['openmp','serial']:
        group=[v['members'] for k,v in fingerprints.items() if f'-{backend}-' in k]
        baseline={k:v for k,v in group[0].items() if k!='_module'}
        if any({k:v for k,v in m.items() if k!='_module'}!=baseline for m in group):raise ValueError('Same-backend default metadata/arrays differ')
    return dict(stage='S7',policy=frozen['policy'],method=frozen['method'],implementation=revision,
        fixed_workers=len(fixed),api_workers=len(all_rows),total_workers=len(fixed)+len(all_rows),
        qualified_reference_triples=9,unqualified_reference_triples=1,held_out_full_budget_acceptances=sum(r['accepted'] and next(x for x in all_rows if x['request']['id']==r['id'])['request']['budget']==5 for r in records),
        false_acceptances=false,missed_acceptances=missed,predictor_underestimates=underestimates,
        replayed_prediction_checkpoints=predictions,provenance_changes_field_exact=repeatability,
        serial_policy_cases_exact=serial,
        default_comparisons=len(parity['comparisons']),records=records,budgets=budget)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('--write-summary',action='store_true');a=p.parse_args()
    value=audit(a.folder.resolve(),verify_manifest=not a.write_summary)
    if a.write_summary:(a.folder/'summary.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in value.items() if k not in ['records','budgets']},indent=2))
if __name__=='__main__':main()
