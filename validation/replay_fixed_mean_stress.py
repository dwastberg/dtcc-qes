"""Three frozen covariance constructions on archived mean fields; no flow solve."""
import argparse
import io
import json
from pathlib import Path
import subprocess

import numpy as np

from aij import tables
import benchmark_evidence as pedestrian
from frozen_stress_support import read,run_folder
from frozen_stress_support import stencil
from covariance_ablations import anisotropy,matrices,spectral_bound
from dtcc_qes._statistics import _stress_validity

ROOT=Path(__file__).resolve().parents[1]
ARM_NAMES=('legacy','spectral_only','bounded_consistent')


def constructions(trace):
    found=trace['tensor_found'].all(axis=0)
    p=trace['properties'];orient=trace['orientations']
    if not np.isfinite(p[found]).all() or not np.isfinite(orient[found]).all():
        raise ValueError('Computed contributor has missing construction inputs')
    outputs=dict(legacy=trace['tensors'][2].copy(),spectral_only=spectral_bound(trace['tensors'][1],p[:,13]))
    ratio=np.minimum(1,np.divide(p[:,11],p[:,12],out=np.ones(len(p)),where=p[:,12]>0))
    pre=(trace['uncapped_constitutive_reconstruction'].astype(float)*ratio[:,None]).astype(np.float32)
    post=np.full_like(pre,np.nan);post[found]=anisotropy(pre[found],orient[found],False)
    outputs['bounded_consistent']=spectral_bound(post,p[:,13])
    legacy_post=anisotropy(trace['tensors'][0,found],orient[found],False)
    scale=np.maximum(1,np.max(np.abs(trace['tensors'][1,found]),axis=1))
    error=np.max(np.abs(legacy_post-trace['tensors'][1,found]),axis=1)/scale
    if np.max(error)>16*np.finfo(np.float32).eps:raise ValueError('Legacy anisotropy replay exceeds frozen envelope')
    np.testing.assert_array_equal(trace['tensors'][2,found],np.clip(trace['tensors'][1,found],-p[found,13,None],p[found,13,None]))
    return outputs,found,float(error.max())


def sample_tensors(raw,trace,samples,points):
    axes=[samples[k].astype(float)+samples['origin'][i] for i,k in enumerate('xyz')]
    s=stencil(dict(axes=axes,solid=np.zeros(tuple(len(a) for a in axes[::-1]),bool)),points)
    lookup={tuple(c):i for i,c in enumerate(trace['tensor_cells'])}
    computed=trace['tensor_found'].all(axis=0);source_valid=_stress_validity(raw)[0]
    values=np.full((len(points),6),np.nan);valid=np.zeros(len(points),bool);covered=valid.copy();bad_weight=np.zeros(len(points))
    for q,(indices,weights,inside) in enumerate(zip(s['indices'],s['weights'],s['supported'],strict=True)):
        take=weights>0;cells=indices[take,::-1]
        if not inside or any(tuple(c) not in lookup for c in cells):continue
        at=np.array([lookup[tuple(c)] for c in cells]);w=weights[take]
        if not computed[at].all():continue
        covered[q]=True;values[q]=np.sum(raw[at].astype(float)*w[:,None],axis=0)
        bad_weight[q]=w[~source_valid[at]].sum()
        valid[q]=bool(source_valid[at].all() and _stress_validity(values[q:q+1])[0][0])
    return dict(stress=values,valid=valid,covered=covered,invalid_source_weight=bad_weight,
                interpolant_valid=_stress_validity(values)[0])


def score(values,measured,population):
    at=np.asarray(population,bool);values=np.asarray(values,float);measured=np.asarray(measured,float)
    missing=at&~np.isfinite(values)
    if missing.any():return dict(count=int(at.sum()),complete=False,missing_indices=np.flatnonzero(missing))
    a,b=values[at],measured[at];err=a-b
    correlation=float(np.corrcoef(a,b)[0,1]) if len(a)>2 and np.std(a)>0 and np.std(b)>0 else None
    return dict(count=int(at.sum()),complete=True,rmse=float(np.sqrt(np.mean(err*err))),
        mae=float(np.mean(np.abs(err))),bias=float(np.mean(err)),correlation=correlation)


