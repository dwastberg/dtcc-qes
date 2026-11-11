"""Frozen-input D1 verification. No new wind solves, a 900 s total ceiling."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import resource

import numpy as np

ROOT=Path(os.environ['DTCC_QES_RESEARCH_ROOT'])
sys.path.insert(0,str(ROOT/'validation'))
from covariance_ablations import anisotropy, matrices, spectral_bound, interpolate
from dtcc_qes import _qes
from dtcc_qes._statistics import _stress_validity


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(args,**kwargs):return subprocess.run(args,check=True,timeout=120,**kwargs)
def energy(raw):
    return np.where(_stress_validity(raw)[0],np.maximum(0,.5*np.sum(raw[:,[0,3,5]].astype(float),axis=1)),np.nan)
def summary(values):
    finite=np.asarray(values)[np.isfinite(values)]
    return dict(count=len(finite),minimum=float(finite.min()) if len(finite) else None,
        median=float(np.median(finite)) if len(finite) else None,maximum=float(finite.max()) if len(finite) else None)
def component_bound(raw,bounds):
    scale=np.max(np.abs(raw.astype(float)),axis=1)
    alpha=np.minimum(1,np.divide(bounds,scale,out=np.ones(len(raw)),where=scale>0))
    return (raw.astype(float)*alpha[:,None]).astype(np.float32)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();paths=sorted((ROOT/'docs/data/directed-improvements/raw').glob('*/trace.npz'))
    native=ROOT/'tests/native/stress_replay_probe.cpp';binary=args.output/'stress_replay_probe'
    compiler=run(['c++','--version'],text=True,capture_output=True).stdout
    command=['c++','-std=c++17','-O2','-I'+str(ROOT/'src/qes_core/dtcc/api'),str(native),'-o',str(binary)]
    manifest=dict(schema_version=1,budget_worker_seconds=900,new_wind_solves=0,
        git=run(['git','rev-parse','main','research/pedestrian-wind-campaign'],cwd=ROOT,text=True,capture_output=True).stdout.splitlines(),
        compiler=compiler,compile_command=command,python=sys.version,platform=platform.platform(),
        native_package_sha256=sha(Path(_qes.__file__)),threads={k:os.getenv(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS')},
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        sources={str(p):sha(p) for p in (Path(__file__),native,
            ROOT/'src/qes_core/dtcc/api/covariance_model.h',ROOT/'src/qes_core/dtcc/api/stress_validity.h',
            ROOT/'validation/covariance_ablations.py')})
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    run(command);rows=[]
    for path in paths:
        if time.monotonic()-started>900:raise RuntimeError('D1 worker budget exhausted')
        with np.load(path) as d:trace={k:d[k] for k in d.files}
        with np.load(path.with_name('samples.npz')) as d:samples={k:d[k] for k in d.files}
        props=trace['properties'];orientations=trace['orientations'];bounds=props[:,13]
        computed=trace['tensor_found'].astype(bool).all(axis=0)
        ratio=np.minimum(1,np.divide(props[:,11],props[:,12],out=np.ones(len(props)),where=props[:,12]>0))
        coupled_pre=(trace['uncapped_constitutive_reconstruction'].astype(float)*ratio[:,None]).astype(np.float32)
        coupled=np.full_like(coupled_pre,np.nan)
        finite=computed & np.isfinite(orientations).all(axis=1) & np.isfinite(coupled_pre).all(axis=1)
        coupled[finite]=anisotropy(coupled_pre[finite],orientations[finite],False)
        tensors=dict(legacy=trace['tensors'][2],coupled_only=coupled,
            final_limit_only=spectral_bound(trace['tensors'][1],bounds),
            combined_spectral=spectral_bound(coupled,bounds),combined_component=component_bound(coupled,bounds))
        inputs=np.column_stack((props,orientations));take=np.isfinite(inputs).all(axis=1)
        payload='\n'.join(' '.join(format(float(v),'.17g') for v in row) for row in inputs[take])+'\n'
        native_output=run([str(binary)],input=payload,text=True,capture_output=True)
        replay=np.fromstring(native_output.stdout,sep=' ').reshape(-1,18)
        error=np.abs(replay[:,12:]-tensors['combined_spectral'][take])/np.maximum(1,np.max(np.abs(replay[:,12:]),axis=1))[:,None]
        native_error=float(np.nanmax(error))
        if native_error>16*np.finfo(np.float32).eps:raise AssertionError('Native coupled replay differs from oracle')
        baseline=_stress_validity(tensors['legacy'])[0]&computed
        stages={name:dict(valid=int((_stress_validity(t)[0]&computed).sum()),
            invalid_computed=int((~_stress_validity(t)[0]&computed).sum()),
            recovered=int((~baseline&_stress_validity(t)[0]&computed).sum()),
            lost=int((baseline&~_stress_validity(t)[0]).sum())) for name,t in tensors.items()}
        axes=[samples[k].astype(float)+samples['origin'][i] for i,k in enumerate('xyz')]
        queries={name:interpolate(t,trace,samples['points'],axes) for name,t in tensors.items()}
        before=queries['legacy'][1];after=queries['combined_spectral'][1]
        spectral=tensors['combined_spectral'];component=tensors['combined_component']
        # Rotating all tensors changes the component rule, not the spectral radius.
        theta=.731;c,s=np.cos(theta),np.sin(theta);q=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        rotated=q@matrices(coupled)@q.T
        packed=rotated[:,(0,0,0,1,1,2),(0,1,2,1,2,2)].astype(np.float32)
        rotated_spectral=spectral_bound(packed,bounds);rotated_component=component_bound(packed,bounds)
        rows.append(dict(name=path.parent.name,source_rows=len(props),computed=int(computed.sum()),
            unsupported=int((~computed).sum()),native_maximum_scaled_error=native_error,stages=stages,
            queries=dict(requested=len(before),recovered=int((~before&after).sum()),lost=int((before&~after).sum()),
                valid_before=int(before.sum()),valid_after=int(after.sum())),
            physical_k_spectral_minus_component=summary(energy(spectral)-energy(component)),
            query_physical_k_spectral_minus_component=summary(np.where(queries['combined_spectral'][1]&
                queries['combined_component'][1],energy(queries['combined_spectral'][0])-energy(queries['combined_component'][0]),np.nan)),
            component_rotation_energy_difference=summary(energy(rotated_component)-energy(component)),
            spectral_rotation_energy_difference=summary(energy(rotated_spectral)-energy(spectral))))
    gates=dict(all_computed_psd=all(r['stages']['combined_spectral']['invalid_computed']==0 for r in rows),
        no_valid_query_lost=all(r['queries']['lost']==0 for r in rows),
        native_oracle_agreement=all(r['native_maximum_scaled_error']<=16*np.finfo(np.float32).eps for r in rows))
    report=dict(schema_version=1,manifest_sha256=sha(args.output/'manifest.json'),rows=rows,gates=gates,
        elapsed_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        native_probe_sha256=sha(binary),new_wind_solves=0,
        interpretation='Uniform spectral bounding is rotation covariant. Component bounding depends on the frame; '
            'its smaller component norm generally leaves more energy than the spectral norm. Neither uniform '
            'scaling repairs a materially indefinite input. Native and independent float64 oracle must agree.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(gates=gates,computed=sum(r['computed'] for r in rows),
        queries=sum(r['queries']['requested'] for r in rows),elapsed_seconds=report['elapsed_seconds']),indent=2))

if __name__=='__main__':main()
