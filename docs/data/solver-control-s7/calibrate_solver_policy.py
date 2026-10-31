"""One bounded draft-2 replay revision, preserving the failed fresh-tail draft."""
import argparse
import json
from pathlib import Path
import shutil
import time
from run_solver_numerics import digest,write
from run_solver_policy_study import oracle,qualify
from solver_policy_replay import replay,POLICY,METHOD,TARGET


def calibrate(out):
    protocol=json.loads((out/'draft2-protocol.json').read_text());rows=json.loads((out/'fixed-results.json').read_text())['rows']
    if (out/'policy-freeze.json').exists():raise ValueError('A policy is already frozen')
    if len(rows)!=12 or any(r['request']['case'] not in protocol['calibration'] for r in rows):raise ValueError('Held-out data contamination')
    for name in ['calibrate_solver_policy.py','solver_policy_replay.py']:
        shutil.copyfile(Path(__file__).parent/name,out/name)
    trials=[]
    for params in protocol['calibration_parameters']:
        records=[]
        for row in rows:
            if row['request']['purpose']!='calibration':continue
            case=json.loads((out/f"cases/{row['request']['case']}.json").read_text())
            ref=next(r for r in rows if r['request']['case']==case['name'] and r['request']['purpose']=='reference' and r['request']['iterations']==2000)
            truth=oracle(row,out,ref);estimated=replay(row['result']['checkpoints'],params,case['speed'])
            false=[e['iteration'] for e,t in zip(estimated,truth) if e['accepted'] and not t['passed']]
            hits=[e['iteration'] for e in estimated if e['accepted']]
            records.append(dict(case=case['name'],false_acceptances=false,first_accept=hits[0] if hits else None))
        eligible=all(not r['false_acceptances'] and r['first_accept'] is not None for r in records)
        trials.append(dict(parameters=params,records=records,eligible=eligible,
                           cost=sum(r['first_accept'] for r in records)/len(records) if eligible else None))
    write(out/'draft2-trials.json',trials)
    feasible=[r for r in trials if r['eligible']]
    if not feasible:raise ValueError('Second finite draft failed; adaptive remains unreleased')
    selected=min(feasible,key=lambda r:(r['cost'],-r['parameters']['safety_factor'],-r['parameters']['minimum_iterations'],r['parameters']['maximum_ratio']))
    write(out/'policy-freeze.json',dict(policy=POLICY,method=METHOD,parameters=selected['parameters'],selection=selected,
        protocol_sha256=digest(out/'draft2-protocol.json'),calibration_results_sha256=digest(out/'fixed-results.json'),
        predictor_sha256=digest(out/'solver_policy_replay.py'),validation_started=False,scope=protocol['scope'],target=TARGET,
        freeze_timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    print(json.dumps(selected,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();calibrate(a.folder)
