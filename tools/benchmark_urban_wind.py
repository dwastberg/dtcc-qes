"""Frozen urban inputs, isolated source builds and bounded API comparisons.

Run a single explicit shard at a time. Numerical differences from a baseline
are reported as differences; accuracy needs a separately qualified reference.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np
import urban_wind_cases as cases

ROOT = Path(__file__).resolve().parents[1]
DRIVERS = [Path(__file__), Path(cases.__file__)]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n"); temporary.replace(path)


def package_index(package):
    return {p.relative_to(package).as_posix():digest(p) for p in sorted(package.rglob("*"))
            if p.is_file() and (p.suffix in (".py", ".so", ".pyd") or p.name == "_qes_revision.txt")}


def positive_iterations(value):
    value=int(value)
    if value<=0: raise argparse.ArgumentTypeError('Iterations must be positive')
    return value


def positive_seconds(value):
    value=float(value)
    if not np.isfinite(value) or value<=0:
        raise argparse.ArgumentTypeError('Solve seconds must be finite and positive')
    return value


def fixtures(args):
    from dtcc_qes import wind
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    (output/"cases").mkdir()
    specs = [cases.make_case(n) for n in cases.NAMES]
    for path in args.city_case:
        spec=json.loads(path.read_text())
        if spec.get("synthetic", True): raise ValueError("Imported real-city cases must declare synthetic=false and source provenance")
        specs.append(spec)
    if len({s['name'] for s in specs}) != len(specs): raise ValueError("Duplicate case name")
    resolution = dict(smoke=8.,pilot=4.,core=2.,scale=1.)[args.tier]
    directions = [270.] if args.tier in ("smoke", "pilot") else [225.,270.,315.]
    repetitions = 1 if args.tier == "smoke" else 3
    rows = []
    for spec in specs:
        name=spec['name']
        if not name.replace('_','').isalnum(): raise ValueError("Case names must be alphanumeric/underscore")
        cases.write_case(spec,output/f"cases/{name}.json")
        bounds=tuple(np.asarray(spec['bounds'])+np.tile(spec['origin'],2))
        settings=dict(min_layer_thickness=.2,max_aspect_ratio=max(8.,resolution/.2))
        preview=wind.preview_grid(cases.city(spec),bounds=bounds,resolution=resolution,
            vertical_grid=wind.VerticalGrid.auto(**settings),max_cells=40_000_000,terrain="flat")
        # Freeze exact pre-accumulation float32 thickness operands, then pass
        # their float64 cumulative faces to both archives' explicit-grid API.
        spec['solver_dz']=preview.solver_dz.tolist();spec['resolution']=resolution
        spec['expected_shape']=list(preview.shape);spec['max_cells']=40_000_000
        spec['grid_planning_settings']=settings
        spec['planning_bounds']=list(spec['bounds'])
        spec['bounds'][5]=spec['bounds'][2]+float(np.sum(preview.solver_dz.astype(float)))
        explicit=wind.preview_grid(cases.city(spec),**frozen_options(spec,wind))
        for axis in ('x','y','z','z_faces','solver_dz'):
            if not np.array_equal(getattr(preview,axis),getattr(explicit,axis)):
                raise ValueError(f"Frozen explicit grid changed {axis}")
        write(output/f"cases/{name}.json",spec)
        for direction in directions:
            for repeat in range(repetitions):
                for variant in ("baseline", "disabled", "bounded"):
                    rows.append(dict(case=name,direction=direction,repeat=repeat,variant=variant,
                        precision="float32",threads=2 if args.tier=="smoke" else 4,
                        iterations=args.iterations if args.iterations is not None else (8 if args.tier=="smoke" else 500),
                        speed=5.,reference_height=10.,roughness_length=.1,
                        max_solve_seconds=args.solve_seconds,checkpoint_interval=25,residual_interval=0))
    # Six workers per shard means the declared worst-case subprocess limits fit
    # the three-minute matrix envelope. There is no automatic next-shard loop.
    for i,row in enumerate(rows): row.update(id=f"{i:04d}",shard=i//6)
    for driver in DRIVERS:
        dest=output/"sources"/driver.name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(driver.read_bytes())
    write(output/"protocol.json",dict(schema="urban-benchmark-v1",utc=datetime.now(timezone.utc).isoformat(),tier=args.tier,
        rows=rows,shards=1+rows[-1]['shard'],worker_seconds=30,total_shard_seconds=180,
        source_sha256={p.name:digest(p) for p in DRIVERS},
        files={p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file()},
        timing_scope="Fresh worker, small warmup; API timer includes geometry extraction/grid planning, native preparation, initialization, solve, mass, optional monitoring and NumPy construction. Separate load/City, preview, sampling and serialization timers. Supervisor records process wall time including imports and warmup.",
        baseline_policy="S3 is the immediate control-overhead baseline. Corrected S1a can measure aggregate S2–S4 gains. S0 comparisons must label condition-state and ordering changes.",
        accuracy="Unassessed. Same-work parity and baseline field differences are distinct from qualified same-grid reference error.",
        frozen_grid="Exact solver thickness operands; generator cost is measured separately. Native axes/flags/grid metadata are checked by each worker.",
        scope="Synthetic urban morphologies plus explicitly imported frozen real cities; flat ground and constant-height footprints. No network access during workers."))
    print(json.dumps(dict(cases=len(specs),rows=len(rows),shards=1+rows[-1]['shard'],output=str(output))))


def builds(args):
    from compare_native_builds import export_archive, build, stage_package
    from profile_solver_baseline import archive_files
    from profile_solver_s2 import source_files
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    value={}
    for label,path in (("baseline",args.baseline_archive),("candidate",args.candidate_archive)):
        tree,identity,source_id=export_archive(path.resolve(),output/"work")
        instrument_team_probe(tree)
        instrumented=archive_files(output/f"{label}-probe-sources.tar.gz",source_files(tree),tree)
        binary=build(tree,output/"work"/f"{identity}-{args.backend}",args.backend)
        package=output/f"{label}-package";stage_package(tree,binary,package)
        value[label]=dict(package=str(package),source_id=source_id,instrumented_sources=instrumented,files=package_index(package))
    write(output/"builds.json",dict(backend=args.backend,builds=value))
    print(output/"builds.json")


def instrument_team_probe(tree):
    """Append a team-size probe; preserve every existing numerical statement."""
    runner=tree/'src/qes_core/dtcc/wind_runner.cpp';binding=tree/'src/cpp/bindings.cpp'
    if '_urban_benchmark_actual_threads' in binding.read_text(): raise ValueError("Snapshot already instrumented")
    with runner.open('a') as f:
        f.write('''
#ifdef _OPENMP
#include <omp.h>
#endif
extern "C" int dtcc_urban_benchmark_threads() {
  int threads=1;
#ifdef _OPENMP
#pragma omp parallel
  {
#pragma omp single
    threads=omp_get_num_threads();
  }
#endif
  return threads;
}
''')
    text=binding.read_text();text='extern "C" int dtcc_urban_benchmark_threads();\n'+text
    marker='  m.doc() = '
    if text.count(marker)!=1: raise ValueError("Unknown binding module layout")
    text=text.replace(marker,'  m.def("_urban_benchmark_actual_threads", &dtcc_urban_benchmark_threads);\n'+marker)
    binding.write_text(text)


def check_inputs(folder):
    protocol=json.loads((folder/"protocol.json").read_text())
    for name,sha in protocol['files'].items():
        if digest(folder/name)!=sha: raise ValueError(f"Changed benchmark fixture/source: {name}")
    for p in DRIVERS:
        if digest(p)!=protocol['source_sha256'][p.name]: raise ValueError(f"Changed live benchmark driver: {p.name}")
    return protocol


def frozen_options(spec,wind):
    faces=np.r_[0,np.cumsum(spec['solver_dz'],dtype=float)]
    bounds=tuple(np.asarray(spec['bounds'])+np.tile(spec['origin'],2))
    return dict(bounds=bounds,resolution=spec['resolution'],vertical_grid=wind.VerticalGrid.from_faces(faces),
        max_cells=spec['max_cells'],terrain='flat',reference_height=10.,roughness_length=.1)


def run(args):
    folder=args.fixtures.resolve();protocol=check_inputs(folder)
    build_info=json.loads(args.builds.read_text())
    for b in build_info['builds'].values():
        if package_index(Path(b['package']))!=b['files']: raise ValueError("Staged package differs from its source-build manifest")
    rows=[r for r in protocol['rows'] if r['shard']==args.shard]
    if not rows: raise ValueError("Unknown shard")
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    write(output/"execution.json",dict(protocol_sha256=digest(folder/"protocol.json"),builds=build_info,
        rows=rows,worker_seconds=30,total_shard_seconds=180,utc=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(),cpu_count=os.cpu_count()))
    started=time.monotonic();results=[]
    for row in rows:
        label='baseline' if row['variant']=='baseline' else 'candidate'
        target=output/f"{row['id']}.json"; remaining=180-(time.monotonic()-started)
        if remaining<=0: result=dict(status="skipped_total_budget",request=row)
        else:
            package=build_info['builds'][label]['package'];env=os.environ|dict(PYTHONPATH=package,
                OMP_NUM_THREADS=str(row['threads']),OMP_DYNAMIC="FALSE")
            command=[sys.executable,str(Path(__file__).resolve()),"worker","--fixtures",str(folder),"--row",row['id'],"--output",str(target),"--package",package]
            process_start=time.monotonic()
            try:
                with (output/f"{row['id']}.log").open('w') as log:
                    proc=subprocess.run(command,env=env,cwd=package,stdout=log,stderr=subprocess.STDOUT,timeout=min(30,remaining))
                result=json.loads(target.read_text()) if proc.returncode==0 else dict(status="failed",exit_code=proc.returncode,request=row)
            except subprocess.TimeoutExpired:
                result=dict(status="timeout",request=row,wall_limit_seconds=min(30,remaining))
            result['process_seconds']=time.monotonic()-process_start
        result['source_id']=build_info['builds'][label]['source_id'];write(target,result);results.append(result)
        print(row['id'],row['case'],row['variant'],result['status'],flush=True)
    write(output/"summary.json",dict(completed=all(r['status']=='completed' for r in results),elapsed_seconds=time.monotonic()-started,results=results))
    analyze(output)
    write(output/"manifest.json",dict(files={p.name:digest(p) for p in output.iterdir() if p.is_file()}))


def receptor(plane,x,y):
    if x<plane.x[0] or x>plane.x[-1] or y<plane.y[0] or y>plane.y[-1]: return None
    supports=[]
    for axis,p in ((plane.x,x),(plane.y,y)):
        axis=axis.astype(float);hi=int(np.searchsorted(axis,p))
        if axis[hi]==p: supports.append([(hi,1.)])
        else:
            w=(p-axis[hi-1])/(axis[hi]-axis[hi-1]);supports.append([(hi-1,1-w),(hi,w)])
    value=np.zeros(3)
    for i,wx in supports[0]:
        for j,wy in supports[1]:
            if not plane.valid[j,i]: return None
            value+=wx*wy*plane.velocity[j,i]
    return value.tolist()


def worker(args):
    from dtcc_qes import wind,_qes
    import dtcc_qes
    from dtcc_core.model import City
    if any(not Path(module.__file__).resolve().is_relative_to(args.package.resolve()) for module in (dtcc_qes,wind,_qes)):
        raise ValueError("Worker imported the wrong package")
    protocol=json.loads((args.fixtures/"protocol.json").read_text());row=next(r for r in protocol['rows'] if r['id']==args.row)
    actual_threads=_qes._urban_benchmark_actual_threads()
    expected_threads=row['threads'] if _qes.openmp_enabled else 1
    if actual_threads!=expected_threads: raise ValueError("Unexpected actual OpenMP team")
    wind.run(City(),5,270,bounds=(0,0,0,20,20,20),resolution=2,max_iterations=2)
    started=time.perf_counter();t=started
    spec=json.loads((args.fixtures/f"cases/{row['case']}.json").read_text());value=cases.city(spec)
    timing=dict(load_and_city_seconds=time.perf_counter()-t);t=time.perf_counter()
    options=frozen_options(spec,wind)
    options.update(reference_height=row['reference_height'],roughness_length=row['roughness_length'])
    preview=wind.preview_grid(value,**options)
    if list(preview.shape)!=spec['expected_shape'] or preview.solver_dz.tolist()!=spec['solver_dz']: raise ValueError("Frozen grid operands changed")
    timing['preview_seconds']=time.perf_counter()-t;control={}
    if row['variant']=='bounded':
        monitor=wind.MonitorSpec(tuple(spec['roi']),heights=tuple(spec['heights']),history_limit=16,
            receptors=tuple(wind.Receptor(f"r{i}-h{h}",x,y,h) for h in spec['heights'] for i,(x,y) in enumerate(spec['receptors'])))
        control['solver_control']=wind.SolverControl(row['max_solve_seconds'],monitor,
            checkpoint_interval=row['checkpoint_interval'],residual_interval=row['residual_interval'])
    t=time.perf_counter()
    try:
        result=wind.run(value,row['speed'],row['direction'],**options,max_iterations=row['iterations'],
                        solver_precision=row['precision'],**control)
    except RuntimeError as e:
        if hasattr(e,'record'):
            write(args.output,dict(status="budget_exhausted_zero_work",request=row,record=e.record));return
        raise
    timing['api_seconds']=time.perf_counter()-t;t=time.perf_counter();arrays={};receptors=[];peaks=[]
    for n,h in enumerate(spec['heights']):
        plane=result.sample(h,method='linear');r=spec['roi']
        maskx=(plane.x>=r[0])&(plane.x<r[1]);masky=(plane.y>=r[2])&(plane.y<r[3])
        velocity=plane.velocity[masky][:,maskx];valid=plane.valid[masky][:,maskx]
        arrays[f'velocity{n}']=velocity;arrays[f'valid{n}']=valid
        arrays[f'x{n}']=plane.x[maskx];arrays[f'y{n}']=plane.y[masky]
        speeds=np.linalg.norm(velocity,axis=-1);speeds[~valid]=-np.inf
        if valid.any():
            j,i=np.unravel_index(np.argmax(speeds),speeds.shape)
            peaks.append(dict(height=h,speed=float(speeds[j,i]),x=float(plane.x[maskx][i]),y=float(plane.y[masky][j])))
        else: peaks.append(dict(height=h,speed=None,x=None,y=None))
        receptors.append([receptor(plane,x,y) for x,y in spec['receptors']])
    timing['sampling_seconds']=time.perf_counter()-t;t=time.perf_counter()
    hashes={name:hashlib.sha256(memoryview(getattr(result,name)).cast('B')).hexdigest() for name in ('velocity','cell_flags')}
    grid_hashes={name:hashlib.sha256(memoryview(getattr(result,name)).cast('B')).hexdigest() for name in ('x','y','z','z_faces')}
    np.savez_compressed(args.output.with_suffix('.npz'),**arrays)
    timing['hash_and_output_seconds']=time.perf_counter()-t;timing['pipeline_seconds']=time.perf_counter()-started
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    write(args.output,dict(status="completed",request=row,timing=timing,diagnostics=asdict(result.diagnostics),
        control=result.metadata.get('solver_control'),field_sha256=hashes,grid_sha256=grid_hashes,
        shape=list(result.cell_flags.shape),building_count=len(spec['buildings']),peak_rss_bytes=rss,
        actual_threads=actual_threads,
        peaks=peaks,receptors=receptors,extension_sha256=digest(_qes.__file__),backend=_qes.cpu_backend,
        native_build=result.metadata['versions']['native_build'],versions=result.metadata['versions'],effective_domain=result.metadata['domain']))


def analyze(output):
    summary=json.loads((output/'summary.json').read_text());groups={}
    for row in summary['results']:
        q=row['request'];groups.setdefault((q['case'],q['direction'],q['repeat']),{})[q['variant']]=row
    comparisons=[]
    for key,g in groups.items():
        base=g.get('baseline')
        for name in ('disabled','bounded'):
            other=g.get(name)
            if not base or not other or base['status']!='completed' or other['status']!='completed': continue
            compatible=base['grid_sha256']==other['grid_sha256'] and base['shape']==other['shape']
            same_work=base['diagnostics']['iterations']==other['diagnostics']['iterations']
            record=dict(case=key[0],direction=key[1],repeat=key[2],variant=name,same_grid=compatible,same_completed_work=same_work,
                api_ratio=other['timing']['api_seconds']/base['timing']['api_seconds'],
                field_bitwise_equal=base['field_sha256']==other['field_sha256'],reference_qualification="not_assessed",planes=[])
            if not compatible:
                comparisons.append(record);continue
            with np.load(output/f"{base['request']['id']}.npz") as a,np.load(output/f"{other['request']['id']}.npz") as b:
                for n in (0,1):
                    va,vb=a[f'valid{n}'],b[f'valid{n}'];common=va&vb
                    delta=np.linalg.norm(a[f'velocity{n}'][common]-b[f'velocity{n}'][common],axis=-1)/base['request']['speed']
                    speed=np.abs(np.linalg.norm(a[f'velocity{n}'][common],axis=-1)-np.linalg.norm(b[f'velocity{n}'][common],axis=-1))/base['request']['speed']
                    record['planes'].append(dict(common_valid=int(common.sum()),validity_changes=int((va!=vb).sum()),
                        vector_difference_over_uref_p95=float(np.percentile(delta,95)) if delta.size else None,
                        vector_difference_over_uref_max=float(delta.max()) if delta.size else None,
                        speed_factor_difference_p95=float(np.percentile(speed,95)) if speed.size else None))
            comparisons.append(record)
    write(output/'comparisons.json',dict(comparisons=comparisons,
        qualification="Baseline differences only. Completed-work counts, grid and validity must be inspected. No adaptive accuracy acceptance or physical validation."))
    print_report(summary['results'],comparisons,output,summary.get('elapsed_seconds'))


def print_report(results, comparisons, output, elapsed_seconds=None):
    """Print descriptive results without changing the timed worker workload."""
    counts=Counter(r['status'] for r in results)
    completed=counts.get('completed',0)
    elapsed=f"; shard elapsed {elapsed_seconds:.2f} s" if elapsed_seconds is not None else ''
    print(f"\nBenchmark results: {completed}/{len(results)} workers completed{elapsed}")
    print('Statuses: '+', '.join(f'{name}={n}' for name,n in sorted(counts.items())))
    groups={}
    for row in results:
        if row['status']=='completed':
            q=row['request']
            groups.setdefault((q['case'],q['direction'],q['variant']),[]).append(row)

    def number(values, scale=1, precision=3):
        values=[v/scale for v in values if v is not None]
        return f'{np.median(values):.{precision}f}' if values else 'n/a'

    def table(headers, rows):
        widths=[max(len(str(row[i])) for row in [headers,*rows]) for i in range(len(headers))]
        for row in [headers,*rows]:
            print('  '.join(str(value).ljust(width) for value,width in zip(row,widths)))

    if groups:
        print('\nMedians by case and variant (RSS is process peak; sweeps show min-max):')
        rows=[]
        order={'baseline':0,'disabled':1,'bounded':2}
        for (case,direction,variant),g in sorted(groups.items(),key=lambda item:(item[0][:2],order[item[0][2]])):
            sweeps=[r['diagnostics']['iterations'] for r in g]
            stops=Counter((r.get('control') or {}).get('termination_reason') or
                          ('legacy_tolerance' if r['diagnostics'].get('converged') else 'iteration_limit') for r in g)
            rows.append([f'{case} {direction:g}deg',variant,str(len(g)),
                number([r['timing']['api_seconds'] for r in g]),
                number([r['timing'].get('pipeline_seconds') for r in g]),
                number([r.get('peak_rss_bytes') for r in g],1024**2,1),
                str(min(sweeps)) if min(sweeps)==max(sweeps) else f'{min(sweeps)}-{max(sweeps)}',
                ', '.join(f'{name}:{n}' for name,n in sorted(stops.items()))])
        table(['Case / wind FROM','Variant','N','API s','Pipeline s','RSS MiB','Sweeps','Stops'],rows)

    if comparisons:
        print('\nPaired comparisons with baseline (API/base < 1 is faster; inspect equal-work counts):')
        paired={}
        for c in comparisons:
            paired.setdefault((c['case'],c['direction'],c['variant']),[]).append(c)
        rows=[]
        for (case,direction,variant),g in sorted(paired.items()):
            planes=[p for c in g for p in c['planes']]
            def maximum(field):
                values=[p[field] for p in planes if p.get(field) is not None]
                return f'{max(values):.3g}' if values else 'n/a'
            rows.append([f'{case} {direction:g}deg',variant,str(len(g)),
                number([c['api_ratio'] for c in g]),
                *[f'{sum(bool(c[field]) for c in g)}/{len(g)}' for field in
                  ('same_grid','same_completed_work','field_bitwise_equal')],
                maximum('vector_difference_over_uref_p95'),maximum('vector_difference_over_uref_max'),
                maximum('validity_changes')])
        table(['Case / wind FROM','Variant','Pairs','API/base','Same grid','Same work','Equal fields',
               'p95 dU/Uref*','max dU/Uref*','Mask changes*'],rows)
        print('* Largest value across paired repetitions and sampled heights; n/a means no comparable support.')
    elif completed:
        print('\nNo paired baseline comparisons available in these results.')
    for row in results:
        if row['status']!='completed':
            q=row['request']
            print(f"  {q['id']} {q['case']} {q['variant']}: {row['status']}")
    print('Field differences are against baseline; accuracy is not assessed.')
    print(f'Detailed results: {Path(output).resolve()}',flush=True)


def aggregate(args):
    groups={};seen=set();identity=None;incomplete=[];results=[];comparisons=[]
    for folder in args.runs:
        manifest=json.loads((folder/'manifest.json').read_text())
        for name,sha in manifest['files'].items():
            if digest(folder/name)!=sha: raise ValueError(f"Edited benchmark outcome: {folder/name}")
        execution=json.loads((folder/'execution.json').read_text())
        current=(execution['protocol_sha256'],json.dumps(execution['builds'],sort_keys=True))
        if identity is not None and current!=identity: raise ValueError("Cannot aggregate different protocols/builds")
        identity=current
        summary=json.loads((folder/'summary.json').read_text())
        results.extend(summary['results'])
        comparisons.extend(json.loads((folder/'comparisons.json').read_text())['comparisons'])
        if not summary['completed']: incomplete.append(str(folder))
        for row in summary['results']:
            q=row['request']
            if q['id'] in seen: raise ValueError("Duplicate benchmark row")
            seen.add(q['id'])
            if row['status']!='completed': continue
            groups.setdefault((q['case'],q['direction'],q['variant']),[]).append(row)
    medians=[]
    for key,g in sorted(groups.items()):
        elapsed=[r['timing']['api_seconds'] for r in g]
        medians.append(dict(case=key[0],direction=key[1],variant=key[2],repetitions=len(g),
            api_median_seconds=float(np.median(elapsed)),api_min_seconds=min(elapsed),api_max_seconds=max(elapsed),
            pipeline_median_seconds=float(np.median([r['timing']['pipeline_seconds'] for r in g])),
            peak_rss_median_bytes=float(np.median([r['peak_rss_bytes'] for r in g])),
            completed_sweeps=[r['diagnostics']['iterations'] for r in g],
            source_ids=sorted({r['source_id'] for r in g}),reference_qualification='not_assessed'))
    write(args.output,dict(medians=medians,rows=len(seen),incomplete_shards=incomplete,
        qualification="Descriptive process repetitions only; no timing guarantee or accuracy acceptance. Missing/failed rows remain explicit."))
    print_report(results,comparisons,args.output)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('fixtures');p.add_argument('--output',type=Path,required=True);p.add_argument('--tier',choices=('smoke','pilot','core','scale'),default='pilot');p.add_argument('--city-case',type=Path,action='append',default=[])
    p.add_argument('--iterations',type=positive_iterations,help='Override the tier iteration cap')
    p.add_argument('--solve-seconds',type=positive_seconds,default=5.,help='Monitored solve budget (default: 5 seconds)')
    p=sub.add_parser('builds');p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-archive',type=Path,required=True);p.add_argument('--candidate-archive',type=Path,required=True);p.add_argument('--backend',choices=('openmp','serial'),default='openmp')
    p=sub.add_parser('run');p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--builds',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--shard',type=int,required=True)
    p=sub.add_parser('worker');p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--row',required=True);p.add_argument('--package',type=Path,required=True)
    p=sub.add_parser('analyze');p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('aggregate');p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.output) if args.action=='analyze' else globals()[args.action](args)


if __name__=='__main__': main()
