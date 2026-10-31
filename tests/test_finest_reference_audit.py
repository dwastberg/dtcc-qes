"""Validate native triple identity and support independently of acceptance."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import run_finest_reference as study
from audit_finest_reference import stopped_summary
sys.path.pop(0)


@pytest.fixture
def native():
    manifest=study.prior.read(study.PARENT/'manifest.json')
    old=study.prior.read(study.PARENT/'raw.json.gz')
    run=copy.deepcopy(next(r for r in old['openmp']['runs'] if r['task']['family']=='split-4'))
    for c,n in zip(run['checkpoints'],study.SWEEPS):c['iterations']=n
    m=dict(task=run['task'],configurations=manifest['configurations'])
    return run,m


def test_schema_validation_does_not_mislabel_failed_early_residual(native):
    run,m=native;study.validate(run,m)
    assert not study.prior.gate(run)['accepted']


@pytest.mark.parametrize('field',['threads','precision','disabled_mask','resolution','start'])
def test_native_scope_changes_rejected(native,field):
    run,m=native;run[field]={'threads':1,'precision':'float32','disabled_mask':1,'resolution':1,'start':'warm'}[field]
    with pytest.raises(ValueError):study.validate(run,m)


def test_intermediate_occupancy_change_rejected(native):
    run,m=native;run['checkpoints'][1]['planes'][0]['flags'][0]=[0,0]
    with pytest.raises(ValueError,match='Occupancy'):study.validate(run,m)


def test_roof_change_rejected(native):
    run,m=native;run['roof_errors'][0]+=.01
    with pytest.raises(AssertionError):study.validate(run,m)


def test_frozen_input_change_rejected(tmp_path):
    manifest=study.prior.read(study.OUTPUT/'manifest.json')
    import shutil
    shutil.copytree(study.OUTPUT,tmp_path/'archive')
    root=tmp_path/'archive';(root/'input.txt').write_text('altered')
    with pytest.raises(ValueError,match='Saved stdin'):
        study.verify(root,manifest)


def test_stopped_reference_has_unknown_acceptance_and_accounts_for_wasted_work():
    first=dict(completed_checkpoint_results=0,last_observed_cpu_seconds=200,
               executed_cell_sweeps_upper_bound=1000)
    second=dict(saved_checkpoint_results=0,last_observed_cpu_seconds=100,
                executed_cell_sweeps_upper_bound=1000)
    result=stopped_summary(first,second)
    assert not result['complete'] and not result['reference_usable']
    assert result['accepted'] is None
    assert result['total_execution_attempts']==2
    assert result['observed_cpu_seconds_lower_bound']==300
    assert result['executed_cell_sweeps_range']==[0,2000]
    assert not result['comfort_qualified'] and not result['preset_selected']


def test_stopped_summary_cannot_hide_saved_checkpoint_results():
    with pytest.raises(ValueError,match='completed checkpoints'):
        stopped_summary(dict(completed_checkpoint_results=1),dict(saved_checkpoint_results=0))
