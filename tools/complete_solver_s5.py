"""Finite S5a follow-up on the separately frozen S5c numerical correction.

Builds are verified through the urban campaign cache. All study workers run
sequentially with 30s worker / 180s six-worker-shard limits. No automatic retries.
"""
from __future__ import annotations
from dataclasses import replace
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tarfile
import time
import numpy as np
import run_urban_benchmarks as campaign
from run_solver_numerics import digest,write

ROOT=Path(__file__).resolve().parents[1]
CASES=['perimeter_neighbourhood_core','mixed_downtown_core']


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    study=ROOT/'build/solver-control-s5c/study'
    archive=study/'sources.tar.gz'
    baseline=out/'s3-matched-mask-sources.tar.gz'
    tree=out/'s3-matched-mask-tree';tree.mkdir()
    with tarfile.open(ROOT/'docs/data/solver-control-s3/sources.tar.gz') as a:a.extractall(tree,filter='data')
    for name in ['StreetCanyon.cpp','StreetCanyonModified.cpp']:
        shutil.copyfile(study/'tree/src/qes_core/winds'/name,tree/'src/qes_core/winds'/name)
    with tarfile.open(baseline,'w:gz') as a:
        for f in sorted(tree.rglob('*')):
            if f.is_file():a.add(f,arcname=f.relative_to(tree).as_posix(),recursive=False)
    shutil.copyfile(archive,out/'candidate-sources.tar.gz')
    shutil.copyfile(Path(__file__),out/'complete_solver_s5.py')
    for name in CASES:
        shutil.copyfile(study/f'cases/{name}.json',out/f'{name}.json')
    context=campaign.build_context();cache=ROOT/'build/urban-benchmark-cache'
    with campaign.campaign_lock(cache):
        builds={};decisions={}
        for label,src in [('candidate',out/'candidate-sources.tar.gz'),('s3_matched_mask',baseline)]:
            builds[label],decisions[label]=campaign.cached_build(src,'openmp',cache,context,label=label)
            # A second verified lookup explicitly exercises safe reuse before measurements.
            again,decision=campaign.cached_build(src,'openmp',cache,context,label=label)
            if again!=builds[label] or not decision['reused']:raise ValueError('Verified build reuse failed')
    write(out/'builds.json',dict(builds=builds,decisions=decisions,context=context))
    write(out/'plan.json',dict(stage='S5a',candidate_sha256=digest(out/'candidate-sources.tar.gz'),
        s3_matched_mask_sha256=digest(baseline),
        attribution='S3 and S5c share the exact two corrected canyon source files; timing changes are not conflated with geometry-mask correction.',
        screen=dict(cadences=[25,50,100],iterations=500,repetitions=1,workers=6,
                    selection='Smallest cadence whose API time on each case is within 3% of that case best. If none, use cadence minimizing maximum per-case ratio to best; tie favors smaller cadence.'),
        confirmation=dict(iterations=2000,repetitions=3,workers=18,variants=['disabled','bounded','s3_matched_mask']),
        threads=dict(teams=[1,2,4,8],iterations=500,workers=8),
        resources=dict(seconds=[.25,.5,1,2,5,1e-9],iteration_cap=100000,workers=12),
        same_work_replay=dict(seconds=.5,workers=2),max_workers=46,
        worker_seconds=30,shard_workers=6,shard_seconds=180,
        monitor='Both heights 1.5/1.75m, all 16 fixed receptors at each height, ROI planes, current/previous hotspots, short/long spans 1/2, bounded 16-summary history; no global monitor mass. Public defaults unchanged.',
        targets=dict(disabled_api_regression_vs_s3=.05,monitor_api_overhead=.10),
        quality='Always not_assessed in bounded mode; budgets are cooperative native solve time including initialization/RHS/monitor, excluding preparation/finalization/transfer. Not an API wall-time guarantee.'))


