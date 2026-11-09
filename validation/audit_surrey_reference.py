"""Export the acquired Surrey tables and audit eligibility, without fitting a model."""
import argparse
import csv
import gzip
import io
import importlib.metadata
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from scipy.io import loadmat

import benchmark_evidence as pedestrian

ROOT=Path(__file__).resolve().parents[1]


def raw_table(frame,opaque):
    """Check converted numeric columns against the decoded raw MCOS properties."""
    if opaque.classname!='table':raise ValueError('Expected a MATLAB table')
    props=opaque.properties;nrows=int(props['nrows'].item());nvars=int(props['nvars'].item())
    names=[str(v.item()) for v in props['varnames'].ravel()]
    if frame.shape!=(nrows,nvars) or frame.columns.tolist()!=names:raise ValueError('MATLAB table shape/name mismatch')
    data=np.column_stack([np.asarray(c).ravel() for c in props['data'].ravel()])
    np.testing.assert_array_equal(data,frame.to_numpy())
    if not np.issubdtype(data.dtype,np.number):raise ValueError('Non-numeric scientific table')
    return data


def moments(velocity,weights):
    velocity=np.asarray(velocity,float);weights=np.asarray(weights,float)
    if not np.isfinite(velocity).all() or not np.isfinite(weights).all() or np.any(weights<0) or weights.sum()<=0:
        raise ValueError('Invalid statistical input')
    weights=weights/weights.sum();mean=np.sum(weights[:,None]*velocity,axis=0)
    delta=velocity-mean;covariance=np.einsum('n,ni,nj->ij',weights,delta,delta)
    return dict(mean=mean,covariance=covariance,variance=np.diag(covariance),k=.5*np.trace(covariance))


def trace_statistics(frame):
    if frame.columns.tolist()!=['Time','U_inst','V_inst','W_inst']:raise ValueError('Time-series schema changed')
    a=frame.to_numpy(float);time=a[:,0];dt=np.diff(time)
    if len(a)<3 or not np.isfinite(a).all() or np.any(dt<=0):raise ValueError('Invalid time series')
    uniform=moments(a[:,1:],np.ones(len(a)))
    weights=np.r_[dt[0]/2,(dt[:-1]+dt[1:])/2,dt[-1]/2]
    weighted=moments(a[:,1:],weights)
    return dict(samples=len(a),first_time=float(time[0]),last_time=float(time[-1]),
        duration=float(time[-1]-time[0]),interval_range=[float(dt.min()),float(dt.max())],
        mean_sample_rate=float(1/dt.mean()),interval_cv=float(dt.std()/dt.mean()),
        unweighted_population_moments=uniform,trapezoidal_node_weighted_moments=weighted,
        weighting_status='Descriptive reductions only: neither residence-time weights nor resampling history is supplied',
        covariance_minimum_eigenvalue=float(np.linalg.eigvalsh(uniform['covariance']).min()))


def export_table(output,name,frame,opaque):
    data=raw_table(frame,opaque)
    filename=name+'.csv.gz';payload=frame.to_csv(index=False,float_format='%.17g').encode()
    (output/filename).write_bytes(gzip.compress(payload,mtime=0))
    parsed=list(csv.reader(io.StringIO(gzip.decompress((output/filename).read_bytes()).decode())))
    if parsed[0]!=frame.columns.tolist():raise ValueError('CSV column names changed')
    roundtrip=np.array([[float(v) for v in row] for row in parsed[1:]])
    np.testing.assert_array_equal(roundtrip,data)
    result=dict(rows=len(frame),columns=frame.columns.tolist(),shape=list(data.shape),
        finite_values=int(np.isfinite(data).sum()),nonfinite_values=int((~np.isfinite(data)).sum()),
        decoded_raw_properties_equal=True,csv_roundtrip_exact=True,export=filename,
        export_sha256=pedestrian.digest(output/filename))
    if 'Z_mm' in frame:result['heights_mm']=np.unique(frame['Z_mm'])
    return result


