from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

pd=pytest.importorskip('pandas')
pytest.importorskip('scipy')
from audit_surrey_reference import export_table,moments,raw_table,roughness_profile_inventory,trace_statistics


def test_weighted_moments_have_known_covariance_and_trace():
    m=moments([[-1,0,0],[1,0,0]],[1,3])
    np.testing.assert_allclose(m['mean'],[.5,0,0])
    np.testing.assert_allclose(m['variance'],[.75,0,0])
    assert m['k']==.375


def test_time_weight_sensitivity_is_labelled_and_not_relabelled_as_residence_time():
    f=pd.DataFrame({'Time':[0,1,2],'U_inst':[0,1,2],'V_inst':[0,0,0],'W_inst':[0,0,0]})
    r=trace_statistics(f)
    assert r['unweighted_population_moments']['variance'][0]==pytest.approx(2/3)
    assert r['trapezoidal_node_weighted_moments']['variance'][0]==.5
    assert 'neither residence-time weights' in r['weighting_status']
    f.loc[2,'Time']=1
    with pytest.raises(ValueError,match='Invalid time series'):trace_statistics(f)


def table():
    values=np.array([[.1,1.0000000000000002],[np.pi,np.nextafter(1.,0.)]])
    data=np.empty((1,2),object);names=np.empty((1,2),object)
    for i,name in enumerate(('U_mean','V_mean')):data[0,i]=values[:,i,None];names[0,i]=np.array([name])
    props=dict(nrows=np.array([[2.]]),nvars=np.array([[2.]]),varnames=names,data=data)
    return pd.DataFrame(values,columns=['U_mean','V_mean']),SimpleNamespace(classname='table',properties=props)


def test_raw_table_mapping_cannot_silently_swap_column_names():
    frame,opaque=table()
    np.testing.assert_array_equal(raw_table(frame,opaque),frame.to_numpy())
    with pytest.raises(ValueError,match='shape/name mismatch'):raw_table(frame[['V_mean','U_mean']],opaque)


def test_numeric_csv_export_preserves_binary_values(tmp_path):
    frame,opaque=table();r=export_table(tmp_path,'roundtrip',frame,opaque)
    assert r['decoded_raw_properties_equal'] and r['csv_roundtrip_exact']


def roughness_export():
    root=Path(__file__).resolve().parents[2]
    return pd.read_csv(root/'docs/data/next-pedestrian-campaign/stress-reference-audit/surrey-numeric-exports/Urban_roughness.csv.gz')


def test_urban_named_table_contains_suburban_reference_with_three_variances():
    inventory=roughness_profile_inventory(roughness_export())
    assert inventory['rows']==101 and inventory['suburban_reference_present']
    profiles=inventory['profiles']
    assert [p['x_hat_over_l_D'] for p in profiles]==[-10,1,2,3,5,6,7,8,9,15,20]
    assert profiles[0]['rows']==11 and all(p['rows']==9 for p in profiles[1:])
    np.testing.assert_array_equal(profiles[0]['heights_mm'],[40,60,90,120,180,240,300,420,660,700,750])
    assert 'Unresolved' in inventory['cluster_inflow_matching_status']


def test_downstream_profiles_do_not_imply_presence_of_suburban_reference():
    frame=roughness_export()
    inventory=roughness_profile_inventory(frame.loc[frame.X_mm>0])
    assert not inventory['suburban_reference_present']
    assert inventory['rows']==90
