"""Finite S6 SOR study on the frozen S5 implementation; no public policy change.

Run: .venv/bin/python tools/run_solver_method_study.py --output build/solver-control-s6
Replay portable evidence: .venv/bin/python docs/data/solver-control-s6/run_solver_method_study.py --audit docs/data/solver-control-s6
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import numpy as np
from run_solver_numerics import affordable_cases, compare_samples, digest, qualify, stdin_for, write

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'f138616b7796f20b3f66e04c2c52f01f6f27c5fcd4122bccc373caf82156adeb'
METHOD = 's5c-rb-sor-float-omega-v1'
OMEGAS = [1.78, 1.85, 1.90, 1.95]
GATES = dict(vector_maximum=1e-3, vector_p95=5e-4, scaled_mass_maximum=1e-3,
             scaled_mass_rms=1e-4, relative_residual_maximum=1e-3,
             relative_residual_rms=1e-4, length_m=23.7, uref_mps=5., consecutive=3)


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT/'docs/data/solver-control-s5/sources.tar.gz'
    if digest(base) != BASE_SHA:
        raise ValueError('Frozen S5 implementation changed')
    tree = out/'tree'; tree.mkdir()
    with tarfile.open(base) as a:
        a.extractall(tree, filter='data')
    shutil.copyfile(ROOT/'tools/solver_numerics_probe.cpp', tree/'tools/solver_numerics_probe.cpp')
    for name in ['run_solver_method_study.py', 'run_solver_numerics.py']:
        shutil.copyfile(ROOT/'tools'/name, out/name)
    shutil.copyfile(ROOT/'tests/test_solver_method_study.py', out/'test_solver_method_study.py')
    shutil.copyfile(base, out/'parent-sources.tar.gz')
    index = {p.relative_to(tree).as_posix(): digest(p) for p in tree.rglob('*') if p.is_file()}
    write(out/'source-index.json', index)
    with tarfile.open(out/'sources.tar.gz', 'w:gz') as a:
        for name in sorted(index):
            a.add(tree/name, arcname=name, recursive=False)
    cases = affordable_cases()
    held = json.loads(json.dumps(cases[1])); held['name'] = 'passages_2m_225'
    cases.append(held)
    for case in cases:
        write(out/f"cases/{case['name']}.json", case)
    # Copy original qualified evidence from the portable S5 archive, not a build tree.
    sys.path.insert(0, str(ROOT/'tools'))
    from publish_solver_s5 import Evidence
    source = Evidence(ROOT/'docs/data/solver-control-s5')
    results = source.json('s5c/results.json')
    original = []
    for row in results['rows']:
        if row['request']['purpose'] != 'reference_triple':
            continue
        r = json.loads(json.dumps(row)); old = r['request']['id']; new = 'parent-'+old
        r['request']['id'] = new
        (out/f'{new}.npz').write_bytes(source.read(f's5c/{old}.npz'))
        original.append(r)
    write(out/'parent-references.json', original)
    parent_checks = qualify(original, out)
    if len(parent_checks) != 2 or not all(r['accepted'] for r in parent_checks):
        raise ValueError('S5 references no longer qualify')
    protocol = dict(stage='S6', method_family=METHOD, parent_source_sha256=BASE_SHA,
        parent_manifest_sha256=digest(ROOT/'docs/data/solver-control-s5/manifest.json'),
        source_sha256=digest(out/'sources.tar.gz'), gates=GATES, omegas=OMEGAS,
        screen_cases=[c['name'] for c in cases[:2]], held_out=held['name'],
        iterations=2000, cadence=25, team=4, worker_seconds=30, study_seconds=180,
        reference=dict(precision='float64', omega=1.78, independent_zero_starts=[500,1000,2000],
                       gates='Unchanged S5 triple gates, both pairs, both heights, masks and all required receptors'),
        screen_selection='Among nondefault factors reaching the target on both screen cases, minimize geometric mean of total native first-target cost/default. Tie favors smaller omega. If none qualify, confirm 1.85 and retain default.',
        confirmation=dict(repetitions=3, paired_order='Alternate default/challenger by case and repetition',
            selection='Opt-in only if all three cases qualify, median paired challenger/default cost <=0.90 on EVERY case, at least 2/3 pairs faster on EVERY case, and all float64 controls qualify. Otherwise retain 1.78.'),
        budgets=[.05,.15], precision_controls=['float32 screen/confirmation', 'float64 both factors, all three cases'],
        target='Offline numerical comparison only: 3 consecutive noninitial checkpoints and no later failed gate. Cost is last of first three, including native preparation, RHS, all preceding checks, monitor capture and sample writes. Excludes process launch and full-volume API finalization/turbulence. No online acceptance claim.',
        hotspots='Full two-height ROI maxima cover moving/current/previous pedestrian hotspots; all fixed required receptors checked. Global interior mass maximum covers moving volume hotspots. Top-band mass/flux reported separately and never qualified by this interior scope.',
        limits='43 workers maximum (8 screen, 3 held-out reference, 18 paired confirmation, 6 precision, 8 budget). No retries or budget escalation. Unqualified held-out case forces retain-default decision.',
        precision_and_transients='Record early residual/mass growth, late-window residual/drift, and both precision tails. No inference of error from update magnitude.',
        policy='All public defaults unchanged. S7 must bind its policy to the recorded method and qualify supported grids/directions separately.')
    write(out/'protocol.json', protocol)
    return protocol


def assess(checkpoint, sample, reference, plane_points, gates=GATES):
    heights = compare_samples(sample, reference, plane_points)
    mass = checkpoint['mass']; residual = checkpoint['residual']
    scaled_max = mass['maximum']*gates['length_m']/gates['uref_mps']
    scaled_rms = mass['rms']*gates['length_m']/gates['uref_mps']
    values = [scaled_max, scaled_rms, residual['relative_maximum'], residual['relative_rms']]
    numerical = (all(math.isfinite(v) and v >= 0 for v in values)
        and scaled_max <= gates['scaled_mass_maximum'] and scaled_rms <= gates['scaled_mass_rms']
        and residual['relative_maximum'] <= gates['relative_residual_maximum']
        and residual['relative_rms'] <= gates['relative_residual_rms'])
    passed = numerical and all(h['maximum'] is not None and h['maximum'] <= gates['vector_maximum']
        and h['p95'] <= gates['vector_p95'] and h['required_valid'] and not h['validity_changes'] for h in heights)
    return dict(passed=bool(passed), heights=heights, scaled_mass_maximum=scaled_max,
                scaled_mass_rms=scaled_rms)


def evaluate(row, folder, reference_row):
    if row['status'] != 'completed':
        return dict(qualified=False, error=row.get('error', 'incomplete'))
    with np.load(folder/f"{row['request']['id']}.npz") as v:
        samples = v['samples']
    with np.load(folder/f"{reference_row['request']['id']}.npz") as v:
        reference = v['samples'][-1]
    same_initial = row['result']['initial_hashes'] == reference_row['result']['initial_hashes']
    checks = [assess(c, s, reference, row['result']['plane_points'])
              for c, s in zip(row['result']['checkpoints'], samples)]
    first = None
    for i in range(1, len(checks)-GATES['consecutive']+1):
        if all(c['passed'] for c in checks[i:]) and len(checks)-i >= GATES['consecutive']:
            first = i+GATES['consecutive']-1
            break
    cp = row['result']['checkpoints']; last = cp[-1]; initial = cp[0]
    late = max(1, len(cp)-11)
    drift = compare_samples(samples[late], samples[-1], row['result']['plane_points'])
    def growth(key, field):
        baseline = initial[key][field]
        return max(c[key][field] for c in cp[:min(11,len(cp))])/max(baseline, 1e-30)
    # Full ROI includes the error hotspot at every checkpoint; record its sample index.
    hotspot = []
    for sample in samples:
        valid = (sample[:,3] == 1) & (reference[:,3] == 1)
        delta = np.where(valid, np.linalg.norm(sample[:,:3]-reference[:,:3], axis=1)/5, -1)
        hotspot.append(int(np.argmax(delta)))
    qualified = same_initial and first is not None
    return dict(qualified=qualified, same_initial=same_initial, checks=checks,
        first_target_iteration=cp[first]['iteration'] if qualified else None,
        total_cost_seconds=cp[first]['elapsed_seconds'] if qualified else None,
        early_residual_max_growth=growth('residual','maximum'),
        early_mass_max_growth=growth('mass','maximum'),
        tail_residual_rms=[c['residual']['relative_rms'] for c in cp[late:]],
        tail_vector_drift=drift, error_hotspot_sample_indices=hotspot,
        final_top_mass_maximum=last['mass']['top_maximum'],
        final_relative_residual_rms=last['residual']['relative_rms'],
        final_maximum_change=last['maximum_change'])


def screen_choice(rows, assessments, cases):
    choices = []
    for omega in OMEGAS[1:]:
        ratios = []
        for case in cases:
            group = [r for r in rows if r['request']['purpose']=='screen' and r['request']['case']==case]
            a = next(assessments[r['request']['id']] for r in group if r['request']['omega']==1.78)
            b = next(assessments[r['request']['id']] for r in group if r['request']['omega']==omega)
            if a['qualified'] and b['qualified']:
                ratios.append(b['total_cost_seconds']/a['total_cost_seconds'])
        if len(ratios)==len(cases):
            choices.append((math.prod(ratios)**(1/len(ratios)), omega))
    return min(choices)[1] if choices else 1.85


def decision(rows, assessments, challenger, cases, references_ok):
    pairs = []
    for case in cases:
        ratios=[]
        for rep in range(3):
            group=[r for r in rows if r['request']['purpose']=='confirmation'
                   and r['request']['case']==case and r['request']['rep']==rep]
            a=[assessments[r['request']['id']] for r in group if r['request']['omega']==1.78]
            b=[assessments[r['request']['id']] for r in group if r['request']['omega']==challenger]
            ratios.append(b[0]['total_cost_seconds']/a[0]['total_cost_seconds']
                          if len(a)==len(b)==1 and a[0]['qualified'] and b[0]['qualified'] else None)
        median=float(np.median(ratios)) if all(x is not None for x in ratios) else None
        pairs.append(dict(case=case, ratios=ratios, median_ratio=median,
                          passed=median is not None and median<=.90 and sum(x<1 for x in ratios)>=2))
    controls=[r for r in rows if r['request']['purpose']=='precision']
    precision_ok=len(controls)==6 and all(assessments[r['request']['id']]['qualified'] for r in controls)
    opt_in=bool(references_ok and precision_ok and all(p['passed'] for p in pairs))
    factor=challenger if opt_in else 1.78
    return dict(outcome='scoped_internal_opt_in' if opt_in else 'retain_default', factor=factor,
                method_id=f'{METHOD}-omega-{factor:.2f}', public_default=1.78, challenger=challenger,
                pairs=pairs, references_qualified=references_ok, precision_controls_qualified=precision_ok,
                scope=cases, online_accuracy='not_assessed',
                acceleration='Deferred; CG is not selected. Symmetry/SPD of the actual stretched/ground/solid operator is not assumed or established by SOR results.',
                disposition='S7 must qualify its own policy. The large-city reference and top boundary limitations remain. Full API cost is not measured by this slab-output native study.')


def build(out):
    for name,cmd,limit in [
        ('configure',['cmake','-S',str(out/'tree'),'-B',str(out/'native'),'-DCMAKE_BUILD_TYPE=Release',
                      f'-DPython_EXECUTABLE={sys.executable}','-DDTCC_QES_BUILD_TESTS=ON','-DDTCC_QES_OPENMP=ON'],120),
        ('build',['cmake','--build',str(out/'native'),'-j8'],240),
        ('native-tests',['ctest','--test-dir',str(out/'native'),'--output-on-failure','-j1'],120)]:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=limit)
        (out/f'{name}.log').write_text(p.stdout+p.stderr);p.check_returncode()
    write(out/'execution.json',dict(executable_sha256=digest(out/'native/solver_numerics_probe'),
        cache_sha256=digest(out/'native/CMakeCache.txt'), protocol_sha256=digest(out/'protocol.json'),
        platform=platform.platform(), python=sys.version, environment={'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'}))


def run(out, protocol):
    rows=[]; started=time.monotonic()
    def worker(case, purpose, omega=1.78, precision='float32', iterations=2000, rep=0, budget=0):
        request=dict(id=f'{len(rows):02}',case=case,purpose=purpose,omega=omega,precision=precision,
                     iterations=iterations,cadence=25,direction=225 if case.endswith('_225') else 270,
                     rep=rep,budget=budget)
        row=dict(request=request)
        spec=json.loads((out/f'cases/{case}.json').read_text())
        data=stdin_for(spec,request); (out/f"{request['id']}.stdin").write_text(data)
        print(f"[{len(rows)+1}/43] {purpose} {case} omega={omega} {precision} budget={budget}",flush=True)
        try:
            remaining=protocol['study_seconds']-(time.monotonic()-started)
            if remaining<=0: raise ValueError('Finite study cap exhausted; no retry')
            p=subprocess.run([str(out/'native/solver_numerics_probe'),precision,str(out/f"{request['id']}.bin"),'0',str(omega),str(budget)],
                             input=data,capture_output=True,text=True,timeout=min(30,remaining),
                             env=os.environ|{'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
            (out/f"{request['id']}.log").write_text(p.stdout+'\n'+p.stderr);p.check_returncode()
            value=json.loads(p.stdout); n=value['checkpoints'][0]['samples']
            if value['team']!=4 or (not budget and value['checkpoints'][-1]['iteration']!=iterations):
                raise ValueError('Wrong team or work')
            samples=np.fromfile(out/f"{request['id']}.bin",dtype=np.float64).reshape(len(value['checkpoints']),n,4)
            np.savez_compressed(out/f"{request['id']}.npz",samples=samples,
                                iterations=[c['iteration'] for c in value['checkpoints']])
            (out/f"{request['id']}.bin").unlink()
            row.update(status='completed', result=value)
        except (ValueError,subprocess.SubprocessError) as exc:
            row.update(status='failed',error=str(exc))
        rows.append(row);write(out/'results.json',dict(rows=rows))
        return row
    cases=protocol['screen_cases']; held=protocol['held_out']
    for case in cases:
        for omega in OMEGAS:worker(case,'screen',omega)
    parent=json.loads((out/'parent-references.json').read_text())
    refs={c:next(r for r in parent if r['request']['case']==c and r['request']['iterations']==2000) for c in cases}
    assessments={r['request']['id']:evaluate(r,out,refs[r['request']['case']]) for r in rows}
    challenger=screen_choice(rows,assessments,cases)
    write(out/'screen-decision.json',dict(challenger=challenger,assessments=assessments))
    held_rows=[]
    for n in [500,1000,2000]:held_rows.append(worker(held,'reference_triple',precision='float64',iterations=n))
    for rep in range(3):
        for i,case in enumerate(cases+[held]):
            for omega in ([1.78,challenger] if (rep+i)%2==0 else [challenger,1.78]):
                worker(case,'confirmation',omega,rep=rep)
    for case in cases+[held]:
        for omega in [1.78,challenger]:worker(case,'precision',omega,precision='float64')
    for case in cases:
        for budget in protocol['budgets']:
            for omega in [1.78,challenger]:worker(case,'budget',omega,budget=budget)
    write(out/'run-complete.json',dict(seconds=time.monotonic()-started,workers=len(rows)))
    return analyze(out)


def analyze(out):
    protocol=json.loads((out/'protocol.json').read_text()); rows=json.loads((out/'results.json').read_text())['rows']
    parent=json.loads((out/'parent-references.json').read_text())
    checks=qualify(parent+[r for r in rows if r['request']['purpose']=='reference_triple'],out)
    refrows=parent+[r for r in rows if r['request']['purpose']=='reference_triple']
    refs={r['request']['case']:r for r in refrows if r['request']['iterations']==2000 and r['status']=='completed'}
    assessments={r['request']['id']:evaluate(r,out,refs[r['request']['case']]) if r['request']['case'] in refs
                 else dict(qualified=False,error='Missing reference') for r in rows if r['request']['purpose']!='reference_triple'}
    qualified_references={c['case']:c['accepted'] for c in checks}
    for row in rows:
        if row['request']['purpose']=='reference_triple':continue
        a=assessments[row['request']['id']]
        a['reference_qualified']=qualified_references.get(row['request']['case'],False)
        a['comparison_label']='reference_error' if a['reference_qualified'] else 'unqualified_iterate_difference'
        a['qualified']=bool(a['qualified'] and a['reference_qualified'])
    challenger=screen_choice(rows,assessments,protocol['screen_cases'])
    result=decision(rows,assessments,challenger,protocol['screen_cases']+[protocol['held_out']],
                    len(checks)==3 and all(c['accepted'] for c in checks))
    summary=dict(stage='S6',completed=len(rows)==43 and all(r['status']=='completed' for r in rows),
                 references=checks,assessments=assessments,decision=result)
    return summary


def publish(out, destination):
    destination.mkdir(parents=True,exist_ok=False)
    for p in out.rglob('*'):
        rel=p.relative_to(out)
        if not p.is_file() or rel.parts[0] in {'tree','native','__pycache__'} or '__pycache__' in rel.parts:
            continue
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    write(destination/'summary.json',analyze(destination))
    files={p.relative_to(destination).as_posix():digest(p) for p in destination.rglob('*') if p.is_file()}
    write(destination/'manifest.json',dict(stage='S6',files=files))


def audit(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if digest(folder/name)!=sha:raise ValueError('Changed evidence: '+name)
    protocol=json.loads((folder/'protocol.json').read_text())
    if digest(folder/'parent-sources.tar.gz')!=BASE_SHA or digest(folder/'sources.tar.gz')!=protocol['source_sha256']:
        raise ValueError('Changed method implementation')
    with tarfile.open(folder/'sources.tar.gz') as a:
        index=json.loads((folder/'source-index.json').read_text())
        import hashlib
        actual={m.name:hashlib.sha256(a.extractfile(m).read()).hexdigest() for m in a if m.isfile()}
        if actual!=index:raise ValueError('Source member mismatch')
    with tarfile.open(folder/'parent-sources.tar.gz') as a:
        parent={m.name:a.extractfile(m).read() for m in a if m.isfile()}
    with tarfile.open(folder/'sources.tar.gz') as a:
        candidate={m.name:a.extractfile(m).read() for m in a if m.isfile()}
    changed=[name for name in parent.keys()|candidate.keys() if parent.get(name)!=candidate.get(name)]
    if changed!=['tools/solver_numerics_probe.cpp']:
        raise ValueError('Production default changed: '+str(changed))
    replay=analyze(folder)
    if replay!=json.loads((folder/'summary.json').read_text()):raise ValueError('Decision replay differs')
    return dict(stage='S6',files=len(manifest['files']),workers=43,decision=replay['decision'],completed=replay['completed'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path);p.add_argument('--publish',type=Path);p.add_argument('--audit',type=Path)
    args=p.parse_args()
    if args.audit:
        print(json.dumps(audit(args.audit),indent=2));return
    if args.output is None:p.error('--output or --audit is required')
    out=args.output.resolve();protocol=prepare(out);build(out);summary=run(out,protocol)
    write(out/'summary.json',summary)
    if args.publish:publish(out,args.publish.resolve())
    print(json.dumps(dict(completed=summary['completed'],decision=summary['decision'],output=str(out)),indent=2))

if __name__=='__main__':main()