def roughness_profile_inventory(frame):
    """Inventory stations using the roughness origin, not the cluster origin.

    The paper's section 2.2 defines x_hat=x+735 mm and l_D=70 mm.
    Figure 5 identifies the x_hat/l_D=-10 profile as the Suburban case;
    the Urban_roughness filename does not mean all rows are urban inflow.
    """
    columns=['X_mm','Y_mm','Z_mm','U_mean','V_mean','W_mean',
        'U_variance','V_variance','W_variance']
    values=frame[columns].to_numpy(float)
    if not np.isfinite(values).all() or np.any(values[:,-3:]<0):
        raise ValueError('Invalid roughness profile values')
    station=np.rint(frame['X_mm'].to_numpy(float)/70).astype(int)
    if np.any(np.abs(frame['X_mm'].to_numpy(float)-70*station)>.05):
        raise ValueError('Unrecognized roughness-profile station')
    profiles=[]
    for position in np.unique(station):
        group=frame.loc[station==position]
        profiles.append(dict(x_hat_over_l_D=int(position),rows=len(group),
            x_hat_mm_range=[float(group.X_mm.min()),float(group.X_mm.max())],
            heights_mm=np.unique(group.Z_mm),
            interpretation='Suburban reference (paper Figure 5)' if position==-10
                else 'Urban roughness adjustment' if position>0 else 'Unclassified station'))
    return dict(rows=len(frame),profiles=profiles,
        suburban_reference_present=bool(np.any(station==-10)),
        coordinate_convention='X_mm interpreted as x_hat, measured from start of Urban roughness; cluster-centred x=x_hat-735 mm',
        interpretation_source='Paper section 2.2 and Figure 5',
        cluster_inflow_matching_status='Unresolved: presence of a Suburban reference does not establish condition-matched cluster inflow')


