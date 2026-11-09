import json
from pathlib import Path

import numpy as np
import pytest

from surrey_background import observations
from surrey_transition import blocks,bounds,checkpoint_change,compare_runs,inlet,layers,sample_scalar,solid_union

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture
def protocol():
    return json.loads((ROOT/'validation/specifications/surrey_transition_v1.json').read_text())


def descriptor(protocol,name):
    return next(d for d in protocol['matrix'] if d['name']==name)


def test_frozen_matrix_has_exact_regular_arrays_without_a_cluster_hole(protocol):
    assert len(protocol['matrix'])==len({d['name'] for d in protocol['matrix']})==10
    for name,count in (('empty-coarse',0),('street-coarse',64),('block-coarse',80),('street-wide',128),('street-long',80)):
        rows=blocks(descriptor(protocol,name),protocol)
        assert len(rows)==count
        if rows:
            assert {r['height'] for r in rows}=={.07}
            assert any(r['xmin']==.56 for r in rows)
            assert min(r['xmin'] for r in rows)==0


def test_both_phases_and_roofs_are_commensurate_with_both_grids(protocol):
    for name in ('street-coarse','street-fine','block-coarse','block-fine'):
        d=descriptor(protocol,name);b=bounds(d,protocol);h=d['spacing_m']
        for r in blocks(d,protocol):
            values=[(r['xmin']-b[0])/h,(r['xmax']-b[0])/h,
                (r['ymin']-b[1])/h,(r['ymax']-b[1])/h,r['height']/h]
            np.testing.assert_allclose(values,np.rint(values),rtol=0,atol=1e-10)
        assert .07/h in (4,8)


def test_street_and_block_phase_have_same_spacing_and_explicit_edge_clearance(protocol):
    for name in ('street-coarse','block-coarse'):
        d=descriptor(protocol,name);b=bounds(d,protocol);rows=blocks(d,protocol)
        ymin=sorted({r['ymin'] for r in rows});xmin=sorted({r['xmin'] for r in rows})
        np.testing.assert_allclose(np.diff(ymin),.21,rtol=0,atol=1e-12)
        np.testing.assert_allclose(np.diff(xmin),.14,rtol=0,atol=1e-12)
        assert min(ymin)-b[1]>=.07-1e-12
        assert b[4]-max(r['ymax'] for r in rows)>=.07-1e-12
        covered=any(r['ymin']<0<r['ymax'] for r in rows)
        assert covered==(name=='block-coarse')


def test_upstream_profile_does_not_read_downstream_means_or_any_variances(protocol):
    bg=json.loads((ROOT/protocol['background_protocol']).read_text());rows=observations(bg,ROOT/bg['source'])
    before=inlet(rows,bg).to_dict()
    for row in rows:
        row['k']=999;row['uu']=999
        if row['station']!=-10:row.update(U=999,V=999)
    assert inlet(rows,bg).to_dict()==before


def test_independent_rectangular_union_has_known_cells_and_keeps_above_roof_fluid():
    mask=solid_union(np.array([.025,.075,.125]),np.array([-.025,.025,.075]),np.array([.025,.075,.125]),
        [dict(xmin=0,xmax=.1,ymin=-.05,ymax=.05,height=.1)])
    assert mask.sum()==8
    assert mask[:2,:2,:2].all() and not mask[2].any() and not mask[:,:,2].any()


def test_scalar_sampling_uses_positive_weight_spatial_contributors():
    field=np.full((3,3,3),np.nan);field[1,1,0]=3;field[1,1,1]=6
    details=dict(indices=np.array([[[0,1,1],[1,1,1],[-1,-1,-1]]]),weights=np.array([[.25,.75,0]]))
    np.testing.assert_array_equal(sample_scalar(field,details),[5.25])


def test_tunnel_height_control_has_a_different_tail_but_same_lower_layers(protocol):
    a=layers(descriptor(protocol,'street-coarse'),protocol)
    b=layers(descriptor(protocol,'street-tunnel-height'),protocol)
    np.testing.assert_array_equal(a[:49],b[:49])
    assert a[-1]==16 and b[-1]==1.5
    assert not descriptor(protocol,'street-tunnel-height')['turbulence']


def test_checkpoint_stability_uses_vectors_and_does_not_skip_invalid_receptors():
    def receptor(v,valid=True):return dict(receptor=0,sample=dict(valid=valid,velocity=v))
    history=dict(checkpoint_history=[dict(receptors=[receptor([1,0,0])]),dict(receptors=[receptor([1,.002,0])])])
    assert checkpoint_change(history,2)==.001
    history['checkpoint_history'][-1]['receptors'][0]['sample']['valid']=False
    assert checkpoint_change(history,2) is None


def test_comparison_joins_ids_and_marks_missing_physics_incomplete():
    def row(id_,u):return dict(id=id_,U=u,V=0,W=0,k=None,uu=None,vv=None,ww=None,f_w=None,velocity_valid=True,stress_valid=False)
    a=dict(predictions=[row('a',1),row('b',2)],guards=dict(ok=True))
    b=dict(predictions=[row('b',4),row('a',2)],guards=dict(ok=True))
    result=compare_runs(a,b)
    assert result['U']['rmse']==pytest.approx(np.sqrt(2.5))
    assert result['U']['count']==2 and not result['k']['complete']
    b['predictions'].pop()
    with pytest.raises(ValueError,match='identity changed'):compare_runs(a,b)


def test_increment_targets_use_only_exact_shared_heights_and_keep_invalid_points(protocol):
    from analyse_surrey_transition import shared_increments
    bg=json.loads((ROOT/protocol['background_protocol']).read_text());rows=observations(bg,ROOT/bg['source'])
    predicted=[dict(r,velocity_valid=True,computed=True,stress_valid=True,internal_k=r['k']) for r in rows]
    target,values=shared_increments(rows,predicted[::-1])
    assert len(target)==len(values)==70
    assert sorted({r['z_m'] for r in target})==[.09,.12,.18,.24,.42,.7,.75]
    assert all(v['k']==t['k'] for t,v in zip(target,values,strict=True))
    row=next(r for r in predicted if r['station']==1 and r['z_m']==.09)
    row['stress_valid']=False
    _,values=shared_increments(rows,predicted)
    assert len(values)==70 and sum(not r['stress_valid'] for r in values)==1
