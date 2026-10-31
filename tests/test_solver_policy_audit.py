"""Portable S7 evidence and failed-support decision replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_solver_policy import audit
from solver_policy_replay import replay

EVIDENCE=Path(__file__).resolve().parents[1]/'docs/data/solver-control-s7'


def test_portable_evidence_replays_frozen_decisions_and_errors():
    result=audit(EVIDENCE)
    assert result==json.loads((EVIDENCE/'summary.json').read_text())
    assert result['total_workers']==100 and result['false_acceptances']==0
    assert result['predictor_underestimates']==0 and len(result['serial_policy_cases_exact'])==6


def test_reproduction_preserves_its_actual_input_manifest():
    folder=EVIDENCE/'reproduction'
    inputs=json.loads((folder/'reproduction-input.json').read_text())
    assert hashlib.sha256((folder/'input-manifest.json').read_bytes()).hexdigest()==inputs['evidence_manifest_sha256']
    summary=json.loads((folder/'reproduction-summary.json').read_text())
    assert summary['workers']==57 and summary['final_build_fields_exact'] and summary['exact_workers']==24


def test_invalid_support_revokes_a_trusted_anchor():
    rows=json.loads((EVIDENCE/'fixed-results.json').read_text())['rows']
    row=next(r for r in rows if r['request']['case']=='passages_2m' and r['request']['purpose']=='calibration')
    parameters=json.loads((EVIDENCE/'policy-freeze.json').read_text())['parameters']
    original=replay(row['result']['checkpoints'],parameters,5)
    assert any(r['accepted'] and r['iteration']==225 for r in original)
    changed=deepcopy(row['result']['checkpoints'])
    for c in changed:
        if c['iteration']>=200:c['monitor']['required_valid']=False
    result=replay(changed,parameters,5)
    assert not any(r['accepted'] for r in result)
    assert all(r['prediction']['anchor_iteration'] is None for r in result if r['iteration']>=200)