def audit(inputs,output,catalogue):
    # mat-io 1.0.2 sets a pandas option whose behaviour is already the default
    # in pandas 3. Capture this known import deprecation without masking others.
    with warnings.catch_warnings(record=True) as compatibility_warnings:
        warnings.filterwarnings('always',message="The 'future.infer_string' option is deprecated.*")
        import matio
    output.mkdir(parents=True,exist_ok=False);exports=output/'exports';exports.mkdir()
    intake=json.loads((ROOT/'validation/INDEPENDENT_REFERENCE_INTAKE.json').read_text())
    original=next(r for r in intake['references'] if r['id']=='surrey-5x7wv')
    checked={}
    for record in original['files'].values():
        p=inputs/Path(record['local_path']).name
        if pedestrian.digest(p)!=record['sha256']:raise ValueError('Acquired Surrey input changed')
        checked[p.name]=record['sha256']
    if pedestrian.digest(inputs/'surrey-paper.pdf')!=original['paper_sha256']:raise ValueError('Paper changed')
    paths={'urban':inputs/'surrey-urban.mat','semiurban':inputs/'surrey-semiurban.mat','timetrace':inputs/'surrey-timetrace.mat'}
    converted={};raw={};tables={}
    for label,path in paths.items():
        converted[label]=matio.load_from_mat(path,add_table_attrs=True)
        raw[label]=matio.load_from_mat(path,raw_data=True)
        scipy=loadmat(path)
        top_names={k for k in scipy if not k.startswith('__')}
        if top_names!=set(converted[label]):raise ValueError('Top-level variable mapping changed')
        for name,value in converted[label].items():
            if isinstance(value,pd.DataFrame):tables[name]=export_table(exports,name,value,raw[label][name])
    traces=[];numeric={};coords=[]
    for condition in ('SemiUrban','Urban'):
        key=condition+'_4x4_timetrace';coordinate_key=key+'_coordinate'
        cells=converted['timetrace'][key].ravel();raw_cells=raw['timetrace'][key].ravel()
        coordinates=converted['timetrace'][coordinate_key]
        if len(cells)!=len(coordinates):raise ValueError('Time-series coordinate mapping mismatch')
        for i,(frame,opaque) in enumerate(zip(cells,raw_cells,strict=True)):
            a=raw_table(frame,opaque);name=f'{condition}-{i:02d}'
            numeric[name]=a;point=coordinates.iloc[i].to_numpy(float)
            stats=trace_statistics(frame)
            row=dict(name=name,condition=condition,index=i,coordinate_mm=point,coordinate_m=point/1000,
                z_over_building_height=float(point[2]/240),columns=frame.columns.tolist(),
                raw_payload_sha256=__import__('hashlib').sha256(a.tobytes(order='C')).hexdigest(),**stats)
            # Independent supplied summary comparison only at the same actual height and position.
            summary=converted['urban' if condition=='Urban' else 'semiurban'][condition+'_4x4_longitudinal']
            distance=np.linalg.norm(summary[['X_mm','Y_mm','Z_mm']].to_numpy()-point,axis=1)
            matches=np.flatnonzero(distance<=.01)
            if len(matches)==1:
                s=summary.iloc[matches[0]];mean=stats['unweighted_population_moments']['mean']
                row['matched_summary']=dict(distance_mm=float(distance[matches[0]]),
                    U_mean=float(s['U_mean']),W_mean=float(s['W_mean']),
                    U_difference=float(mean[0]-s['U_mean']),W_difference=float(mean[2]-s['W_mean']),
                    U_relative_difference=float(mean[0]/s['U_mean']-1),
                    status='Same-coordinate check, not evidence of identical acquisition/processing')
            else:row['matched_summary']=None
            traces.append(row);coords.append(point)
    np.savez_compressed(exports/'time-traces.npz',**numeric)
    with np.load(exports/'time-traces.npz') as saved:
        for name,a in numeric.items():np.testing.assert_array_equal(saved[name],a)
    eligibility=dict(
        independent_physics=dict(status='pass',evidence='Independent EnFlo wind tunnel experiment'),
        geometry_and_roughness=dict(status='partial',evidence='Building dimensions documented; explicit roughness layout and origin reconstruction remain outstanding'),
        inflow_mean_and_three_variances=dict(status='partial',evidence='Urban_roughness includes an 11-height Suburban reference at x_hat/l_D=-10 and ten Urban adjustment profiles, all with three means/variances; matching these to the cluster inlet remains unresolved'),
        pedestrian_and_two_higher_levels=dict(status='fail',evidence='Wake time traces: suburban z=60 mm=0.25HB; urban z=120 mm=0.5HB; one height per condition'),
        mean_vectors_and_three_variances=dict(status='partial',evidence='13 three-component traces decoded; variance statistics require acquisition/weighting qualification'),
        instrument_averaging_uncertainty=dict(status='fail',evidence='LDA, nominal acquisition and generic errors documented; residence-time weighting/resampling and same-acquisition mapping unresolved'),
        normalization_and_scale=dict(status='partial',evidence='SI velocities, mm coordinates and 2 m/s freestream documented; physical pedestrian scaling and roughness-origin mapping not frozen'),
        data_readable_and_quality_checked=dict(status='partial',evidence='Raw properties/column names/dimensions and numeric exports checked exactly; published velocity reduction not reproduced by simple means'))
    reader=Path(matio.__file__).parent
    catalogue_text=catalogue.read_text()
    if 'password protected' not in catalogue_text or 'Policy Agreement' not in catalogue_text:
        raise ValueError('Hamburg access evidence requires manual review')
    manifest=dict(schema='surrey-reference-audit-v1',date='2026-11-09',input_sha256=checked,
        paper_sha256=original['paper_sha256'],reader_package='mat-io',reader_version=importlib.metadata.version('mat-io'),
        reader_sources={str(p.relative_to(reader)):pedestrian.digest(p) for p in sorted(reader.rglob('*')) if p.is_file() and p.suffix in ('.py','.so')},
        reader_import_compatibility_warnings=[str(w.message) for w in compatibility_warnings],
        script_sha256=pedestrian.digest(__file__),tables=tables,traces=traces,
        roughness_profiles=roughness_profile_inventory(converted['urban']['Urban_roughness']),
        numeric_time_trace_export=dict(path='exports/time-traces.npz',sha256=pedestrian.digest(exports/'time-traces.npz'),roundtrip_exact=True),
        eligibility=eligibility,qualified=False,qualified_reference_ids=[],new_aij_launches=0,
        statistic_status='Structurally checked numeric export; physical/statistical reduction remains unqualified',
        height_warning='Multiheight concentration and roughness-only tables do not add multiheight wake velocity variances',
        column_discrepancy='Upstream lateral tables contain Y_mm, Z_mm, U_mean; the readme lists different upstream column names',
        hamburg=dict(catalogue_url='https://www.mi.uni-hamburg.de/en/arbeitsgruppen/windkanallabor/data-sets.html',
            catalogue_sha256=pedestrian.digest(catalogue),checked_date='2026-11-09',
            status='Measurement archives are password protected; the COST ES1006 Michelstadt collection also requires a signed data policy',
            contacts_sent=False,agreements_signed=False,confirmation_measurements_inspected=False))
    pedestrian.write_json(output/'report.json',manifest)
    print('Exported',len(tables),'tables and',len(traces),'traces;',sum(len(a) for a in numeric.values()),'time samples; qualified=False')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,default=ROOT/'build/reference-intake')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--hamburg-catalogue',type=Path,required=True)
    a=p.parse_args();audit(a.inputs,a.output,a.hamburg_catalogue)


if __name__=='__main__':main()
