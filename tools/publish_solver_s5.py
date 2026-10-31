"""Publish/replay S5 evidence as deduplicated, hash-checked original file blobs.

Original campaigns and S0-S5b evidence are read-only. This archive preserves
full original protocols/outcomes/logs and compact planes, without duplicating
identical data for baseline/disabled/bounded repetitions.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import struct
import zipfile
import numpy as np
from run_solver_numerics import digest,write,compare_samples,qualify
ROOT=Path(__file__).resolve().parents[1]
CAMPAIGNS=['20261030T113311Z-44150a27','20261030T113701Z-fb78576f','20261030T114345Z-c5e93cfb','core-2000-20261030-clean','controls-2000-20261030']


def publish(out):
    out.mkdir(parents=True,exist_ok=False);(out/'blobs').mkdir();index={}
    def blob(data):
        sha=hashlib.sha256(data).hexdigest();path=out/f'blobs/{sha}.gz'
        if not path.exists():path.write_bytes(gzip.compress(data,compresslevel=6,mtime=0))
        return path.relative_to(out).as_posix()
    def add(logical,path):
        data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
        record=dict(sha256=sha,bytes=len(data))
        if logical.startswith('parity/') and path.suffix=='.npz':
            # Separate original ZIP headers from already-compressed array
            # payloads. Equal fields share payloads even when ZIP timestamps
            # differ. Concatenation reproduces the ORIGINAL archive exactly.
            boundaries={0,len(data)}
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    fname,extra=struct.unpack_from('<HH',data,info.header_offset+26)
                    start=info.header_offset+30+fname+extra
                    boundaries.update([info.header_offset,start,start+info.compress_size])
            points=sorted(boundaries)
            record['segments']=[blob(data[a:b]) for a,b in zip(points,points[1:]) if b>a]
        else:record['blob']=blob(data)
        index[logical]=record
    def folder(logical,path):
        for p in sorted(path.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':add(logical+'/'+p.relative_to(path).as_posix(),p)
    for name in CAMPAIGNS+['core-2000-20261030']:
        p=ROOT/'build/urban-benchmarks'/name;folder('campaigns/'+name,p)
    folder('tolerance',ROOT/'build/legacy-tolerance-investigation-20261030')
    folder('s5b',ROOT/'docs/data/solver-control-s5b')
    # Publication includes finite study inputs/results, not native build trees.
    for label,path,skip in [
        ('s5c',ROOT/'build/solver-control-s5c/study',{'tree','native'}),
        ('performance',ROOT/'build/solver-control-s5/performance',{'s3-matched-mask-tree'}),
        ('parity',ROOT/'build/solver-control-s5c/parity',{'baseline-tree','candidate-tree','baseline-openmp-build','baseline-serial-build','candidate-openmp-build','candidate-serial-build','baseline-openmp-package','baseline-serial-package','candidate-openmp-package','candidate-serial-package'})]:
        for p in sorted(path.rglob('*')):
            rel=p.relative_to(path)
            if p.is_file() and rel.parts[0] not in skip and '__pycache__' not in rel.parts and p.suffix!='.pyc':add(label+'/'+rel.as_posix(),p)
    for stage in ['s1a','s3','s4']:
        add(f'sources/{stage}.tar.gz',ROOT/f'docs/data/solver-control-{stage}/sources.tar.gz')
    # Preserve the actual cache/toolchain/package identity behind every campaign.
    build_records=[]
    for name in CAMPAIGNS:
        doc=json.loads((ROOT/f'build/urban-benchmarks/{name}/builds.json').read_text())
        for label,value in doc['builds'].items():build_records.append((name+'/'+label,value))
    doc=json.loads((ROOT/'build/solver-control-s5/performance/builds.json').read_text())
    for label,value in doc['builds'].items():build_records.append(('performance/'+label,value))
    for label,value in build_records:
        archive=Path(value['instrumented_archive']);generation=archive.parent
        if digest(archive)!=value['instrumented_sources']['sha256']:raise ValueError('Changed measured instrumented archive')
        for rel in ['probe-sources.tar.gz','build.log','native/CMakeCache.txt']:
            add('build-records/'+label+'/'+rel,generation/rel)
        current=generation.parent/'current.json'
        if current.exists():add('build-records/'+label+'/cache-attestation.json',current)
        package=Path(value['package'])
        # Validate every recorded package member before preserving its identity.
        for filename,sha in value['files'].items():
            if digest(package/filename)!=sha:raise ValueError('Changed benchmark package: '+filename)
    # Preserve even a bytecode member referenced by the original study manifest.
    raw=ROOT/'build/solver-control-s5c/study'
    for rel in json.loads((raw/'manifest.json').read_text())['files']:
        if 's5c/'+rel not in index:add('s5c/'+rel,raw/rel)
    folder('validation',ROOT/'build/solver-control-s5/validation')
    for name in ['current-default-smoke','current-default-reuse']:
        folder('integration/'+name,ROOT/'build/solver-control-s5'/name)
    for filename in ['complete_solver_s5.py','publish_solver_s5.py','check_condition_mask_parity.py','run_solver_numerics.py','analyze_solver_numerics.py','run_urban_benchmarks.py','benchmark_urban_wind.py','compare_native_builds.py','profile_solver_baseline.py','profile_solver_s2.py']:
        add('implementation/tools/'+filename,ROOT/'tools'/filename)
    for filename in ['check_condition_mask.cpp']:
        add('implementation/tests/native/'+filename,ROOT/'tests/native'/filename)
    write(out/'index.json',dict(schema='solver-s5-original-files-v1',files=index,campaigns=CAMPAIGNS,
        excluded_campaign='core-2000-20261030',scope='Original bytes retained; absolute paths describe original machines. Full-volume fingerprints are records; only compact planes can be re-evaluated without rerunning native solves.'))
    shutil.copyfile(Path(__file__),out/'audit.py')
    # Include dependency-free replay helpers as standalone audit inputs.
    shutil.copyfile(ROOT/'tools/run_solver_numerics.py',out/'run_solver_numerics.py')
    shutil.copyfile(ROOT/'tools/analyze_solver_numerics.py',out/'analyze_solver_numerics.py')
    write(out/'manifest.json',dict(stage='S5',index_sha256=digest(out/'index.json'),
        files={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'},
        original_files=len(index),unique_blobs=len(list((out/'blobs').iterdir()))))
    result=audit(out)
    write(out/'summary.json',result)
    current_comparison(out)
    seal(out)


class Evidence:
    def __init__(self,out):
        self.out=out;self.index=json.loads((out/'index.json').read_text())['files']
    @lru_cache(maxsize=16)
    def read(self,name):
        r=self.index[name]
        data=(b''.join(gzip.decompress((self.out/p).read_bytes()) for p in r['segments']) if 'segments' in r else gzip.decompress((self.out/r['blob']).read_bytes()))
        if len(data)!=r['bytes'] or hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('Changed original bytes: '+name)
        return data
    def json(self,name):return json.loads(self.read(name))


def historical(e):
    campaigns=[];workers=0;pairs=0;converged=0
    for name in CAMPAIGNS:
        prefix='campaigns/'+name;protocol=e.json(prefix+'/fixtures/protocol.json');doc=e.json(prefix+'/campaign.json')
        if doc['status']!='completed':raise ValueError('Historical campaign incomplete')
        driver=e.read('validation/driver-versions/'+doc['runner_sha256']+'.py')
        if hashlib.sha256(driver).hexdigest()!=doc['runner_sha256']:raise ValueError('Original campaign driver source unavailable')
        for rel,sha in protocol['files'].items():
            if hashlib.sha256(e.read(prefix+'/fixtures/'+rel)).hexdigest()!=sha:raise ValueError('Fixture/source changed')
        rows=[];comparisons=[]
        for shard in doc['shards']:
            folder=prefix+f"/run-{shard['shard']:02d}";manifest=e.json(folder+'/manifest.json')
            for rel,sha in manifest['files'].items():
                if hashlib.sha256(e.read(folder+'/'+rel)).hexdigest()!=sha:raise ValueError('Original run manifest mismatch')
            run=e.json(folder+'/summary.json')
            if not run['completed']:raise ValueError('Original shard incomplete')
            expected=e.json(folder+'/comparisons.json')['comparisons'];actual=[]
            groups={}
            for r in run['results']:
                q=r['request'];groups.setdefault((q['case'],q['direction'],q['repeat']),{})[q['variant']]=r
                if r['status']!='completed' or r['actual_threads']!=4 or r['diagnostics']['iterations']!=q['iterations']:raise ValueError('Wrong historical work/team')
                converged+=bool(r['diagnostics']['converged'])
            for key,variants in groups.items():
                baseline=variants['baseline']
                for variant in ['disabled','bounded']:
                    current=variants[variant];stored=next(c for c in expected if (c['case'],c['direction'],c['repeat'],c['variant'])==(*key,variant))
                    if not (stored['same_grid'] and stored['same_completed_work'] and stored['field_bitwise_equal']):raise ValueError('Historical parity was false')
                    if current['field_sha256']!=baseline['field_sha256'] or current['grid_sha256']!=baseline['grid_sha256']:raise ValueError('Field/grid identity mismatch')
                    if stored['api_ratio']!=current['timing']['api_seconds']/baseline['timing']['api_seconds']:raise ValueError('Wrong paired ratio')
                    a=np.load(io.BytesIO(e.read(folder+'/'+baseline['request']['id']+'.npz')))
                    b=np.load(io.BytesIO(e.read(folder+'/'+current['request']['id']+'.npz')))
                    with a,b:
                        for k in a.files:
                            if a[k].dtype!=b[k].dtype or a[k].shape!=b[k].shape or a[k].tobytes()!=b[k].tobytes():raise ValueError('Stored planes differ')
                        for n,h in enumerate(stored['planes']):
                            if int(np.count_nonzero(a[f'valid{n}']))!=h['common_valid'] or h['validity_changes']!=0 or h['vector_difference_over_uref_p95']!=0 or h['vector_difference_over_uref_max']!=0:raise ValueError('Plane comparison replay failed')
                    actual.append(stored)
            rows+=run['results'];comparisons+=actual
        if len(rows)!=len(protocol['rows']):raise ValueError('Incomplete historical campaign rows')
        aggregate=e.json(prefix+'/results.json')
        # Independently replay ratios of medians (distinct from paired ratios).
        cost=[]
        for case,direction in sorted({(r['request']['case'],r['request']['direction']) for r in rows}):
            med={v:float(np.median([r['timing']['api_seconds'] for r in rows if (r['request']['case'],r['request']['direction'],r['request']['variant'])==(case,direction,v)])) for v in ['baseline','disabled','bounded']}
            for variant in med:
                saved=next(g for g in aggregate['medians'] if (g['case'],g['direction'],g['variant'])==(case,direction,variant))
                if saved['api_median_seconds']!=med[variant]:raise ValueError('Median replay failed')
            base_rss=float(np.median([r['peak_rss_bytes'] for r in rows if (r['request']['case'],r['request']['direction'],r['request']['variant'])==(case,direction,'baseline')]))
            off_rss=float(np.median([r['peak_rss_bytes'] for r in rows if (r['request']['case'],r['request']['direction'],r['request']['variant'])==(case,direction,'disabled')]))
            cost.append(dict(case=case,direction=direction,median_api_seconds=med,disabled_speedup=med['baseline']/med['disabled'],monitor_overhead=med['bounded']/med['disabled']-1,rss_reduction=1-off_rss/base_rss,
                median_paired_ratios={v:float(np.median([c['api_ratio'] for c in comparisons if (c['case'],c['direction'],c['variant'])==(case,direction,v)])) for v in ['disabled','bounded']}))
        campaigns.append(dict(campaign=name,workers=len(rows),comparisons=len(comparisons),costs=cost));workers+=len(rows);pairs+=len(comparisons)
    if (workers,pairs,converged)!=(324,216,0):raise ValueError('Historical campaign totals changed')
    excluded=e.json('campaigns/core-2000-20261030/campaign.json')
    if excluded['status']=='completed' or not excluded.get('exclusion_reason'):raise ValueError('Interrupted contaminated attempt not marked excluded')
    return dict(campaigns=campaigns,workers=workers,comparisons=pairs,legacy_converged=converged,excluded_attempt_preserved=True)


def performance(e):
    summary=e.json('performance/summary.json');confirm=e.json('performance/confirm-results.json')['rows']
    for group in summary['groups']:
        c=group['case'];off=[r for r in confirm if r['request']['case']==c and r['request']['mode']=='disabled' and r['request']['build']=='candidate']
        on=[r for r in confirm if r['request']['case']==c and r['request']['mode']=='bounded']
        old=[r for r in confirm if r['request']['case']==c and r['request']['build']=='s3_matched_mask']
        med={k:float(np.median([r['api_seconds'] for r in rs])) for k,rs in [('disabled',off),('bounded',on),('s3_matched_mask',old)]}
        if med!=group['median_api_seconds'] or med['bounded']/med['disabled']-1!=group['monitor_overhead'] or med['disabled']/med['s3_matched_mask']-1!=group['disabled_regression_vs_s3']:raise ValueError('S5a cost replay failed')
        if len({tuple(sorted(r['field_sha256'].items())) for r in off+on+old})!=1:raise ValueError('Matched-work field parity failed')
    for r in confirm:
        if r['request']['mode']!='bounded':continue
        control=r['control']
        if len(control['checkpoint_history'])!=16 or not control['history_truncated'] or control['checkpoint_count']!=21:raise ValueError('Monitoring history coverage changed')
        for frame in control['checkpoint_history']:
            if len(frame['heights'])!=2 or len(frame['receptors'])!=32 or not frame['required_receptors_valid']:raise ValueError('Monitoring/receptor coverage was reduced')
    budgets=e.json('performance/budgets-results.json')['rows'];replays=e.json('performance/replay-results.json')['rows']
    for r in budgets:
        control=r['control']
        if control['accuracy_status']!='not_assessed':raise ValueError('Bounded result advertised acceptance')
        if r['status']=='zero_work' and control['iterations']!=0:raise ValueError('Zero work counter failed')
        if r['status']=='completed' and r['request']['seconds']==.5:
            p=next(x for x in replays if x['request']['paired_id']==r['request']['id'])
            if p['field_sha256']!=r['field_sha256']:raise ValueError('Complete-sweep replay failed')
    threads=e.json('performance/threads-results.json')['rows']
    if sorted({r['actual_threads'] for r in threads})!=[1,2,4,8] or len({tuple(sorted(r['field_sha256'].items())) for r in threads})!=1:raise ValueError('Thread parity failed')
    disposition=e.json('validation/performance-disposition.json')
    if not summary['disabled_target_met'] and 'NOT met' not in disposition['target_disposition']:raise ValueError('Missed performance target lacks an honest disposition')
    return summary


def numerics(e):
    corrected=e.json('s5c/results.json');old=e.json('s5b/results.json');records=[]
    for r in corrected['rows']:
        before=next(a for a in old['rows'] if a['request']['id']==r['request']['id'])
        if r['status']!='completed':raise ValueError('Incomplete correction study')
        for frame in r['result']['checkpoints']:
            if frame.get('relabeled_solid_cells',0)!=0:raise ValueError('Solid relabeling persists')
        if r['request']['purpose']=='historical_hotspot':
            records.append(dict(case=r['request']['case'],direction=r['request']['direction'],
                before=before['result']['checkpoints'][-1]['mass'],after=r['result']['checkpoints'][-1]['mass']))
    if len(records)!=4 or not all(r['accepted'] for r in corrected['references']):raise ValueError('Numerical qualification incomplete')
    parity=e.json('parity/parity.json')
    if not parity['passed'] or any(p['differences'] for p in parity['parity']):raise ValueError('Correction compatibility gate failed')
    for r in parity['revisions']:
        allowed=set(r['guard_hit_cases'])
        if any(c['case'] not in allowed for c in r['changed']) or len(r['unchanged'])+len(r['changed'])!=429:raise ValueError('Unexplained correction changes')
    targeted=e.json('parity/targeted-parity.json')
    if not targeted['passed'] or targeted['changed_cases']!=4 or targeted['unchanged_cases']!=8:raise ValueError('Targeted change set failed')
    return dict(hotspot_correction=records,qualified_small_references=corrected['references'],targeted_changed_cases=targeted['changed_cases'],targeted_unchanged_cases=targeted['unchanged_cases'],
                changed_cases=parity['changed_cases'],unchanged_cases=parity['unchanged_cases'],large_urban_accuracy='unqualified',top_boundary='unchanged prescribed-face convention')


def replay_references(e,prefix):
    doc=e.json(prefix+'/results.json');curves=e.json(prefix+'/cost-error-curves.json')['curves']
    for ref in doc['references']:
        rows=sorted([r for r in doc['rows'] if r['request']['case']==ref['case']],key=lambda r:r['request']['iterations'])
        if [r['request']['iterations'] for r in rows]!=[500,1000,2000]:raise ValueError('Wrong independent reference budgets')
        if len({tuple(r['result']['initial_hashes']) for r in rows})!=1:raise ValueError('Reference zero starts differ')
        finals=[]
        for r in rows:
            with np.load(io.BytesIO(e.read(prefix+'/'+r['request']['id']+'.npz'))) as saved:finals.append(saved['samples'][-1])
        pairs=[compare_samples(a,b,rows[0]['result']['plane_points']) for a,b in zip(finals,finals[1:])]
        checks=[dict(maximum=r['result']['checkpoints'][-1]['mass']['maximum']*23.7/5,
                     rms=r['result']['checkpoints'][-1]['mass']['rms']*23.7/5,
                     passed=r['result']['checkpoints'][-1]['mass']['maximum']*23.7/5<=1e-3 and r['result']['checkpoints'][-1]['mass']['rms']*23.7/5<=1e-4) for r in rows]
        accepted=all(c['passed'] for c in checks) and all(h['p95'] is not None and h['maximum']<=1e-3 and h['p95']<=5e-4 and h['validity_changes']==0 and h['required_valid'] for pair in pairs for h in pair)
        if pairs!=ref['pairs'] or checks!=ref['mass_checks'] or accepted!=ref['accepted']:raise ValueError('Reference gate replay changed')
        longest=rows[-1]
        with np.load(io.BytesIO(e.read(prefix+'/'+longest['request']['id']+'.npz'))) as saved:frames=saved['samples']
        entries=[c for c in curves if c['case']==ref['case']]
        if len(entries)!=len(frames) or len(frames)!=81:raise ValueError('Truncated reference replay')
        for entry,frame,checkpoint in zip(entries,frames,longest['result']['checkpoints']):
            if entry['heights']!=compare_samples(frame,frames[-1],longest['result']['plane_points']) or entry['mass']!=checkpoint['mass'] or entry['residual']!=checkpoint['residual']:raise ValueError('Cost/error replay changed')
    return dict(references=len(doc['references']),history_frames=162)


def replay_parity(e):
    comparisons=0
    def unequal(a,b,backend=False):
        if set(a.files)!=set(b.files):raise ValueError('Parity key set differs')
        differences=[]
        for key in a.files:
            x,y=a[key],b[key]
            if backend and key.endswith('/metadata/versions/native_build/scalars'):
                x,y=json.loads(str(x)),json.loads(str(y));x.pop('openmp_enabled',None);y.pop('openmp_enabled',None)
                x,y=np.array(json.dumps(x,sort_keys=True)),np.array(json.dumps(y,sort_keys=True))
            if backend and key.endswith('/metadata/model/scalars'):
                x,y=json.loads(str(x)),json.loads(str(y));x.pop('backend',None);y.pop('backend',None)
                x,y=np.array(json.dumps(x,sort_keys=True)),np.array(json.dumps(y,sort_keys=True))
            if x.dtype!=y.dtype or x.shape!=y.shape or x.tobytes()!=y.tobytes():differences.append(key)
        return differences
    for prefix in ['', 'targeted-']:
        report=e.json('parity/'+prefix+'parity.json')
        for revision in report['revisions']:
            backend=revision['backend'];a_path=f'parity/{prefix}baseline-{backend}-1.npz';b_path=f'parity/{prefix}candidate-{backend}-1.npz'
            with np.load(io.BytesIO(e.read(a_path))) as a,np.load(io.BytesIO(e.read(b_path))) as b:
                differences=unequal(a,b)
            explained=[key for row in revision['changed'] for key in row['differences']]
            if sorted(differences)!=sorted(explained):raise ValueError('Revision differences not exactly enumerated')
        for team in [2,4,8]:
            with np.load(io.BytesIO(e.read(f'parity/{prefix}candidate-openmp-1.npz'))) as a,np.load(io.BytesIO(e.read(f'parity/{prefix}candidate-openmp-{team}.npz'))) as b:
                if unequal(a,b):raise ValueError('Team parity replay failed')
            comparisons+=1
        for team in [1,2,4,8]:
            with np.load(io.BytesIO(e.read(f'parity/{prefix}candidate-serial-1.npz'))) as a,np.load(io.BytesIO(e.read(f'parity/{prefix}candidate-openmp-{team}.npz'))) as b:
                if unequal(a,b,True):raise ValueError('Backend parity replay failed')
            comparisons+=1
    return dict(strict_team_backend_comparisons=comparisons,revision_difference_lists_replayed=True)


def audit(out):
    manifest=json.loads((out/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if digest(out/name)!=sha:raise ValueError('Changed evidence blob/file: '+name)
    e=Evidence(out)
    for name in e.index:e.read(name)
    references={prefix:replay_references(e,prefix) for prefix in ['s5b','s5c']}
    for prefix in ['s5b','s5c']:
        original=e.json(prefix+'/manifest.json')
        for rel,sha in original['files'].items():
            if hashlib.sha256(e.read(prefix+'/'+rel)).hexdigest()!=sha:raise ValueError('Original numerical-study manifest changed')
        index=e.json(prefix+'/source-index.json')
        with tarfile.open(fileobj=io.BytesIO(e.read(prefix+'/sources.tar.gz'))) as archive:
            for name,sha in index.items():
                if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=sha:raise ValueError('Source archive content changed')
    result=dict(passed=True,history=historical(e),performance=performance(e),numerics=numerics(e),references=references,parity=replay_parity(e),files=len(e.index))
    if (out/'current-comparison.json').exists():
        identities=json.loads((out/'current-comparison.json').read_text())
        for name,sha in identities['files'].items():
            if digest(out/name)!=sha:raise ValueError('Current comparison archive changed')
    smoke=[]
    for name in ['current-default-smoke','current-default-reuse']:
        prefix='integration/'+name
        if prefix+'/campaign.json' not in e.index:continue
        record=e.json(prefix+'/campaign.json');results=e.json(prefix+'/results.json')
        if record['status']!='completed' or results['rows']!=12:raise ValueError('Current default integration incomplete')
        count=0
        for shard in record['shards']:
            comparisons=e.json(prefix+f"/run-{shard['shard']:02d}/comparisons.json")['comparisons']
            if any(not c['field_bitwise_equal'] or not c['same_grid'] or not c['same_completed_work'] for c in comparisons):raise ValueError('Current default integration parity failed')
            count+=len(comparisons)
        if count!=8:raise ValueError('Current default comparison count changed')
        reused={label:value['reused'] for label,value in record['build_cache'].items()}
        if name.endswith('reuse') and not all(reused.values()):raise ValueError('Current builds were not reused')
        smoke.append(dict(campaign=name,workers=12,comparisons=8,builds_reused=reused))
    result['integration']=smoke
    result['completion']=dict(stage='S5',complete=True,next='S6',
        disabled_performance_review_target='missed; explicit documented disposition',large_urban_accuracy='unqualified',python_suite='12 inherited dataset failures remain visible')
    if (out/'summary.json').exists() and json.loads((out/'summary.json').read_text())!=result:raise ValueError('Completion summary replay changed')
    print(json.dumps(dict(passed=True,files=len(e.index),historical_workers=result['history']['workers'],historical_comparisons=result['history']['comparisons'],
        monitor_target_met=result['performance']['monitor_target_met'],disabled_target_met=result['performance']['disabled_target_met'],
        historical_unchanged=result['numerics']['unchanged_cases'],targeted_changed=result['numerics']['targeted_changed_cases'],
        reference_triples=4,strict_team_backend_checks=result['parity']['strict_team_backend_comparisons'],current_smoke_campaigns=len(smoke))))
    return result


def current_comparison(out):
    frozen=ROOT/'build/solver-control-s5/comparison-sources'
    if (frozen/'current-comparison.json').exists():
        for name in ['sources.tar.gz','s1a-matched-mask-sources.tar.gz','s3-matched-mask-sources.tar.gz','current-comparison.json']:shutil.copyfile(frozen/name,out/name)
        return
    study=ROOT/'build/solver-control-s5c/study'
    shutil.copyfile(study/'sources.tar.gz',out/'sources.tar.gz')
    shutil.copyfile(ROOT/'build/solver-control-s5/performance/s3-matched-mask-sources.tar.gz',out/'s3-matched-mask-sources.tar.gz')
    with tempfile.TemporaryDirectory() as tmp:
        tree=Path(tmp)
        with tarfile.open(ROOT/'docs/data/solver-control-s1a/sources.tar.gz') as archive:archive.extractall(tree,filter='data')
        for name in ['StreetCanyon.cpp','StreetCanyonModified.cpp']:
            shutil.copyfile(study/'tree/src/qes_core/winds'/name,tree/'src/qes_core/winds'/name)
        with tarfile.open(out/'s1a-matched-mask-sources.tar.gz','w:gz') as archive:
            for file in sorted(tree.rglob('*')):
                if file.is_file():archive.add(file,arcname=file.relative_to(tree).as_posix(),recursive=False)
    names=['sources.tar.gz','s1a-matched-mask-sources.tar.gz','s3-matched-mask-sources.tar.gz']
    write(out/'current-comparison.json',dict(candidate='S5c corrected mask, S5b pure diagnostics, S4 controls',
        baseline_policy='Both architecture and control baselines carry the exact same two canyon-mask corrections; original unmodified S1a/S3/S4 archives remain historical evidence.',files={n:digest(out/n) for n in names}))


def extend(out,inputs):
    """Add final validation/docs without rewriting any original artifact entry."""
    index=json.loads((out/'index.json').read_text())
    for name,path in inputs.items():
        data=Path(path).read_bytes();sha=hashlib.sha256(data).hexdigest()
        if name in index['files']:
            if index['files'][name]['sha256']!=sha:raise ValueError('Cannot rewrite original evidence: '+name)
            continue
        blob=out/f'blobs/{sha}.gz'
        if not blob.exists():blob.write_bytes(gzip.compress(data,compresslevel=6,mtime=0))
        index['files'][name]=dict(sha256=sha,bytes=len(data),blob=blob.relative_to(out).as_posix())
    write(out/'index.json',index)


def seal(out):
    write(out/'manifest.json',dict(stage='S5',index_sha256=digest(out/'index.json'),
        files={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts},
        original_files=len(json.loads((out/'index.json').read_text())['files']),unique_blobs=len(list((out/'blobs').iterdir()))))


def extract(out,prefix,destination):
    e=Evidence(out);destination.mkdir(parents=True,exist_ok=False);count=0
    for name in e.index:
        if not name.startswith(prefix.rstrip('/')+'/'):continue
        rel=Path(name[len(prefix.rstrip('/'))+1:])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe logical artifact path')
        target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(e.read(name));count+=1
    if not count:raise ValueError('No artifacts with the requested prefix')
    print(json.dumps(dict(extracted=count,destination=str(destination))))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--audit',action='store_true');p.add_argument('--extract');p.add_argument('--destination',type=Path);a=p.parse_args();out=(a.output or Path(__file__).parent).resolve()
    if a.extract:
        if not a.destination:p.error('--destination is required with --extract')
        extract(out,a.extract,a.destination.resolve())
    elif a.audit or (a.output is None and Path(__file__).name=='audit.py'):audit(out)
    else:publish(out)

if __name__=='__main__':main()
