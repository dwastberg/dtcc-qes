"""Rebuild and rerun the qualified S7 numerical/API matrix in one command.

.venv/bin/python tools/reproduce_solver_policy.py --output build/solver-policy-reproduction
Uses published immutable inputs and sources. Fresh destinations are required.
Unsupported arithmetic builds stay unaccepted; no reference-budget escalation.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from run_solver_numerics import digest,write
from run_solver_policy_study import fixed_worker,qualify,validation_references
from calibrate_solver_policy import calibrate
from validate_solver_policy import run,analyze

ROOT=Path(__file__).resolve().parents[1]


def reproduce(evidence,out):
    manifest=json.loads((evidence/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if digest(evidence/name)!=sha:raise ValueError('Changed published evidence: '+name)
    out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(evidence/'cases',out/'cases')
    for name in ['protocol.json','draft2-protocol.json','policy-freeze.json']:
        shutil.copyfile(evidence/name,out/('original-policy-freeze.json' if name=='policy-freeze.json' else name))
    archive=evidence/'release-sources.tar.gz';tree=out/'tree';tree.mkdir()
    with tarfile.open(archive) as a:a.extractall(tree,filter='data')
    write(out/'reproduction-input.json',dict(source_sha256=digest(archive),evidence_manifest_sha256=digest(evidence/'manifest.json'),
        worker_cap=57,worker_seconds=30,total_worker_seconds=600,reference_cap=2000,no_retries=True))
    for backend,flag in [('native','ON'),('serial','OFF')]:
        for label,cmd in [('configure',['cmake','-S',str(tree),'-B',str(out/backend),'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}','-DDTCC_QES_BUILD_TESTS=ON',f'-DDTCC_QES_OPENMP={flag}']),
                          ('build',['cmake','--build',str(out/backend),'-j8']),
                          ('tests',['ctest','--test-dir',str(out/backend),'--output-on-failure','-j1'])]:
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=240);(out/f'{backend}-{label}.log').write_text(r.stdout+r.stderr);r.check_returncode()
    # fixed_worker expects the study probe under this name. This read-only
    # alias points to the exact just-built source tree, not a cached executable.
    (out/'calibration-native').symlink_to(out/'native',target_is_directory=True)
    protocol=json.loads((out/'draft2-protocol.json').read_text());rows=[];started=time.monotonic()
    for name in protocol['calibration']:
        case=json.loads((out/f'cases/{name}.json').read_text())
        for n in [500,1000,2000]:fixed_worker(out,case,'reference',n,rows)
        fixed_worker(out,case,'calibration',2000,rows)
        if time.monotonic()-started>180:raise ValueError('Calibration shard cap exhausted')
    calibrate(out)
    frozen=json.loads((out/'policy-freeze.json').read_text());original=json.loads((out/'original-policy-freeze.json').read_text())
    if frozen['parameters']!=original['parameters']:raise ValueError('Frozen calibration selection did not reproduce')
    validation_references(out)
    checks=json.loads((out/'all-reference-qualification.json').read_text())
    if [(r['case'],r['qualified']) for r in checks]!=[(r['case'],r['qualified']) for r in json.loads((evidence/'all-reference-qualification.json').read_text())]:
        raise ValueError('Reference qualification scope did not reproduce')
    restriction=json.loads((evidence/'scope-restriction.json').read_text());restriction['reference_qualification_sha256']=digest(out/'all-reference-qualification.json')
    write(out/'scope-restriction.json',restriction)
    run(out,release=True)
    summary=analyze(out,release=True)
    # Exact returned fields/diagnostics against the original final-build run.
    expected=json.loads((evidence/'release-online-results.json').read_text())['rows']
    actual=json.loads((out/'release-online-results.json').read_text())['rows']
    exact=[]
    for a,b in zip(expected,actual):
        if a['request']!=b['request']:raise ValueError('Reproduction matrix changed')
        equal=a.get('field_hashes')==b.get('field_hashes') and a.get('diagnostics')==b.get('diagnostics')
        exact.append(equal)
    result=dict(reference_triples=len(checks),qualified_references=sum(r['qualified'] for r in checks),
                workers=len(rows)+21+len(actual),false_acceptances=summary['false_acceptances'],missed_acceptances=summary['missed_acceptances'],
                final_build_fields_exact=all(exact),exact_workers=sum(exact),online_workers=len(actual),
                output=str(out),accuracy='empirically_qualified_pedestrian_scope_only')
    write(out/'reproduction-summary.json',result);print(json.dumps(result,indent=2))
    if summary['false_acceptances'] or summary['missed_acceptances'] or not all(exact):raise ValueError('Reproduction did not meet the frozen release gates')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--evidence',type=Path,default=ROOT/'docs/data/solver-control-s7');a=p.parse_args();reproduce(a.evidence.resolve(),a.output.resolve())
