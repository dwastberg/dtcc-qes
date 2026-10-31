"""The S8a decision must follow measured savings and strict numerical parity."""
import copy
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from benchmark_prepared_wind import comparable, worthwhile
from audit_prepared_wind import audit, summarize
from profile_prepared_wind import instrument


def test_parity_excludes_checkpoint_clocks_but_keeps_numerics_and_decisions():
    before=dict(fields={'velocity':'a'},control=dict(accepted=True,checkpoint_history=[dict(elapsed_seconds=.2,iteration=25,error=.01)]))
    after=copy.deepcopy(before);after['control']['checkpoint_history'][0]['elapsed_seconds']=.3
    assert comparable(before)==comparable(after)
    after['control']['checkpoint_history'][0]['error']=.02
    assert comparable(before)!=comparable(after)
    after=copy.deepcopy(before);after['control']['accepted']=False
    assert comparable(before)!=comparable(after)


def test_decision_requires_both_modes_parity_and_no_four_direction_regression():
    rows={f'{m}-{n}':dict(parity=True,saving_fraction=.1,saving_seconds=.01) for m in ['legacy','adaptive'] for n in [4,8]}
    assert worthwhile(rows)
    rows['adaptive-8']['saving_fraction']=.099
    assert not worthwhile(rows)
    rows['adaptive-8']['saving_seconds']=.1
    assert worthwhile(rows)
    rows['legacy-4']['saving_fraction']=-.051
    assert not worthwhile(rows)
    rows['legacy-4']['saving_fraction']=0
    rows['legacy-8']['parity']=False
    assert not worthwhile(rows)


def test_isolated_profile_preserves_all_solver_arithmetic(tmp_path):
    with tarfile.open(ROOT/'docs/data/solver-control-s7/release-sources.tar.gz') as a:a.extractall(tmp_path,filter='data')
    originals={p:p.read_bytes() for p in (tmp_path/'src/qes_core/solver').rglob('*') if p.is_file()}
    runner=tmp_path/'src/qes_core/dtcc/wind_runner.cpp';before=runner.read_text().splitlines()
    instrument(tmp_path)
    assert all(p.read_bytes()==value for p,value in originals.items())
    after=iter(runner.read_text().splitlines())
    for line in before:assert any(value.strip()==line.strip() for value in after),line


def test_portable_evidence_rederives_deferral():
    result=audit(ROOT/'docs/data/solver-control-s8a')
    assert result['passed'] and result['condition_solves']==216
    assert result['decision']=='defer_public_api'


def test_changed_output_cannot_be_hidden_by_summary(tmp_path):
    original=ROOT/'docs/data/solver-control-s8a/primary'
    for p in original.glob('*.json'):(tmp_path/p.name).write_bytes(p.read_bytes())
    p=tmp_path/'legacy-4-0-prototype.json';row=json.loads(p.read_text())
    row['records'][0]['fields']['velocity']['sha256']='changed'
    p.write_text(json.dumps(row))
    with pytest.raises(ValueError,match='parity'):summarize(tmp_path)