def d_scores(record,point_outputs):
    measured=tables.load_exp_s();np.testing.assert_array_equal(measured.ids,record['probes']['ids'])
    parent=measured.measured&point_outputs['legacy']['valid']
    target=np.column_stack([measured.k,measured.variance])/tables.U_H**2
    result={}
    for arm,p in point_outputs.items():
        raw=p['stress']/record['reference_speed']**2
        values=np.column_stack([.5*raw[:,[0,3,5]].sum(axis=1),raw[:,[0,3,5]]]);values[~p['valid']]=np.nan
        metrics={name:score(values[:,i],target[:,i],parent) for i,name in enumerate(('k','xx','yy','zz'))}
        result[arm]=dict(scores=metrics,lost_ids=measured.ids[parent&~p['valid']],
            recovered_ids=measured.ids[measured.measured&~point_outputs['legacy']['valid']&p['valid']],
            values=values,baseline_population_ids=measured.ids[parent])
    for arm in result:
        for name,m in result[arm]['scores'].items():
            base=result['legacy']['scores'][name]
            m['relative_rmse_change']=m['rmse']/base['rmse']-1 if m['complete'] and base['rmse'] else None
            m['correlation_change']=m['correlation']-base['correlation'] if m.get('correlation') is not None and base['correlation'] is not None else None
    return result


def native_check(executable,trace,outputs,found,folder):
    inputs=np.column_stack([trace['properties'][found],trace['orientations'][found]])
    text=io.StringIO();np.savetxt(text,inputs,fmt='%.17g')
    p=subprocess.run([str(executable.resolve())],input=text.getvalue(),capture_output=True,text=True,timeout=30)
    (folder/'native-stderr.log').write_text(p.stderr)
    if p.returncode:raise ValueError('Native constitutive helper failed')
    actual=np.fromstring(p.stdout,sep=' ').astype(np.float32).reshape(-1,3,6)
    expected=[trace['tensors'][1,found],outputs['spectral_only'][found],outputs['bounded_consistent'][found]]
    checks={}
    for i,(name,wanted) in enumerate(zip(('legacy_post','spectral_only','bounded_consistent'),expected,strict=True)):
        scale=np.maximum(1,np.max(np.abs(wanted),axis=1));error=np.max(np.abs(actual[:,i].astype(float)-wanted),axis=1)/scale
        disagreements=int(np.count_nonzero(_stress_validity(actual[:,i])[0]!=_stress_validity(wanted)[0]))
        checks[name]=dict(maximum_scaled_error=float(error.max()),validity_disagreements=disagreements)
        if error.max()>16*np.finfo(np.float32).eps or disagreements:raise ValueError(f'Native replay envelope/validity failure: {name}')
    np.savez_compressed(folder/'native-replay.npz',inputs=inputs,outputs=actual)
    return checks


