"""Release scope and evidence must not silently waive numerical/release gates."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from audit_solver_release import REQUIRED,validate_summary,verify_manifest,compare_fingerprints


def valid():
    scope=json.loads((ROOT/'docs/data/solver-control-s9/scope.json').read_text())
    checks={name:dict(passed=True) for name in REQUIRED}
    checks['parity'].update(comparisons=12,cases=429)
    checks['policy'].update(workers=24,exact_workers=24)
    checks['campaign'].update(fresh_results=True,reused=True,damaged_package_rebuilt=True)
    return dict(checks=checks,native_policy_revision=scope['policy']['native_revision']),scope


def test_scope_explicitly_defers_comfort_and_preserves_defaults():
    summary,scope=valid();validate_summary(summary,scope)
    assert 'not implemented or qualified' in scope['stages']['S8b']
    for bad in ['S8b','defaults','policy']:
        changed=copy.deepcopy(scope)
        if bad=='S8b':changed['stages']['S8b']='complete'
        elif bad=='defaults':changed['defaults']['solver_control']='adaptive'
        else:changed['policy']['native_revision']='invented'
        with pytest.raises(ValueError):validate_summary(summary,changed)


@pytest.mark.parametrize('gate',sorted(REQUIRED))
def test_each_release_gate_is_required(gate):
    summary,scope=valid();summary['checks'][gate]['passed']=False
    with pytest.raises(ValueError,match='gate failed'):validate_summary(summary,scope)
    del summary['checks'][gate]
    with pytest.raises(ValueError,match='Incomplete'):validate_summary(summary,scope)


def test_evidence_tampering_and_bytecode_are_rejected(tmp_path):
    p=tmp_path/'result.json';p.write_text('{}')
    manifest=dict(files={'result.json':hashlib.sha256(p.read_bytes()).hexdigest()})
    verify_manifest(tmp_path,manifest)
    p.write_text('{"passed":true}')
    with pytest.raises(ValueError,match='Changed release evidence'):verify_manifest(tmp_path,manifest)
    with pytest.raises(ValueError,match='bytecode'):verify_manifest(tmp_path,dict(files={'__pycache__/a.pyc':'unused'}))


def test_default_fingerprints_only_exclude_import_location():
    arrays=dict(velocity=dict(dtype='<f4',shape=[2,3],sha256='a'),_module=dict(sha256='old location'))
    other=copy.deepcopy(arrays);other['_module']['sha256']='new location'
    compare_fingerprints(arrays,other)
    other['velocity']['sha256']='rounded values differ'
    with pytest.raises(ValueError,match='fingerprint'):compare_fingerprints(arrays,other)


def test_s8_packaging_repair_preserves_every_original_measurement():
    root=ROOT/'docs/data/solver-control-s8a'
    original=json.loads((root/'manifest-s8a-original.json').read_text());current=json.loads((root/'manifest.json').read_text())
    revision=json.loads((root/'packaging-revision.json').read_text())
    assert hashlib.sha256((root/'manifest-s8a-original.json').read_bytes()).hexdigest()==revision['parent_manifest_sha256']
    removed=set(original['files'])-set(current['files'])
    assert removed==set(revision['excluded_generated_cache_entries'])
    assert all('__pycache__' in Path(name).parts or name.endswith('.pyc') for name in removed)
    assert all(current['files'][k]==v for k,v in original['files'].items() if k not in removed)
    assert original['sources']==current['sources']