def worker(out,request):
    from dtcc_qes import wind,_qes
    import dtcc_qes
    import benchmark_urban_wind as urban
    import urban_wind_cases as cases
    builds=json.loads((out/'builds.json').read_text())['builds'];label=request.get('build','candidate');package=Path(builds[label]['package'])
    if any(not Path(m.__file__).resolve().is_relative_to(package) for m in (dtcc_qes,wind,_qes)):raise ValueError('Wrong isolated package')
    actual=_qes._urban_benchmark_actual_threads()
    if actual!=request['threads']:raise ValueError('Wrong actual team')
    spec=json.loads((out/f"{request['case']}.json").read_text());city=cases.city(spec)
    # Small warmup outside API clock, matching the public urban campaigns.
    from dtcc_core.model import City
    wind.run(City(), bounds=(0,0,0,20,20,20), resolution=2, solver=wind.Solver(max_iterations=2), speed=5, direction=270)
    opts=urban.frozen_options(spec,wind);opts.update(solver=wind.Solver(max_iterations=request['iterations']))
    if request['mode']=='bounded':
        monitor=wind.MonitorSpec(tuple(spec['roi']),heights=(1.5,1.75),history_limit=16,
            receptors=tuple(wind.Receptor(f'r{i}-h{h}',x,y,h) for h in (1.5,1.75) for i,(x,y) in enumerate(spec['receptors'])))
        opts['solver']=replace(opts['solver'],max_solve_seconds=request.get('seconds',20),monitor=monitor,checkpoint_interval=request['cadence'])
    started=time.perf_counter();cpu_started=time.process_time()
    try:
        value=wind.run(city, **opts, speed=5, direction=225)
    except RuntimeError as error:
        if not hasattr(error,'record'):raise
        write(out/f"{request['id']}.json",dict(status='zero_work',request=request,actual_threads=actual,
            api_seconds=time.perf_counter()-started,control=error.record));return
    api=time.perf_counter()-started
    control=value.solver['record']
    if control and control['accuracy_status']!='not_assessed':raise ValueError('Bounded output claims accuracy')
    hashes={name:hashlib.sha256(memoryview(getattr(value,name)).cast('B')).hexdigest() for name in ['velocity','cell_flags','x','y','z','z_faces']}
    arrays={};points=[]
    for n,h in enumerate((1.5,1.75)):
        plane=value.sample(h,method='linear');r=spec['roi'];ix=(plane.x>=r[0])&(plane.x<r[1]);iy=(plane.y>=r[2])&(plane.y<r[3])
        arrays[f'velocity{n}']=plane.velocity[iy][:,ix];arrays[f'valid{n}']=plane.valid[iy][:,ix]
        points.append([urban.receptor(plane,x,y) for x,y in spec['receptors']])
    np.savez_compressed(out/f"{request['id']}.npz",**arrays)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    write(out/f"{request['id']}.json",dict(status='completed',request=request,actual_threads=actual,api_seconds=api,pipeline_cpu_seconds=time.process_time()-cpu_started,
        pipeline_seconds=time.perf_counter()-started,peak_rss_bytes=rss,diagnostics=asdict(value.diagnostics),
        control=control,field_sha256=hashes,receptors=points,native_build=value.metadata['versions']['native_build']))


def execute(out,phase,requests):
    builds=json.loads((out/'builds.json').read_text())['builds']
    for i,r in enumerate(requests):r.update(id=f'{phase}-{i:02d}',shard=i//6)
    shutil.copyfile(Path(__file__),out/f'{phase}-driver.py')
    write(out/f'{phase}-protocol.json',dict(requests=requests,worker_seconds=30,shard_seconds=180,source_driver_sha256=digest(Path(__file__))))
    rows=[];shard=None;started=0
    for r in requests:
        if r['shard']!=shard:shard=r['shard'];started=time.monotonic()
        package=builds[r.get('build','candidate')]['package'];remaining=180-(time.monotonic()-started)
        print(r['id'],r['case'],r['mode'],r['threads'],r.get('seconds','fixed'),flush=True)
        if remaining<=0:rows.append(dict(status='shard_timeout',request=r));continue
        try:
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--output',str(out),'--worker',json.dumps(r)],
                env=os.environ|{'PYTHONPATH':package,'OMP_NUM_THREADS':str(r['threads']),'OMP_DYNAMIC':'FALSE'},
                capture_output=True,text=True,timeout=min(30,remaining))
            (out/f"{r['id']}.log").write_text(result.stdout+result.stderr);result.check_returncode()
            rows.append(json.loads((out/f"{r['id']}.json").read_text()))
        except subprocess.SubprocessError as e:rows.append(dict(status='failed',request=r,error=str(e)))
    write(out/f'{phase}-results.json',dict(rows=rows))
    if any(r['status'] not in ('completed','zero_work') for r in rows):raise RuntimeError(f'{phase} has failed workers; results preserved')
    return rows


def screen(out):
    rows=execute(out,'screen',[dict(case=c,mode='bounded',cadence=k,iterations=500,threads=4) for c in CASES for k in [25,50,100]])
    ratios={k:[] for k in [25,50,100]}
    for c in CASES:
        group=[r for r in rows if r['request']['case']==c];best=min(r['api_seconds'] for r in group)
        for r in group:ratios[r['request']['cadence']].append(r['api_seconds']/best)
    choices=[k for k,v in ratios.items() if max(v)<=1.03]
    chosen=min(choices) if choices else min(ratios,key=lambda k:(max(ratios[k]),k))
    write(out/'selection.json',dict(cadence=chosen,ratios_to_case_best=ratios,screen_workers=6))


def confirm(out):
    cadence=json.loads((out/'selection.json').read_text())['cadence']
    execute(out,'confirm',[dict(case=c,mode='bounded' if mode=='bounded' else 'disabled',
        build='s3_matched_mask' if mode=='s3_matched_mask' else 'candidate',cadence=cadence,iterations=2000,threads=4,repeat=rep)
        for c in CASES for rep in range(3) for mode in ['disabled','bounded','s3_matched_mask']])


