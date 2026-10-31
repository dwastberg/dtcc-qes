"""Portable S8a audit: rederive parity, timing summaries and the reuse decision."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import tarfile

from benchmark_prepared_wind import comparable, worthwhile


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)


def summarize(primary):
    series={}
    for mode in ['legacy','adaptive']:
        for count in [4,8]:
            groups={kind:[read(primary/f'{mode}-{count}-{rep}-{kind}.json') for rep in range(3)] for kind in ['fresh','prototype']}
            expected=comparable(groups['fresh'][0]['records'])
            require(len(expected)==count,'Wrong series length')
            for kind,rows in groups.items():
                for r in rows:
                    require(r['mode']==mode and r['kind']==kind and r['count']==count,'Wrong worker identity')
                    require(r['counts']==dict(geometry=count if kind=='fresh' else 1,domain=count if kind=='fresh' else 1,
                        native_prepare=count if kind=='fresh' else 1,native_solve_and_transfer=count),'Wrong preparation/solve counts')
                    require(comparable(r['records'])==expected,f'Field/diagnostic/control parity: {mode}/{count}/{kind}')
                    require(0<r['elapsed_seconds']<30,'Worker exceeded bound')
            medians={k:statistics.median(r['elapsed_seconds'] for r in rows) for k,rows in groups.items()}
            series[f'{mode}-{count}']=dict(parity=True,median_seconds=medians,
                saving_seconds=medians['fresh']-medians['prototype'],saving_fraction=1-medians['prototype']/medians['fresh'],
                median_phases={k:{p:statistics.median(r['phases'][p] for r in rows) for p in rows[0]['phases']} for k,rows in groups.items()},
                peak_rss_bytes_range={k:[min(r['peak_rss_bytes'] for r in rows),max(r['peak_rss_bytes'] for r in rows)] for k,rows in groups.items()},
                iterations=[r['diagnostics']['iterations'] for r in expected],
                accepted=[None if r['control'] is None else r['control']['accepted'] for r in expected])
    return dict(worthwhile=worthwhile(series),decision='adopt' if worthwhile(series) else 'defer_public_api',series=series)


def audit(root):
    manifest=read(root/'manifest.json')
    for name,value in manifest['files'].items():require(sha(root/name)==value,f'Changed S8a evidence: {name}')
    for archive,index in manifest['sources'].items():
        with tarfile.open(root/archive) as a:
            for name,value in index.items():
                require(hashlib.sha256(a.extractfile(name).read()).hexdigest()==value,f'Changed S8a source member: {archive}/{name}')
    summary=summarize(root/'primary')
    require(summary==read(root/'summary.json'),'S8a summary does not match raw workers')
    workers=[read(p) for p in (root/'primary').glob('*-fresh.json')]+[read(p) for p in (root/'primary').glob('*-prototype.json')]
    require(len(workers)==24,'Wrong primary worker count')
    condition_solves=sum(len(r['records']) for r in workers)
    for directory in ['profile','memory']:
        paths=list((root/directory).glob('legacy-*.json' if directory=='profile' else '*-*-*.json'))
        require(len(paths)==(4 if directory=='profile' else 8),f'Wrong {directory} worker count')
        for path in paths:
            row=read(path)
            condition_solves+=len(row['records'])
            reference=read(root/f"primary/{row['mode']}-{row['count']}-0-fresh.json")
            require(comparable(row['records'])==comparable(reference['records']),f'{directory} field/diagnostic/control parity: {path.name}')
            if directory=='profile':
                counts=row['native_profile']['object_allocations']
                n=row['count'] if row['kind']=='fresh' else 1
                require(counts==dict(prepared_objects=n,operator_objects=n,float_workspace_objects=n),'Wrong native allocation counts')
                require(row['native_profile']['array_bytes']['operator']>0 and row['native_profile']['array_bytes']['workspace']>0,'Missing native storage accounting')
            else:
                require(row['allocation']['traced_peak_bytes']>0,'Missing allocation tracing')
                workers.append(row)
    require(len({r['native_module_sha256'] for r in workers})==1,'Primary/memory native binary changed')
    require(len({r['policy_revision'] for r in workers})==1,'Policy identity changed')
    require(condition_solves==216,'Wrong condition solve count')
    replay_workers=0
    replay=root/'reproduction/raw.json.gz'
    if replay.exists():
        rows=json.loads(gzip.decompress(replay.read_bytes()))
        require(len(rows)==24,'Wrong rebuilt-source replay worker count')
        for name,row in rows.items():
            original=read(root/'primary'/name)
            require(comparable(row['records'])==comparable(original['records']),f'Rebuilt-source replay parity: {name}')
            require(row['policy_revision']==original['policy_revision'],'Rebuilt-source policy identity changed')
        replay_workers=len(rows)
    return dict(passed=True,primary_workers=24,profile_workers=4,memory_workers=8,condition_solves=216,
        rebuilt_source_replay_workers=replay_workers,
        field_diagnostic_and_control_parity=True,worthwhile=summary['worthwhile'],decision=summary['decision'])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('evidence',type=Path)
    args=ap.parse_args();print(json.dumps(audit(args.evidence),indent=2))
