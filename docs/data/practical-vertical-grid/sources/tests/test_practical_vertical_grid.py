"""Meaningful checks of candidate error budgets and spatial support handling."""
import importlib.util
from pathlib import Path
import sys

import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
spec=importlib.util.spec_from_file_location('practical_vertical_grid',TOOLS/'run_practical_vertical_grid.py')
study=importlib.util.module_from_spec(spec)
sys.path.insert(0,str(TOOLS))
try:
    spec.loader.exec_module(study)
finally:
    sys.path.pop(0)


def test_speed_agreement_cannot_hide_vector_error():
    row=study.error_metrics([[5,0,0]],[[-5,0,0]],[0])
    assert row['p95_abs_delta_K']==0
    assert row['p95_vector_error_over_Uref']==2
    assert not row['candidate_lattice_budget_met']


def test_local_error_cannot_hide_behind_percentile():
    a=[[5,0,0]]*99+[[5.2,0,0]]
    row=study.error_metrics(a,[[5,0,0]]*100,[99])
    assert row['p95_abs_delta_K']==0
    assert not row['candidate_lattice_budget_met']


def test_invalid_required_support_fails():
    row=study.error_metrics([[5,0,0],None],[[5,0,0],[5,0,0]],[1])
    assert row['validity_changes']==1
    assert not row['critical_checks'][1]['valid']
    assert not row['candidate_lattice_budget_met']


def test_pair_peak_outside_frozen_set_is_checked():
    row=study.error_metrics([[5,0,0],[6,0,0]],[[5,0,0],[5.5,0,0]],[0])
    assert [c['index'] for c in row['critical_checks']]==[0,1]
    assert not row['critical_checks'][1]['within_budget']


def test_low_speed_uses_absolute_budget():
    assert study.numeric_check(.012,.01)['within_budget']
    assert not study.numeric_check(.02,.01)['within_budget']
    assert study.numeric_check(.012,.01)['relative_error'] is None


def test_invalid_and_empty_support_is_not_a_pass():
    assert not study.numeric_check(None,None)['within_budget']
    with pytest.raises(ValueError,match='No common'):
        study.error_metrics([None],[None],[])


def test_matrix_is_bounded_and_keeps_default_precision():
    assert [(t['family'],t['iterations']) for t in study.tasks()]==[
        ('generated',1000),('uniform',1000),('generated',2000),('uniform',2000)]