def analyse(archive,executable,output):
    output.mkdir(parents=True,exist_ok=False)
    sources={p:pedestrian.digest(ROOT/p) for p in ('validation/replay_fixed_mean_stress.py',
        'validation/covariance_ablations.py','tests/native/stress_replay_probe.cpp','validation/FIXED_MEAN_STRESS_REPLAY_PROTOCOL.md')}
    pedestrian.write_json(output/'manifest.json',dict(sources=sources,executable_sha256=pedestrian.digest(executable),
        archive_manifest_sha256=pedestrian.digest(archive/'manifest.json'),arms=ARM_NAMES,new_aij_launches=0))
    for name in sources:
        p=output/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    checks=read(archive/'checksums.json')
    for name,sha in checks.items():
        if pedestrian.digest(archive/name)!=sha:raise ValueError('Archived capture changed')
    manifest=read(archive/'manifest.json');rows=[];saved={}
    for descriptor in manifest['descriptors']:
        name=descriptor['run_name'];folder=run_folder(archive,name);dest=output/name;dest.mkdir()
        r=read(folder/'worker.json')
        if r['descriptor']!=descriptor or not all(r['guards'].values()):raise ValueError('Unqualified archived worker')
        with np.load(folder/'trace.npz') as d:trace={k:d[k] for k in d.files}
        with np.load(folder/'samples.npz') as d:samples={k:d[k] for k in d.files}
        tensors,found,reconstruction=constructions(trace)
        native=native_check(executable,trace,tensors,found,dest)
        outputs={};statistics={};arrays={}
        for arm,raw in tensors.items():
            observed=sample_tensors(raw,trace,samples,samples['observed'])
            if arm=='legacy':
                np.testing.assert_allclose(observed['stress'],samples['observed_stress'],rtol=0,atol=0,equal_nan=True)
                np.testing.assert_array_equal(observed['valid'],samples['observed_stress_valid'])
            point=sample_tensors(raw,trace,samples,r['probes']['sampled']);outputs[arm]=point
            if arm=='legacy':
                np.testing.assert_allclose(point['stress'],r['probes']['stress'],rtol=0,atol=0,equal_nan=True)
                np.testing.assert_array_equal(point['valid'],r['probes']['stress_valid'])
            eigen=np.linalg.eigvalsh(matrices(raw[found]));radius=np.max(np.abs(eigen),axis=1);bound=trace['properties'][found,13]
            cell_valid=_stress_validity(raw[found])[0]
            statistics[arm]=dict(invalid_computed_sources=int((~cell_valid).sum()),minimum_eigenvalue=float(eigen.min()),
                spectral_bound_violations=int(np.count_nonzero(radius>bound*(1+16*np.finfo(np.float32).eps))),
                valid_observations=int(point['valid'].sum()),covered_observations=int(point['covered'].sum()),
                lost_ids=np.asarray(r['probes']['ids'])[outputs['legacy']['valid']&~point['valid']],
                recovered_ids=np.asarray(r['probes']['ids'])[~outputs['legacy']['valid']&point['valid']],
                observed_height_queries=len(observed['valid']),valid_height_queries=int(observed['valid'].sum()),
                valid_interpolant_with_invalid_sources=int(np.count_nonzero(observed['interpolant_valid']&observed['covered']&~observed['valid'])),
                raw_half_trace_range=[float(.5*raw[found][:,[0,3,5]].sum(axis=1).min()),float(.5*raw[found][:,[0,3,5]].sum(axis=1).max())])
            for key,value in point.items():arrays[f'{arm}_{key}']=value
            arrays[f'{arm}_source_stress']=raw
        scores=d_scores(r,outputs) if descriptor['case']=='D' and descriptor['spec']['label']=='0 deg.' else None
        focus={}
        if name.startswith('E-WSW-after'):
            i=r['probes']['ids'].index(60)
            focus['site60']={arm:{key:value[i] for key,value in p.items()} for arm,p in outputs.items()}
        if name.startswith('D-offset_y'):
            focus['sites48_58']={str(site):{arm:dict(stress=p['stress'][r['probes']['ids'].index(site)],valid=p['valid'][r['probes']['ids'].index(site)]) for arm,p in outputs.items()} for site in (48,58)}
        row=dict(name=name,case=descriptor['case'],computed_source_instances=int(found.sum()),
            capture_source_cells=len(found),native_comparison=native,legacy_anisotropy_scaled_error=reconstruction,
            arms=statistics,D_measured_scores=scores,focus=focus,
            mean_velocity_sha256=r['whole_velocity_sha256'],raw_legacy_interpolation_exact=True)
        rows.append(row);saved[name]=(r,outputs)
        np.savez_compressed(dest/'arrays.npz',**arrays)
        print(name,'invalid sources', {a:v['invalid_computed_sources'] for a,v in statistics.items()},flush=True)
    paired={};measured=tables.load_exp_s();target=np.column_stack([measured.k,measured.variance])/tables.U_H**2
    for layout in ('reference','offset_x','offset_y'):
        a,pa=saved[f'D-{layout}-legacy'];b,pb=saved[f'D-{layout}-candidate']
        parent=measured.measured&pa['legacy']['valid']&pb['legacy']['valid'];paired[layout]={}
        for arm in ARM_NAMES:
            values=[]
            for r,p in ((a,pa),(b,pb)):
                t=p[arm]['stress']/r['reference_speed']**2
                v=np.column_stack([.5*t[:,[0,3,5]].sum(axis=1),t[:,[0,3,5]]]);v[~p[arm]['valid']]=np.nan;values.append(v)
            paired[layout][arm]={name:dict(legacy_mean=score(values[0][:,j],target[:,j],parent),
                V2_mean=score(values[1][:,j],target[:,j],parent)) for j,name in enumerate(('k','xx','yy','zz'))}
    report=dict(schema='fixed-mean-stress-replay-v1',new_aij_launches=0,archived_mean_fields=len(rows),
        arms=ARM_NAMES,archive_files_verified=len(checks),computed_source_instances=sum(r['computed_source_instances'] for r in rows),
        rows=rows,paired_mean_fields=paired,whole_domain_validity_assessed=False,native_canyon_covariance_composition_executed=False)
    pedestrian.write_json(output/'report.json',report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native',type=Path,required=True);p.add_argument('--archive',type=Path,default=ROOT/'docs/data/physical-canyon-v2')
    a=p.parse_args();analyse(a.archive,a.native,a.output)


if __name__=='__main__':main()
