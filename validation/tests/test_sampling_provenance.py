import json
from copy import deepcopy

import numpy as np
import pytest
import shapely

from aij import compare,runner,sampling
from aij.sampling_geometry import summarize


def probes():
    return dict(ids=[1,2,3],xyz=[[0,0,2],[2,0,2],[4,0,2]],sampled=[[0,0,2],[2,0,2],[4,0,2]],
        method=['linear']*3,k=[4.,1.,1.])


def test_changed_height_cannot_enter_fixed_height_scores_even_when_rmse_improves():
    a=probes();b=deepcopy(a);b['k']=[1.,2.,1.];b['sampled'][0]=[0,0,1];b['method'][0]='nearest_fluid'
    report=compare.paired_sampling_scores(a,b,np.ones(3))
    assert report['common']['squared_error_reduction']==8
    assert report['changed_operator']['squared_error_reduction']==9
    assert report['same_operator_at_requested_height']['squared_error_reduction']==-1
    assert report['same_operator_at_requested_height']['ids'].tolist()==[2,3]
    assert report['candidate_provenance']['height_change'][0]==-1


def test_missing_candidate_fails_complete_score_and_preserves_parent_target_by_id():
    a=probes();b=deepcopy(a);b['k'][1]=None
    # Candidate order is unrelated to parent order.
    for key in ('ids','xyz','sampled','method','k'):b[key]=b[key][::-1]
    r=compare.paired_sampling_scores(a,b,np.ones(3))
    assert r['parent_count']==3 and r['common_count']==2
    assert not r['no_coverage_loss'] and r['candidate_complete'] is None
    assert r['lost_ids'].tolist()==[2]
    b['ids']=[1,1,3]
    with pytest.raises(ValueError,match='Duplicate'):compare.paired_sampling_scores(a,b,np.ones(3))


def test_legacy_reader_retains_unknown_support_without_changing_record_or_values(tmp_path):
    original=dict(schema='aij-run-v1',key='old',probes=probes())
    (tmp_path/'old.json').write_text(json.dumps(original))
    read=runner.load(tmp_path,'old')
    assert read['schema']=='aij-run-v1' and 'sampling_provenance' not in original['probes']
    assert read['probes']['sampling_provenance']['requested_support'] is None
    assert read['probes']['sampling_provenance']['sampled_support'] is None
    assert read['probes']['k']==original['probes']['k']
    with pytest.raises(ValueError,match='record schema'):runner.read_record({**original,'schema':'aij-run-v999'})


def test_unknown_historical_coordinates_are_excluded_from_unchanged_operator_cohort():
    a=probes();del a['sampled'];del a['method']
    r=compare.paired_sampling_scores(a,probes(),np.ones(3))
    assert r['same_operator_at_requested_height']['count']==0
    assert r['common_count']==3
    assert r['relocated_or_fallback']['count']==0
    assert sampling.provenance(a)['requested_support'] is None


def test_geometry_reports_voxel_displacement_roof_and_bounded_passage():
    solid=np.zeros((4,8,10),bool);solid[:3,1:3,2:4]=True;solid[:3,1:3,7:9]=True
    o=dict(axes=[np.arange(10)+.5,np.arange(8)+.5,np.array([.5,2,4,8])],solid=solid,
        origin=[0,0,0],z_faces=[0,1,3,5,11])
    buildings=[('a',shapely.box(3,2,5,4),4),('b',shapely.box(7,2,9,4),4)]
    r=summarize(o,buildings,[[5.5,1.5,2]])
    np.testing.assert_array_equal(r['buildings'][0]['voxel_bounds'],[2,1,4,3])
    np.testing.assert_array_equal(r['buildings'][0]['edge_displacement'],[-1,-1,-1,-1])
    assert r['buildings'][0]['represented_roof_heights'].tolist()==[5.]
    assert r['points'][0]['passage_x']['width']==3
    assert not r['points'][0]['passage_y']['bounded']
    buildings.append(('overlap',shapely.box(4,2,6,4),2))
    assert summarize(o,buildings,[])['buildings'][0]['status']=='unavailable'