def resources(out):
    cadence=json.loads((out/'selection.json').read_text())['cadence']
    execute(out,'threads',[dict(case=CASES[1],mode=mode,cadence=cadence,iterations=500,threads=t)
            for t in [1,2,4,8] for mode in ['disabled','bounded']])
    rows=execute(out,'budgets',[dict(case=c,mode='bounded',cadence=cadence,iterations=100000,threads=4,seconds=t)
            for c in CASES for t in [.25,.5,1,2,5,1e-9]])
    execute(out,'replay',[dict(case=r['request']['case'],mode='disabled',cadence=cadence,
                iterations=r['diagnostics']['iterations'],threads=4,paired_id=r['request']['id'])
            for r in rows if r['request']['seconds']==.5 and r['status']=='completed'])
    summarize(out)


def summarize(out):
    confirm=json.loads((out/'confirm-results.json').read_text())['rows'];groups=[]
    for c in CASES:
        modes={mode:[r for r in confirm if r['request']['case']==c and (r['request'].get('build')=='s3_matched_mask' if mode=='s3_matched_mask' else r['request']['mode']==mode and r['request'].get('build')=='candidate')] for mode in ['disabled','bounded','s3_matched_mask']}
        med={mode:float(np.median([r['api_seconds'] for r in rows])) for mode,rows in modes.items()}
        allrows=sum(modes.values(),[])
        parity=len({tuple(sorted(r['field_sha256'].items())) for r in allrows})==1
        groups.append(dict(case=c,median_api_seconds=med,monitor_overhead=med['bounded']/med['disabled']-1,
            disabled_regression_vs_s3=med['disabled']/med['s3_matched_mask']-1,full_fields_equal=parity,
            peak_rss_bytes={mode:[r['peak_rss_bytes'] for r in rs] for mode,rs in modes.items()}))
    budgets=json.loads((out/'budgets-results.json').read_text())['rows'];replays=json.loads((out/'replay-results.json').read_text())['rows']
    deadlines=[]
    for r in budgets:
        control=r['control'];request=r['request'];zero=r['status']=='zero_work';record=dict(case=request['case'],seconds=request['seconds'],status=r['status'],iterations=control['iterations'],
            termination_reason=control['termination_reason'],accuracy_status=control['accuracy_status'],phase=control['phase'],api_seconds=r['api_seconds'],timings=control['timings'])
        if zero:
            if control['iterations']!=0:raise ValueError('Zero-work exception counted sweeps')
        elif control['iterations']!=r['diagnostics']['iterations']:raise ValueError('Inconsistent whole-sweep accounting')
        if control['accuracy_status']!='not_assessed':raise ValueError('Unexpected acceptance')
        if request['seconds']==.5 and not zero:
            paired=next(p for p in replays if p['request']['paired_id']==request['id'])
            record['completed_work_replay_equal']=paired['field_sha256']==r['field_sha256']
            if not record['completed_work_replay_equal']:raise ValueError('Deadline field differs from same-work complete iterate')
        deadlines.append(record)
    threads=json.loads((out/'threads-results.json').read_text())['rows']
    thread_parity=len({tuple(sorted(r['field_sha256'].items())) for r in threads})==1
    summary=dict(cadence=json.loads((out/'selection.json').read_text())['cadence'],groups=groups,deadlines=deadlines,
        thread_fields_equal=thread_parity,thread_actual_teams=sorted({r['actual_threads'] for r in threads}),
        monitor_target_met=all(r['monitor_overhead']<=.10 for r in groups),disabled_target_met=all(r['disabled_regression_vs_s3']<=.05 for r in groups))
    if not thread_parity or not all(r['full_fields_equal'] for r in groups):raise ValueError('Matched-work field parity failed')
    write(out/'summary.json',summary);print(json.dumps(summary,indent=2))


def disposition(out):
    # One explicitly bounded follow-up, preserving all original timing rows.
    requests=[]
    for rep in range(3):
        order=['s3_matched_mask','candidate'] if rep%2==0 else ['candidate','s3_matched_mask']
        for build in order:requests.append(dict(case=CASES[1],mode='disabled',build=build,cadence=100,iterations=2000,threads=4,repeat=rep))
    write(out/'disposition-plan.json',dict(reason='Original matched-work confirmation missed 5% target and showed negative monitor cost on downtown; single finite reverse-order check with CPU accounting.',workers=6,worker_seconds=30,shard_seconds=180,automatic_retries=False))
    rows=execute(out,'disposition',requests)
    med={build:float(np.median([r['api_seconds'] for r in rows if r['request']['build']==build])) for build in ['candidate','s3_matched_mask']}
    write(out/'disposition.json',dict(median_api_seconds=med,disabled_regression_vs_s3=med['candidate']/med['s3_matched_mask']-1,
        rows=rows,interpretation='Original confirmation is retained. This selected follow-up does not replace its result or establish a universal regression bound.'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--worker');p.add_argument('--phase',choices=['prepare','screen','confirm','resources','summarize','disposition'],default='prepare')
    a=p.parse_args();out=a.output.resolve()
    if a.worker:worker(out,json.loads(a.worker));return
    {'prepare':prepare,'screen':screen,'confirm':confirm,'resources':resources,'summarize':summarize,'disposition':disposition}[a.phase](out)

if __name__=='__main__':main()
