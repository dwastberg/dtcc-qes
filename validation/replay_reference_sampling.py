"""Replay reference/cap choices on frozen native captures; no mean-flow solves."""
import argparse
import gzip
import json
from pathlib import Path
import numpy as np
from benchmark_evidence import digest,write_json
from dtcc_qes._statistics import _stress_validity
from surrey_background import MEANS,VARIANCES,summarize
ARMS=('legacy','wide_sum','interpolate','interpolate_wide')


def manufactured_checks(raw):
    rows=raw['cases'];errors={};guards={}
    for field in ('affine','turning','vertical','curved'):
        errors[field]={}
        for h in sorted({r['spacing'] for r in rows},reverse=True):
            selected=[r for r in rows if r['field']==field and r['spacing']==h]
            actual=[];legacy=[]
            for r in selected:
                z=r['reference']
                expected=(1+2*z+(4*z*z if field=='curved' else 0)) if field in ('affine','curved') else np.hypot(1,20*(z-.21)) if field=='turning' else np.hypot(1,.2+3*z)
                actual.append(abs(r['interpolation']['double_mean']-expected));legacy.append(abs(r['legacy_float_mean']-expected))
            errors[field][str(h)]=dict(candidate_max_error=max(actual),legacy_max_error=max(legacy))
        if field!='curved':guards[field+'_analytic']=max(v['candidate_max_error'] for v in errors[field].values())<=2e-6
    curve=[v['candidate_max_error'] for v in errors['curved'].values()]
    guards['curved_refinement']=all(b<a for a,b in zip(curve,curve[1:]))
    guards['support']=raw['support']==dict(masked_count=3,empty_supported=False,below_supported=False)
    guards['constant_wide_sum']=all(abs(r['double_mean']-r['oracle'])<2e-12 for r in raw['constant_reductions'])
    return dict(cases=len(rows),errors=errors,constant_reductions=raw['constant_reductions'],
        morphometric_references=raw['morphometric_references'],guards=guards)


def source_cells(record):
    details=record['support']['contributors'];cells=set()
    for at,weights in zip(details['indices'],details['weights'],strict=True):
        cells.update(tuple(c) for c,w in zip(at,weights,strict=True) if w>0)
    return sorted(cells)

def sample(raw,record,arm,actual=False):
    sources=raw['sources'];lookup={tuple(r['cell']):i for i,r in enumerate(sources)}
    tensors=np.array([r['actual_stress'] if actual else r['replays'][arm] for r in sources],np.float32)
    source_valid=_stress_validity(tensors)[0];output=[];details=record['support']['contributors']
    for at,weights in zip(details['indices'],details['weights'],strict=True):
        positive=np.array(weights)>0;indices=[lookup[tuple(c)] for c,w in zip(at,positive,strict=True) if w]
        value=np.sum(tensors[indices].astype(float)*np.array(weights)[positive,None],axis=0)
        valid=bool(source_valid[indices].all() and _stress_validity(value[None,:])[0][0])
        output.append((value,valid))
    return tensors,output

def replay_rows(raw,record,observed):
    groups={};arrays={};sources=raw['sources'];p=np.array([r['properties'] for r in sources],np.float32)
    for arm,name in enumerate(ARMS):
        tensors,values=sample(raw,record,arm);rows=[]
        internal=np.minimum(p[:,12],raw['bound'][arm]);lookup={tuple(r['cell']):i for i,r in enumerate(sources)}
        for n,(row,(tensor,valid)) in enumerate(zip(observed,values,strict=True)):
            diagonal=tensor[[0,3,5]]/4;fractions=diagonal/diagonal.sum()
            details=record['support']['contributors'];weights=np.array(details['weights'][n]);at=details['indices'][n]
            ids=[lookup[tuple(c)] for c,w in zip(at,weights,strict=True) if w>0]
            r=dict(id=row['id'],velocity_valid=True,computed=True,stress_valid=valid,
                internal_k=float(np.sum(internal[ids]*weights[weights>0])/4),k=float(.5*diagonal.sum()))
            r.update({q:record['predictions'][n][q] for q in MEANS})
            r.update(dict(zip(VARIANCES,diagonal,strict=True)));r.update(dict(zip(('f_u','f_v','f_w'),fractions,strict=True)))
            rows.append(r)
        groups[name]=dict(scores=summarize(observed,rows),predictions=rows,
            invalid_sources=int((~_stress_validity(tensors)[0]).sum()),invalid_probes=sum(not r['stress_valid'] for r in rows),
            speed=raw['speed'][arm],friction_velocity=raw['friction_velocity'][arm],bound=raw['bound'][arm])
        arrays[name+'_sources']=tensors;arrays[name+'_sampled']=np.array([v[0] for v in values]);arrays[name+'_valid']=np.array([v[1] for v in values])
    return groups,arrays



def replay(study, mean_archive, output):
    """Reproduce all four arms from checksum-verified, already solved inputs."""
    from surrey_background import ROOT, observations
    for folder in (study, mean_archive):
        checks=json.loads((folder/'checksums.json').read_text())
        for name,sha in checks.items():
            if digest(folder/name)!=sha: raise ValueError('Archived capture changed: '+name)
    protocol=json.loads((ROOT/'validation/specifications/surrey_background_v1.json').read_text())
    observed=observations(protocol, ROOT/protocol['source'])
    output.mkdir(parents=True,exist_ok=False)
    manufactured=json.loads((study/'manufactured.json').read_text())
    checks=manufactured_checks(manufactured)
    if not all(checks['guards'].values()): raise ValueError('Manufactured evidence failed')
    (output/'manufactured.json').write_text(json.dumps(manufactured)+'\n')
    rows=[]
    for name in ('empty-coarse','street-coarse','block-coarse','empty-fine','street-fine','block-fine'):
        raw=json.loads((study/name/'native.json').read_text())
        record=json.loads((mean_archive/name/'worker.json').read_text())
        groups,arrays=replay_rows(raw,record,observed)
        with np.load(study/name/'replays.npz') as expected:
            for key,values in arrays.items(): np.testing.assert_array_equal(values,expected[key])
        folder=output/name;folder.mkdir();np.savez_compressed(folder/'replays.npz',**arrays)
        rows.append(dict(name=name,reference_height=raw['reference_height'],legacy_height=raw['legacy_height'],arms=groups))
    write_json(output/'report.json',dict(schema='reference-sampling-results-v1',cases=rows,
        manufactured=checks,mean_reproductions=0,new_aij_launches=0,
        physical_qualification=False,default_reference_changed=False,
        study_checksums_sha256=digest(study/'checksums.json'),mean_archive_checksums_sha256=digest(mean_archive/'checksums.json')))
    write_json(output/'checksums.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--mean-archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();replay(args.study,args.mean_archive,args.output)


if __name__=='__main__': main()
