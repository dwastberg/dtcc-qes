import json
from pathlib import Path

import numpy as np
import pytest

from surrey_background import turbulence_settings, observations, published_log, score, scores_for_rows, vertical_faces


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def protocol():
    return json.loads((ROOT/'validation/specifications/surrey_background_v1.json').read_text())


@pytest.fixture
def rows(protocol):
    return observations(protocol, ROOT/protocol['source'])


def test_reference_inventory_and_origins_are_not_inferred_from_urban_filename(rows):
    assert len(rows)==101 and len({r['id'] for r in rows})==101
    assert sum(r['group']=='suburban' for r in rows)==11
    assert sum(r['group']=='urban_developing' for r in rows)==45
    assert sum(r['group']=='urban_developed' for r in rows)==45
    assert rows[0]['x_hat_m']==pytest.approx(-.699997)
    assert rows[0]['x_cluster_m']==pytest.approx(-1.434997)
    assert rows[0]['z_m']==.04


def test_reference_normalization_uses_each_recorded_speed_and_physical_trace(rows):
    row=next(r for r in rows if r['station']==-10 and r['z_m']==.12)
    assert row['U']==pytest.approx(1.1929/1.9994)
    assert row['k']==pytest.approx(.5*(.053273+.027908+.0193)/1.9994**2)
    assert row['f_u']+row['f_v']+row['f_w']==pytest.approx(1)
    assert row['U']!=1.1929/2


def test_changed_source_is_rejected_before_scoring(protocol,tmp_path):
    p=tmp_path/'changed.csv.gz';p.write_bytes(b'changed')
    with pytest.raises(ValueError,match='identity changed'):
        observations(protocol,p)


def test_published_displacement_is_retained_and_invalid_heights_are_rejected(protocol):
    assert published_log(.24,'urban',protocol)==pytest.approx(.086/.4*np.log((.24-.049)/.0052))
    with pytest.raises(ValueError,match='below displacement'):
        published_log(.04,'urban',protocol)


def test_vertical_grids_preserve_experimental_scale_and_extend_only_above_one_metre(protocol):
    for dz in protocol['vertical_spacings_m']:
        faces=vertical_faces(dz,protocol)
        n=round(1/dz)
        np.testing.assert_allclose(np.diff(faces[:n+1]),dz,rtol=0,atol=1e-15)
        assert faces[n]==1 and faces[-1]==16
        assert np.all(np.diff(faces)>0)
        assert faces[-4]>.52


def predictions(rows):
    return [dict(r,velocity_valid=True,stress_valid=True,computed=True,internal_k=r['k']*2) for r in rows]


def test_frozen_solver_and_turbulence_settings_are_accepted_before_launch(protocol):
    from dtcc_qes import wind
    assert wind.Solver(**protocol['solver']).raise_on_failure
    from surrey_background import turbulence_settings
    assert turbulence_settings(protocol['turbulence']) == wind.Turbulence()


def test_predictions_align_on_ids_and_internal_energy_is_not_physical_k(rows):
    p=predictions(rows)[::-1]
    result=scores_for_rows(rows,p)
    assert result['k']['count']==101 and result['k']['rmse']==0
    assert result['internal_k_diagnostic']['rmse']>0


def test_invalid_covariance_keeps_population_and_raw_diagnostic_separate(rows):
    p=predictions(rows);p[0]['stress_valid']=False
    result=scores_for_rows(rows,p)
    assert not result['k']['complete'] and result['k']['missing_or_invalid']==1
    assert result['k']['count']==101 and 'rmse' not in result['k']
    assert result['k_raw_diagnostic']['complete'] and result['k_raw_diagnostic']['rmse']==0


def test_missing_duplicate_and_unknown_predictions_cannot_improve_coverage(rows):
    p=predictions(rows)
    assert scores_for_rows(rows,p[:-1])['U']['missing_or_invalid']==1
    with pytest.raises(ValueError,match='Duplicate or unknown'):
        scores_for_rows(rows,p+[p[0]])
    p[0]['id']='foreign'
    with pytest.raises(ValueError,match='Duplicate or unknown'):
        scores_for_rows(rows,p)


def test_score_reports_known_error_on_complete_population():
    result=score([2,4],[1,2],[True,True])
    assert result['rmse']==pytest.approx(np.sqrt(2.5))
    assert result['bias']==1.5 and result['ratio_of_sums']==2
    incomplete=score([2,np.nan],[1,2],[True,True])
    assert not incomplete['complete'] and incomplete['valid']==1
    assert 'rmse' not in incomplete


def test_benchmark_rejects_research_covariance_settings():
    with pytest.raises(ValueError, match='production legacy'):
        turbulence_settings(dict(mixing_length='height', covariance_model='bounded_consistent_v1'))
