"""Complete S6 with first-sweep risk checks and an independent evidence audit.

The main 43-worker protocol is immutable. This separate, predeclared eight-worker
supplement resolves the first 25 sweeps, which the main cadence cannot resolve.
It cannot tune thresholds, choose another factor, or extend the iteration cap.
"""
from __future__ import annotations
import argparse
import hashlib
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
import run_solver_method_study as study
from run_solver_numerics import digest, stdin_for, write


def transient_summary(folder):
    rows=json.loads((folder/'transients/results.json').read_text())['rows']
    summaries=[]
    for row in rows:
        request=row['request']
        if row['status']!='completed':
            summaries.append(dict(request=request,passed=False));continue
        c=row['result']['checkpoints']
        def ratios(key,field):
            return [x[key][field]/max(c[0][key][field],1e-30) for x in c]
        growth=dict(residual_maximum=max(ratios('residual','maximum')),
                    residual_rms=max(ratios('residual','rms')),
                    mass_maximum=max(ratios('mass','maximum')),
                    mass_rms=max(ratios('mass','rms')))
        summaries.append(dict(request=request,growth=growth,
            passed=all(math.isfinite(v) and v<=10 for v in growth.values())))
    return summaries


def supplement(folder):
    extra=folder/'transients';extra.mkdir(exist_ok=False)
    exe=folder/'native/solver_numerics_probe'
    execution=json.loads((folder/'execution.json').read_text())
    if digest(exe)!=execution['executable_sha256']:raise ValueError('Changed measured executable')
    protocol=json.loads((folder/'protocol.json').read_text())
    plan=dict(reason='Main cadence 25 does not resolve the first 25 sweeps. Diagnostic-only supplement, frozen before running; does not retune or repeat the main method selection.',
        cases=protocol['screen_cases'],omegas=study.OMEGAS,precision='float32',iterations=25,cadence=1,
        workers=8,worker_seconds=30,total_seconds=30,
        veto='Any selected-factor worker failure, nonfinite diagnostic, or maximum/RMS residual or interior-mass growth above 10 times its initial value vetoes the scoped opt-in. No replacement candidate selected.',
        executable_sha256=digest(exe),main_protocol_sha256=digest(folder/'protocol.json'))
    write(extra/'protocol.json',plan)
    shutil.copyfile(Path(__file__),folder/'complete_solver_s6.py')
    rows=[];start=time.monotonic()
    for case in plan['cases']:
        spec=json.loads((folder/f'cases/{case}.json').read_text())
        for omega in plan['omegas']:
            request=dict(id=f'{len(rows):02}',case=case,purpose='early_transient',omega=omega,
                         precision='float32',iterations=25,cadence=1,direction=270)
            row=dict(request=request);ident=request['id'];data=stdin_for(spec,request)
            (extra/f'{ident}.stdin').write_text(data)
            try:
                remaining=30-(time.monotonic()-start)
                if remaining<=0:raise ValueError('Supplement cap exhausted')
                p=subprocess.run([str(exe),'float32',str(extra/f'{ident}.bin'),'0',str(omega),'0'],input=data,
                    capture_output=True,text=True,timeout=min(30,remaining),
                    env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
                (extra/f'{ident}.log').write_text(p.stdout+'\n'+p.stderr);p.check_returncode()
                value=json.loads(p.stdout)
                if value['team']!=4 or [c['iteration'] for c in value['checkpoints']]!=list(range(26)):
                    raise ValueError('Wrong early trajectory/team')
                samples=np.fromfile(extra/f'{ident}.bin',dtype=np.float64).reshape(26,value['checkpoints'][0]['samples'],4)
                np.savez_compressed(extra/f'{ident}.npz',samples=samples,iterations=list(range(26)))
                (extra/f'{ident}.bin').unlink();row.update(status='completed',result=value)
            except (ValueError,subprocess.SubprocessError) as e:row.update(status='failed',error=str(e))
            rows.append(row);write(extra/'results.json',dict(rows=rows))
    write(extra/'summary.json',transient_summary(folder))
    original=json.loads((folder/'summary.json').read_text())['decision']
    candidate=original['factor']
    selected=[s for s in transient_summary(folder) if s['request']['omega']==candidate]
    allowed=len(selected)==2 and all(s['passed'] for s in selected)
    frozen=dict(stage='S6',public_default_method=f'{study.METHOD}-omega-1.78',public_default_factor=1.78,
        policy_calibration_candidate=f'{study.METHOD}-omega-{candidate if allowed else 1.78:.2f}',
        policy_calibration_factor=candidate if allowed else 1.78,selection=original,
        early_transient_veto_passed=allowed,parent_source_sha256=study.BASE_SHA,
        measured_source_sha256=protocol['source_sha256'],omega_storage='float argument, converted to workspace Real in both precisions',
        applicability='Method candidate for S7, not a public online accuracy policy. Only the three measured uniform-2m cases have this evidence. Stretched grids and larger urban cases require qualification.',
        setup='Same SOR/operator setup and memory ownership; no preconditioner, cross-condition iterate, or additional persistent workspace.',
        calibration='Method, compiler arithmetic, condition mask or boundary changes require renewed reference compatibility and S7 calibration. All S6 cases/directions are now method-development data, not unseen S7 validation data.')
    write(folder/'method-decision.json',frozen)


def verify(folder, *, manifest=True):
    if manifest:study.audit(folder)
    summary=study.analyze(folder)
    if not summary['completed']:raise ValueError('Incomplete main study')
    rows=json.loads((folder/'results.json').read_text())['rows']
    expected_purposes={'screen':8,'reference_triple':3,'confirmation':18,'precision':6,'budget':8}
    for purpose,count in expected_purposes.items():
        if sum(r['request']['purpose']==purpose for r in rows)!=count:raise ValueError('Wrong worker matrix')
    default_parity=[]
    for row in rows:
        req=row['request']; result=row['result']; checkpoints=result['checkpoints']
        with np.load(folder/f"{req['id']}.npz") as v:
            if v['samples'].shape!=(len(checkpoints),checkpoints[0]['samples'],4):raise ValueError('Truncated sample evidence')
            if v['iterations'].tolist()!=[c['iteration'] for c in checkpoints]:raise ValueError('Sample/iterate mismatch')
            if req['purpose']=='precision' and req['omega']==1.78 and not req['case'].endswith('_225'):
                parent=next(r for r in json.loads((folder/'parent-references.json').read_text())
                            if r['request']['case']==req['case'] and r['request']['iterations']==2000)
                with np.load(folder/f"{parent['request']['id']}.npz") as p:
                    if p['samples'].tobytes()!=v['samples'].tobytes():raise ValueError('Default trajectory changed')
                default_parity.append(req['case'])
        if result['team']!=4 or result['workspace_bytes']<=0:raise ValueError('Wrong native execution')
        if not req['budget'] and checkpoints[-1]['iteration']!=req['iterations']:raise ValueError('Wrong fixed work')
        if req['budget'] and checkpoints[-1]['elapsed_seconds']<req['budget']:raise ValueError('Budget worker ended early')
    if len(default_parity)!=2:raise ValueError('Missing default parity controls')
    early=transient_summary(folder)
    if early!=json.loads((folder/'transients/summary.json').read_text()):raise ValueError('Transient replay differs')
    plan=json.loads((folder/'transients/protocol.json').read_text())
    if len(early)!=8 or plan['main_protocol_sha256']!=digest(folder/'protocol.json'):
        raise ValueError('Changed supplement identity')
    frozen=json.loads((folder/'method-decision.json').read_text())
    candidate=summary['decision']['factor'];selected=[s for s in early if s['request']['omega']==candidate]
    passed=len(selected)==2 and all(s['passed'] for s in selected)
    if frozen['selection']!=summary['decision'] or frozen['early_transient_veto_passed']!=passed:
        raise ValueError('Method decision differs')
    if frozen['policy_calibration_factor']!=(candidate if passed else 1.78):raise ValueError('Transient veto ignored')
    if (frozen['public_default_factor']!=1.78 or frozen['parent_source_sha256']!=study.BASE_SHA
        or frozen['measured_source_sha256']!=json.loads((folder/'protocol.json').read_text())['source_sha256']
        or frozen['policy_calibration_candidate']!=f"{study.METHOD}-omega-{frozen['policy_calibration_factor']:.2f}"):
        raise ValueError('Changed method identity')
    if plan['executable_sha256']!=json.loads((folder/'execution.json').read_text())['executable_sha256']:
        raise ValueError('Transient executable changed')
    # Confirm cases and internal kernels come from the declared S5 source.
    with tarfile.open(folder/'parent-sources.tar.gz') as a:
        import types
        helper=types.ModuleType('frozen_helper');helper.__file__=str(folder/'run_solver_numerics.py')
        exec(compile(a.extractfile('tools/run_solver_numerics.py').read(),'frozen S5 helper','exec'),helper.__dict__)
        cases=helper.affordable_cases()
        kernels={m.name:hashlib.sha256(a.extractfile(m).read()).hexdigest() for m in a
                 if m.isfile() and (m.name.startswith('src/qes_core/solver/') or m.name.endswith('/StreetCanyon.cpp') or m.name.endswith('/StreetCanyonModified.cpp'))}
    for case in cases:
        if case!=json.loads((folder/f"cases/{case['name']}.json").read_text()):raise ValueError('Reference geometry changed')
    held=json.loads((folder/'cases/passages_2m_225.json').read_text());held['name']='passages_2m'
    if held!=cases[1]:raise ValueError('Held-out morphology changed')
    if not kernels:raise ValueError('Missing kernel identity')
    budgets=[]
    for row in rows:
        if row['request']['purpose']!='budget':continue
        req=row['request'];a=summary['assessments'][req['id']];last=row['result']['checkpoints'][-1]
        budgets.append(dict(case=req['case'],omega=req['omega'],budget=req['budget'],iterations=last['iteration'],
            seconds=row['result']['total_seconds'],target_reached=a['qualified'],
            overshoot_seconds=row['result']['total_seconds']-req['budget']))
    return dict(stage='S6',main_workers=43,early_workers=8,native_tests=47,
        default_full_history_exact=default_parity,method=frozen['policy_calibration_candidate'],
        kernel_members=kernels,early_transients=early,budgets=budgets,
        decision=summary['decision'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path);p.add_argument('--publish',type=Path);p.add_argument('--audit',type=Path)
    args=p.parse_args()
    if args.audit:
        value=verify(args.audit.resolve());print(json.dumps(value,indent=2));return
    if args.study is None or args.publish is None:p.error('--study and --publish, or --audit, required')
    folder=args.study.resolve();supplement(folder)
    write(folder/'verification.json',verify(folder,manifest=False))
    study.publish(folder,args.publish.resolve())
    print(json.dumps(verify(args.publish.resolve()),indent=2))

if __name__=='__main__':main()
