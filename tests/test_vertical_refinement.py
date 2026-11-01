"""Checks for systematic subdivision, native alignment and honest scope gates."""

from fixtures.support import load_tool
import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from fixtures.joint_grid_verification import manufactured

_tools=Path(__file__).parents[1]/'tools'
study=load_tool('vertical_refinement', _tools/'run_vertical_refinement.py')


from fixtures.vertical_refinement import documents

def test_three_levels_are_uniform_subdivisions_of_actual_generator_and_fit_resources():
    configs=study.plans()
    base=np.asarray(configs['base']['layers_input'])
    for q in (2,4):
        fine=configs[f'split-{q}']
        assert fine['layers']==92*q
        np.testing.assert_array_equal(fine['layers_input'],np.repeat(base/q,q))
        assert fine['parent_native_face_max_error_m']<1e-4
        assert fine['cell_count']==9420800*q
        assert max(.5/np.asarray(fine['native_thicknesses']))<=8
        assert all(p['support_at_least_third'] for p in fine['sampling'].values())
    assert configs['split-4']['cell_count']==37683200>20000000


def test_alignment_changes_only_lower_band_and_aligns_native_centre():
    configs=study.plans();base=configs['base'];aligned=configs['aligned-1.75']
    np.testing.assert_array_equal(aligned['expected_faces'][8:],base['expected_faces'][8:])
    np.testing.assert_array_equal(aligned['native_thicknesses'][8:],base['native_thicknesses'][8:])
    assert aligned['sampling']['1.75']['centre_indices']==[4,4]
    assert aligned['sampling']['1.75']['bias_K']==pytest.approx(0,abs=1e-15)
    assert aligned['metadata']['roof_representation']==base['metadata']['roof_representation']
    native=np.asarray(aligned['native_thicknesses'])
    assert max(native[1:]/native[:-1])<=1.15*(1+1e-6)


def test_profile_bias_is_interpolation_only_and_diminishes_on_refinement():
    configs=study.plans()
    for h in ('1.5','1.75'):
        assert abs(configs['split-4']['sampling'][h]['bias_K'])<abs(configs['split-2']['sampling'][h]['bias_K'])
    assert configs['base']['sampling']['1.5']['bias_K']==pytest.approx(0,abs=1e-15)
    assert configs['split-2']['sampling']['1.5']['bias_K']<0
    assert 'not a correction' in configs['base']['sampling']['1.5']['interpretation']


def test_complete_pass_does_not_qualify_comfort_and_needs_selected_serial_control():
    docs,refs,configs=documents();s=study.summarize(docs,refs,configs)
    assert s['complete'] and s['sensitivity_budget_pass'] and s['alignment_budget_pass']
    assert not s['comfort_qualified'] and not s['preset_selected']
    docs['serial']['runs'].clear();s=study.summarize(docs,refs,configs)
    assert not s['complete'] and not s['sensitivity_budget_pass'] and not s['control_cpu_agrees']


def test_predeclared_worst_error_points_cannot_be_hidden_by_percentile():
    docs,refs,configs=documents()
    index=list(study.POINTS).index(15)+len(study.POINTS)*list(study.POINTS).index(47)
    for c in docs['openmp']['runs'][0]['checkpoints']:
        c['planes'][0]['velocity'][index]=[4,0,0]
    s=study.summarize(docs,refs,configs)
    row=next(r for r in s['comparisons'] if r['comparison']=='base_to_2' and r['height']==1.5 and r['region']=='all')
    assert row['within_budget'] and not row['combined_within_budget']
    assert not s['sensitivity_budget_pass']
    away=next(r for r in s['comparisons'] if r['comparison']=='base_to_2' and r['height']==1.5 and r['region']=='away4m')
    assert len(away['mandatory_checks'])==2
    assert [15,47] in [p['point'] for p in away['mandatory_checks']]
    assert not away['combined_within_budget']


def test_failed_refined_solve_withholds_all_dependent_comparisons():
    docs,refs,configs=documents()
    docs['openmp']['runs'][1]['checkpoints'][0]['max_divergence']=1
    s=study.summarize(docs,refs,configs)
    assert not s['sensitivity_budget_pass']
    affected=[r for r in s['comparisons'] if r['comparison'] in ('2_to_4','base_to_4','alignment_to_4')]
    assert all(not r['matched_accuracy'] and 'p95_abs_delta_K' not in r for r in affected)


def test_five_locations_have_honest_region_membership():
    assert len(study.LOCATIONS)==5
    assert [p for p in study.LOCATIONS if study.point_distance(p)>=4]==[[15,47],[15,29]]
