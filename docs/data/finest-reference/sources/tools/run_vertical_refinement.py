"""Bounded C2c vertical subdivision and centre-alignment study.

Refine a frozen actual generator output, not its settings. Preserve all prior
archives; compare only accepted independent zero-start solutions. New refined
solutions use OpenMP, with a selected serial alignment-control confirmation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil

import numpy as np

from run_auto_grid_controls import HEIGHTS, POINTS, rectangles
from run_generated_grid_pilot import frozen_indices
from run_horizontal_sensitivity import array, audit_point, comparison, digest, values
from run_joint_grid_verification import (BACKENDS, EXTRA_POINTS, atomic_json, execute,
    fingerprint, gate, input_text, read, resource_estimate)

OUTPUT = Path('docs/data/vertical-refinement')
PROTOCOL = Path('docs/vertical-refinement.md')
PILOT = Path('docs/data/generated-grid-pilot')
LOCATIONS = EXTRA_POINTS + [[15,47],[15,29]]
FAMILIES = ('split-2','split-4','aligned-1.75')


def tasks(backend):
    families = FAMILIES if backend == 'openmp' else ('aligned-1.75',)
    return [dict(id=f'vertical/{family}/160/270/0.5',family=family,extent=160,
                 direction=270,resolution=.5,precision='float64') for family in families]


def align_layers(layers):
    """Align the fifth centre to 1.75; retain all native faces from face eight.

    Redistribute eight lower layers, with bounded growth and monotone thickness
    to float32 tolerance. Bisection fits the first four layers geometrically;
    four equal following layers close the fixed upper face. One float32 ulp
    correction restores that face exactly. No flow measurements enter this fit.
    """
    from dtcc_qes.vertical_grid import effective_faces
    original = effective_faces(layers)
    result = np.array(layers,dtype=float,copy=True)
    tail = (float(original[8])-1.75)/3.5
    fourth = tail/1.15
    target = 1.75-tail/2
    lo,hi=1.,1.15
    for _ in range(100):
        ratio=(lo+hi)/2
        if sum(fourth/ratio**k for k in range(4)) > target:
            lo=ratio
        else:
            hi=ratio
    ratio=(lo+hi)/2
    result[:4]=[fourth/ratio**k for k in (3,2,1,0)]
    result[4:8]=tail
    faces=effective_faces(result)
    result[7]=float(np.float32(result[7])+np.float32(original[8]-faces[8]))
    # Fit the requested float64 endpoint without changing ANY native operand.
    # Starting at each float32 rounding-bin centre leaves room for this tiny
    # normalization. The public explicit-grid endpoint guard remains strict.
    native=result.astype(np.float32)
    result=native.astype(float)*(float(np.sum(layers))/float(np.sum(native,dtype=float)))
    np.testing.assert_array_equal(result.astype(np.float32),native)
    faces=effective_faces(result)
    centres=np.float32(.5)*(faces[:-1]+faces[1:])
    if centres[4]!=np.float32(1.75) or not np.array_equal(faces[8:],original[8:]):
        raise ValueError('Cannot align native centre while preserving upper faces')
    return result


def flat_profile(faces, height):
    faces=np.asarray(faces,dtype=np.float32)
    centres=np.float32(.5)*(faces[:-1]+faces[1:])
    hi=int(np.searchsorted(centres,height))
    exact=hi<len(centres) and centres[hi]==height
    lo=hi if exact else hi-1
    if lo<0 or hi>=len(centres): raise ValueError('Profile would extrapolate')
    weight=0. if exact else (height-float(centres[lo]))/float(centres[hi]-centres[lo])
    profile=np.log((centres.astype(float)+.1)/.1)/np.log(10.1/.1)
    exact_k=float(np.log((height+.1)/.1)/np.log(10.1/.1))
    sampled=float((1-weight)*profile[lo]+weight*profile[hi])
    return dict(centre_indices=[lo,hi],bracketing_centres=[float(centres[lo]),float(centres[hi])],
        upper_weight=weight,exact_K=exact_k,interpolated_K=sampled,bias_K=sampled-exact_k,
        third_centre=float(centres[2]),support_at_least_third=lo>=2,
        interpretation='Analytical neutral profile interpolation only; not a correction to solved flow')


def plans():
    from dtcc_qes import wind
    from dtcc_qes.vertical_grid import effective_faces
    from run_auto_grid_controls import make_city
    parent=read(PILOT/'manifest.json')['configurations']['generated']
    base=np.asarray(parent['layers_input'])
    parent_faces=effective_faces(base)
    candidates={'base':base,**{f'split-{q}':np.repeat(base/q,q) for q in (2,4)},
                'aligned-1.75':align_layers(base)}
    configs={}; city=make_city(rectangles('tower'))
    for family,layers in candidates.items():
        spec=wind.VerticalGrid.from_faces(np.r_[0.,np.cumsum(layers)])
        np.testing.assert_array_equal(spec.layers.astype(np.float32),layers.astype(np.float32))
        preview=wind.preview_grid(city,resolution=.5,bounds=(-40,-40,0,120,120,64),
                                  vertical_grid=spec,max_cells=40000000)
        np.testing.assert_array_equal(preview.z_faces,effective_faces(layers))
        native=preview.solver_dz
        if np.max(.5/native)>8*(1+1e-6) or np.max(native[1:]/native[:-1])>1.15*(1+1e-6):
            raise ValueError('Study growth/aspect constraint violated')
        q=int(family.split('-')[1]) if family.startswith('split-') else 1
        parent_error=float(np.max(np.abs(preview.z_faces[8:]-parent_faces[8:]))) if family=='aligned-1.75' else float(np.max(np.abs(preview.z_faces[::q]-parent_faces)))
        if parent_error>1e-4: raise ValueError('Subdivision parent-face error exceeds predeclared tolerance')
        sampling={str(h):flat_profile(preview.z_faces,h) for h in HEIGHTS}
        if not all(p['support_at_least_third'] for p in sampling.values()):
            raise ValueError('Pedestrian support falls below third physical cell')
        configs[family]=dict(layers_input=layers.tolist(),expected_faces=preview.z_faces.tolist(),
            layers=len(layers),metadata=preview.domain['vertical_grid'],sampling=sampling,
            subdivision=q,parent_native_face_max_error_m=parent_error,
            native_thicknesses=native.tolist(),shape=list(preview.shape),cell_count=preview.cell_count,
            policy='explicit systematic subdivision' if q>1 else
                   'study-only lower-eight-layer alignment' if family=='aligned-1.75' else 'actual auto policy baseline')
    np.testing.assert_array_equal(configs['aligned-1.75']['expected_faces'][8:],configs['base']['expected_faces'][8:])
    return configs


def reference_data(hashes=None):
    paths=[PILOT/name for name in ('manifest.json','raw.json.gz','summary.json','audit.json')]
    paths += [Path('docs/data/joint-grid-verification')/b/name for b in BACKENDS
              for name in ('manifest.json','raw.json.gz','summary.json')]
    actual={str(p):digest(p) for p in paths}
    if hashes is not None and hashes!=actual: raise ValueError('Reference fingerprints changed')
    if not read(PILOT/'audit.json')['vertical_pilot_pass']:
        raise ValueError('Require completed accepted generated-grid pilot')
    source=read(PILOT/'raw.json.gz')
    refs={}
    for backend in BACKENDS:
        base,=[r for r in source[backend]['runs'] if r['task']['extent']==160]
        if not gate(base)['accepted'] or base['backend']!=BACKENDS[backend] or base['disabled_mask']:
            raise ValueError('Baseline scope or solve mismatch')
        refs[backend]=dict(base=base,joint=read(Path('docs/data/joint-grid-verification')/backend/'raw.json.gz'))
    return refs,actual


def point_distance(point):
    x,y=point
    return min(float(np.hypot(max(bx-x,x-bx-w,0),max(by-y,y-by-length,0)))
               for bx,by,w,length,_ in rectangles('tower'))


def point_checks(a,b,height,region):
    rows=[]
    for point in LOCATIONS:
        if region=='away4m' and point_distance(point)<4: continue
        aa,bb=[audit_point(r,height,point,'final') for r in (a,b)]
        valid=aa['valid'] and bb['valid']
        delta=abs(aa['K']-bb['K']) if valid else None
        relative=delta/bb['K'] if valid and bb['K']>=.1 else None
        rows.append(dict(point=point,wall_distance=point_distance(point),valid=valid,K=[aa['K'],bb['K']],
            abs_delta_K=delta,relative_difference=relative,
            within_budget=bool(valid and (relative<.05 if relative is not None else delta<.05))))
    return rows


def compare_pair(a,b,reference,label):
    matched=gate(a)['accepted'] and gate(b)['accepted']
    result=[]
    for height in HEIGHTS:
        for region in ('all','away4m'):
            row=dict(comparison=label,height=height,region=region,matched_accuracy=matched)
            if matched:
                row.update(comparison(a,b,height,frozen_indices(reference,height,region),region))
                row['mandatory_checks']=point_checks(a,b,height,region)
                row['combined_within_budget']=bool(row['within_budget'] and row['solid_fluid_transitions']==0
                    and all(p['within_budget'] for p in row['mandatory_checks']))
            else:
                row['withheld_reason']='Failed common residual/stability gate'
            result.append(row)
    return result


def collect(root,manifest):
    docs={}
    for backend in BACKENDS:
        runs=[]; attempts=[]
        for task in tasks(backend):
            p=root/backend/'cases'/(task['id']+'.json.gz')
            if not p.exists(): continue
            r=read(p)
            if r['study_identity']!=fingerprint(manifest): raise ValueError('Case identity mismatch')
            if r['run'] is not None:
                if r['run']['task']!=task or r['accepted']!=gate(r['run'])['accepted']:
                    raise ValueError('Case task or acceptance mismatch')
                runs.append(r['run'])
            attempts.extend(r['attempts'])
        docs[backend]=dict(runs=runs,attempts=attempts)
    return docs


def summarize(docs,refs,configs):
    result=dict(complete=all(len(docs[b]['runs'])==len(tasks(b)) for b in BACKENDS),
        comfort_qualified=False,preset_selected=False,backend_scope='OpenMP refinement; selected serial alignment control',
        runs={},comparisons=[],control_comparisons=[],control_cpu=[],sensitivity_budget_pass=False)
    for backend in BACKENDS:
        result['runs'][backend]=[dict(task=r['task'],**gate(r),cells=r['cells'],roof_errors=r['roof_errors'],
            peak_rss_bytes=r['peak_rss_bytes'],solver_workspace_bytes=r['solver_workspace_bytes'],
            final_sweeps=r['checkpoints'][-1]['iterations'],
            certification_solve_seconds=sum(c['solve_seconds'] for c in r['checkpoints'])) for r in docs[backend]['runs']]
    available={'base':refs['openmp']['base'],**{r['task']['family']:r for r in docs['openmp']['runs']}}
    pairs=[('base','split-2','base_to_2'),('split-2','split-4','2_to_4'),('base','split-4','base_to_4'),
           ('aligned-1.75','base','alignment_to_base'),('aligned-1.75','split-4','alignment_to_4')]
    for a,b,label in pairs:
        if a in available and b in available:
            result['comparisons'].extend(compare_pair(available[a],available[b],refs['openmp']['joint'],label))
    controls={b:next((r for r in docs[b]['runs'] if r['task']['family']=='aligned-1.75'),None) for b in BACKENDS}
    for backend,c in controls.items():
        if c is not None:
            result['control_comparisons'].extend(dict(backend=backend,**r) for r in
                compare_pair(c,refs[backend]['base'],refs[backend]['joint'],'alignment_to_base'))
    a,b=controls['serial'],controls['openmp']
    if a is not None and b is not None:
        for key in ('initial_planes','profile_planes','sample_x','sample_y','z_faces','roof_errors'):
            if a[key]!=b[key]: raise ValueError('CPU control initial/support mismatch')
        if gate(a)['accepted'] and gate(b)['accepted']:
            for h in HEIGHTS:
                av,bv=[array(values(r,h)) for r in (a,b)]
                am,bm=[np.isfinite(v).all(axis=1) for v in (av,bv)]
                np.testing.assert_array_equal(am,bm)
                delta=np.linalg.norm(av[am]-bv[bm],axis=1)/5
                result['control_cpu'].append(dict(height=h,max_vector_difference_over_Uref=float(delta.max()),
                    p95_vector_difference_over_Uref=float(np.percentile(delta,95))))
    result['control_cpu_agrees']=bool(len(result['control_cpu'])==2 and all(
        r['max_vector_difference_over_Uref']<=1e-3 and r['p95_vector_difference_over_Uref']<=5e-4 for r in result['control_cpu']))
    full=[r for r in result['comparisons'] if r['region']=='all' and r['comparison'] in ('base_to_2','2_to_4','base_to_4')]
    result['sensitivity_budget_pass']=bool(result['complete'] and len(full)==6 and all(r.get('combined_within_budget',False) for r in full))
    result['alignment_budget_pass']=bool(result['complete'] and all(r.get('combined_within_budget',False) for r in result['comparisons']
        if r['region']=='all' and r['comparison'].startswith('alignment_')) and result['control_cpu_agrees'])
    result['flat_profile']={family:config['sampling'] for family,config in configs.items()}
    return result


def verify_frozen(root,manifest,execution=False):
    if digest(root/'protocol.md')!=manifest['protocol_sha256']: raise ValueError('Protocol changed')
    for name,sha in manifest['source_sha256'].items():
        if digest(root/'sources'/name)!=sha: raise ValueError('Frozen source changed')
        if execution and digest(name)!=sha: raise ValueError('Active source changed')
    if execution:
        for binary in manifest['binaries'].values():
            if digest(binary['path'])!=binary['sha256']: raise ValueError('Worker changed')


def freeze(root):
    if (root/'manifest.json').exists(): raise ValueError('Manifest exists; use --resume')
    refs,hashes=reference_data(); configs=plans()
    old=read(PILOT/'manifest.json')
    sources=[Path(__file__).relative_to(Path.cwd()) if Path(__file__).is_absolute() else Path(__file__),
        Path('tests/test_vertical_refinement.py')]
    sources += [Path(name) for name in old['source_sha256'] if not name.startswith('tests/')]
    sources=sorted(set(sources))
    for name,sha in old['source_sha256'].items():
        if not name.startswith('tests/') and digest(name)!=sha:
            raise ValueError(f'Pilot source changed: {name}')
    for binary in old['binaries'].values():
        if digest(binary['path'])!=binary['sha256']: raise ValueError('Historical worker changed')
    initial={'split-2':8000,'split-4':8000,'aligned-1.75':8000}
    manifest=dict(schema='vertical-refinement-v1',utc=datetime.now(timezone.utc).isoformat(),
        configurations=configs,references_sha256=hashes,source_sha256={str(p):digest(p) for p in sources},
        protocol_sha256=digest(PROTOCOL),binaries=old['binaries'],
        task_matrix={b:tasks(b) for b in BACKENDS},initial_n=initial,max_n=16000,workers=2,
        serial_alignment_initial_n=4000,cell_target=20000000,allocation_ceiling=40000000,
        resources={f:resource_estimate(dict(extent=160,resolution=.5,family=f),configs) for f in FAMILIES},
        points=POINTS.tolist(),heights=list(HEIGHTS),mandatory_locations=LOCATIONS,
        numpy=np.__version__,platform=platform.platform(),
        hardware_memory_bytes=os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE'),
        scope='Systematic z subdivision and lower-band alignment; fixed x/y; no policy tuning or comfort qualification')
    if max(r['physical_cells'] for r in manifest['resources'].values())>manifest['allocation_ceiling']:
        raise ValueError('Allocation ceiling below declared matrix')
    root.mkdir(parents=True,exist_ok=True)
    for source in sources:
        target=root/'sources'/source; target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    shutil.copyfile(PROTOCOL,root/'protocol.md');atomic_json(root/'manifest.json',manifest)
    return manifest,refs


def write_summary(root,manifest,refs):
    docs=collect(root,manifest);atomic_json(root/'raw.json.gz',docs)
    summary=summarize(docs,refs,manifest['configurations']);atomic_json(root/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--summarize',action='store_true')
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();root=args.output
    if args.resume or args.summarize:
        manifest=read(root/'manifest.json');verify_frozen(root,manifest,execution=not args.summarize)
        refs,_=reference_data(manifest['references_sha256'])
    else:
        manifest,refs=freeze(root)
    write_summary(root,manifest,refs)
    if args.summarize or args.freeze_only:return
    existing={b:{r['task']['id'] for r in doc['runs']} for b,doc in collect(root,manifest).items()}
    jobs=[(backend,t) for backend in ('openmp','serial') for t in tasks(backend)
          if t['id'] not in existing[backend]]
    def run(job):
        backend,task=job
        n=manifest['serial_alignment_initial_n'] if backend=='serial' else manifest['initial_n'][task['family']]
        return execute(task,manifest['configurations'],Path(manifest['binaries'][backend]['path']),BACKENDS[backend],
            n,manifest['max_n'],manifest['allocation_ceiling'],root/backend,fingerprint(manifest))
    with ThreadPoolExecutor(max_workers=manifest['workers']) as pool:
        for future in as_completed([pool.submit(run,job) for job in jobs]):
            future.result();write_summary(root,manifest,refs)
    s=write_summary(root,manifest,refs)
    print('COMPLETE',s['complete'],'SENSITIVITY',s['sensitivity_budget_pass'],'ALIGNMENT',s['alignment_budget_pass'],flush=True)


if __name__=='__main__':
    main()
