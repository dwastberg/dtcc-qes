"""Explicit Surrey Urban roughness, common Suburban inlet, and bounded workers."""
import argparse
from dataclasses import asdict
import gzip
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time

import numpy as np

from benchmark_evidence import digest, write_json
from aij.workers import run_worker
from surrey_background import ROOT, MEANS, VARIANCES, observations, score, summarize, vertical_faces, write_csv, turbulence_settings

PROTOCOL=ROOT/'validation/specifications/surrey_transition_v1.json'


def bounds(descriptor,protocol):
    d=protocol['domain'];half=descriptor.get('half_width_m',d['half_width_m'])
    return (descriptor.get('xmin_m',d['xmin_m']),-half,0.,
        descriptor.get('xmax_m',d['xmax_m']),half,descriptor.get('top_m',d['top_m']))


def blocks(descriptor,protocol):
    if descriptor['layout']=='empty':return []
    g=protocol['geometry'];b=bounds(descriptor,protocol);padding=g['edge_padding_m']
    phase=.5 if descriptor['layout']=='street' else 0.
    output=[];nrows=int(np.ceil(b[3]/g['streamwise_pitch_m']))
    ncols=int(np.ceil(b[4]/g['lateral_pitch_m']))+1
    for i in range(nrows):
        x=round(i*g['streamwise_pitch_m'],12)
        if x+g['length_m']>b[3]-padding+1e-12:continue
        for j in range(-ncols,ncols+1):
            y=round((j+phase)*g['lateral_pitch_m'],12)
            lo,hi=round(y-g['width_m']/2,12),round(y+g['width_m']/2,12)
            if lo<b[1]+padding-1e-12 or hi>b[4]-padding+1e-12:continue
            output.append(dict(id=f'roughness-r{i:03d}-c{j:+03d}',row=i,column=j,
                xmin=x,xmax=round(x+g['length_m'],12),ymin=lo,ymax=hi,height=g['height_m']))
    return output


def city_from_blocks(rectangles):
    from dtcc_core.model import Building,City,GeometryType,Surface
    city=City()
    for r in rectangles:
        building=Building(id=r['id']);building.measured_height=r['height']
        building.add_geometry(Surface(vertices=np.array([[r['xmin'],r['ymin'],0],
            [r['xmin'],r['ymax'],0],[r['xmax'],r['ymax'],0],[r['xmax'],r['ymin'],0]],float)),GeometryType.LOD0)
        city.add_building(building)
    return city


def layers(descriptor,protocol):
    return vertical_faces(descriptor['spacing_m'],dict(domain=dict(protocol['domain'],top_m=bounds(descriptor,protocol)[5])))


def inlet(observed,background):
    from dtcc_qes import wind
    rows=[r for r in observed if r['station']==-10];ref=background['nominal_reference_speed_m_s']
    return wind.MeasuredProfile.from_components([r['z_m'] for r in rows],
        [r['U']*ref for r in rows],[r['V']*ref for r in rows],reference_height=.24,
        roughness_length=background['published_parameters']['suburban']['z0_m'],below='log',above='constant')


def parameters(descriptor,protocol):
    from dtcc_qes import wind
    p=dict(protocol['parameterizations'])
    if descriptor.get('projection_only'):
        p.update(rooftop=0,upwind_cavity=0,street_canyon=0,wake=0,high_rise=0,sidewall=0)
    return wind.Parameterizations(**p)


def solid_union(x,y,z,rectangles):
    """Independent rectangular containment, without calling the native rasterizer."""
    mask=np.zeros((len(z),len(y),len(x)),bool)
    for r in rectangles:
        i=np.flatnonzero((x>r['xmin'])&(x<r['xmax']))
        j=np.flatnonzero((y>r['ymin'])&(y<r['ymax']))
        k=np.flatnonzero((z>0)&(z<r['height']))
        mask[np.ix_(k,j,i)]=True
    return mask


def sample_scalar(field,details):
    """Use exactly the positive-weight geometric contributors in i,j,k order."""
    values=[]
    for indices,weights in zip(details['indices'],details['weights'],strict=True):
        take=weights>0;i,j,k=np.asarray(indices)[take].T
        values.append(np.sum(field[k,j,i]*np.asarray(weights)[take]))
    return np.array(values)


def prediction_rows(observed,sampled,fields,ref):
    n=len(observed);computed=np.zeros(n,bool);valid=computed.copy()
    diagonal=np.full((n,3),np.nan);internal=np.full(n,np.nan);mixing=internal.copy();cap=internal.copy()
    if fields is not None:
        computed=sampled.support.computed;valid=sampled.stress_valid
        diagonal=sampled.stress[:,[0,3,5]]/ref**2
        internal=sample_scalar(fields.tke,sampled.support.contributors)/ref**2
        mixing=sample_scalar(fields.mixing_length,sampled.support.contributors)
        cap=sample_scalar(fields.capped,sampled.support.contributors)
    fractions=np.divide(diagonal,diagonal.sum(axis=1)[:,None],out=np.full_like(diagonal,np.nan),where=diagonal.sum(axis=1)[:,None]>0)
    output=[]
    for i,r in enumerate(observed):
        row=dict(id=r['id'],station=r['station'],z_m=r['z_m'],
            velocity_valid=bool(sampled.valid[i]),computed=bool(computed[i]),stress_valid=bool(valid[i]),
            internal_k=float(internal[i]),k=float(.5*diagonal[i].sum()),mixing_length_m=float(mixing[i]),capped_source_weight=float(cap[i]))
        row.update(dict(zip(MEANS,sampled.velocity[i]/ref,strict=True)))
        row.update(dict(zip(VARIANCES,diagonal[i],strict=True)))
        row.update(dict(zip(('f_u','f_v','f_w'),fractions[i],strict=True)))
        for j,q in enumerate(('xx','xy','xz','yy','yz','zz')):
            row[q]=float(sampled.stress[i,j]/ref**2) if fields is not None else float('nan')
        output.append(row)
    return output


def epoch(protocol_path,identity_path):
    import dtcc_qes
    from dtcc_qes import _qes
    if digest(identity_path)!=_qes.solver_policy_revision:raise ValueError('Native/build identity mismatch')
    for line in identity_path.read_text().splitlines()[1:]:
        name,sha=line.rsplit(' ',1)
        if digest(ROOT/name)!=sha:raise ValueError('Native source changed: '+name)
    package=Path(dtcc_qes.__file__).parent
    for p in (ROOT/'src/dtcc_qes').glob('*.py'):
        if digest(package/p.name)!=digest(p):raise ValueError('Imported Python source mismatch')
    source_names=('validation/surrey_transition.py','validation/surrey_background.py',
        'validation/SURREY_TRANSITION_PROTOCOL.md','validation/specifications/surrey_transition_v1.json',
        'validation/specifications/surrey_background_v1.json')
    prior=json.loads(gzip.decompress((ROOT/'docs/data/surrey-background/manifest.json.gz').read_bytes()))
    if prior['protocol_sha256']!=digest(ROOT/'validation/specifications/surrey_background_v1.json'):
        raise ValueError('Background protocol changed')
    return dict(sources={name:digest(ROOT/name) for name in source_names},protocol_sha256=digest(protocol_path),
        native_sha256=digest(_qes.__file__),native_policy_revision=_qes.solver_policy_revision,
        native_matches_background_binary=digest(_qes.__file__)==prior['native']['sha256'],
        native_matches_background_build_identity=_qes.solver_policy_revision==prior['native']['policy_revision'],
        python={p.name:digest(p) for p in package.glob('*.py')})


def checkpoint_change(record,ref):
    history=record['checkpoint_history']
    if len(history)<2:return None
    a,b=history[-2:];previous={r['receptor']:r for r in a['receptors']};deltas=[]
    for r in b['receptors']:
        p=previous.get(r['receptor'])
        if p is None or not r['sample']['valid'] or not p['sample']['valid']:return None
        deltas.append(np.linalg.norm(np.array(r['sample']['velocity'])-p['sample']['velocity'])/ref)
    return float(max(deltas)) if deltas else None


def worker(output,manifest):
    from dtcc_qes import wind
    descriptor=json.loads((output/'descriptor.json').read_text());protocol=manifest['protocol']
    if epoch(Path(manifest['protocol_path']),Path(manifest['identity_path']))!=manifest['epoch']:
        raise ValueError('Campaign source epoch changed')
    background=json.loads((ROOT/protocol['background_protocol']).read_text())
    observed=observations(background,ROOT/background['source']);ref=background['nominal_reference_speed_m_s']
    rectangles=blocks(descriptor,protocol);city=city_from_blocks(rectangles);profile=inlet(observed,background)
    expected=json.loads((output/'geometry.json').read_text())
    if expected['blocks']!=rectangles:raise ValueError('Planned geometry changed')
    points=np.array([[r['x_hat_m'],r['y_m'],r['z_m']] for r in observed])
    monitor=wind.MonitorSpec(region=(-.7,1.41,-.035,.035),heights=(),frame='world',
        receptors=tuple(wind.Receptor(r['id'],*p,required=True) for r,p in zip(observed,points,strict=True)),
        global_mass=True,history_limit=110,memory_limit_bytes=256*2**20)
    use_turbulence=descriptor.get('turbulence',True)
    solver=wind.Solver(**protocol['solver'],monitor=monitor,raise_on_failure=False)
    started=time.perf_counter()
    result=wind.run(city,profile,resolution=descriptor['spacing_m'],bounds=bounds(descriptor,protocol),
        vertical_grid=wind.VerticalGrid.from_faces(layers(descriptor,protocol)),
        turbulence=turbulence_settings(protocol['turbulence']) if use_turbulence else None,
        footprints=wind.Footprints(**protocol['footprints']),parameterizations=parameters(descriptor,protocol),
        solver=solver,max_cells=20_000_000)
    elapsed=time.perf_counter()-started
    sampled=result.sample_points(points,method='linear',frame='global',diagnostics=True,include_contributors=True)
    predictions=prediction_rows(observed,sampled,result.turbulence,ref)
    # Persist the expensive native result before derived geometry/guard analysis.
    write_json(output/'capture.json',dict(descriptor=descriptor,epoch=manifest['epoch'],
        metadata=result.metadata,diagnostics=asdict(result.diagnostics),solver=result.solver,
        support=sampled.support.to_dict(),predictions=predictions,wall_seconds=elapsed))
    np.savez_compressed(output/'observed-native.npz',points=points,velocity=sampled.velocity,
        stress=sampled.stress if use_turbulence else np.empty((0,6)))
    axes=[a.astype(float)+result.origin[i] for i,a in enumerate((result.x,result.y,result.z))]
    independent=solid_union(*axes,rectangles);solid=result.solid_mask
    target_volume=sum((r['xmax']-r['xmin'])*(r['ymax']-r['ymin'])*r['height'] for r in rectangles)
    volume=float(np.sum(solid*np.diff(result.z_faces)[:,None,None])*result.resolution**2)
    volume_error=abs(volume/target_volume-1) if target_volume else float(volume!=0)
    change=checkpoint_change(result.solver['record'],ref)
    mass=result.diagnostics.max_divergence
    relative_mass=mass*descriptor['spacing_m']/ref if mass is not None else None
    guards=dict(converged=result.diagnostics.converged,
        complete_geometry_support=bool(sampled.valid.all() and sampled.support.geometric.all()),
        exact_solid_mask=bool(np.array_equal(independent,solid)),
        solid_volume=volume_error<=protocol['guards']['maximum_solid_volume_relative_error'],
        finite_velocity=bool(np.isfinite(result.velocity).all()),
        cell_flux_divergence=relative_mass is not None and relative_mass<=protocol['guards']['maximum_cell_flux_divergence_over_Uref'],
        stable_checkpoint=change is not None and change<=protocol['guards']['last_checkpoint_velocity_change_over_Uref'])
    if use_turbulence:
        fields=result.turbulence
        guards.update(complete_computed_support=bool(sampled.support.computed.all()),
            finite_computed_stress=bool(np.isfinite(fields.stress[fields.computed]).all()))
    write_json(output/'worker.json',dict(descriptor=descriptor,epoch=manifest['epoch'],
        metadata=result.metadata,diagnostics=asdict(result.diagnostics),solver=result.solver,
        guards=guards,solid_volume_m3=volume,expected_volume_m3=target_volume,solid_volume_relative_error=volume_error,
        cell_flux_divergence_over_Uref=relative_mass,last_checkpoint_velocity_change_over_Uref=change,
        wall_seconds=elapsed,peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if platform.system()=='Darwin' else 1024),
        invalid_stress_observations=int((~sampled.stress_valid).sum()) if use_turbulence else None,
        support=sampled.support.to_dict(),predictions=predictions,
        station_scores={str(s):summarize([r for r in observed if r['station']==s],
            [r for r in predictions if r['station']==s]) for s in background['stations']},
        scores=summarize(observed,predictions)))
    write_csv(output/'predictions.csv',predictions)
    xx,zz=np.meshgrid(axes[0],axes[2][axes[2]<=.84]);curtain=np.c_[xx.ravel(),np.zeros(xx.size),zz.ravel()]
    plane=result.sample_points(curtain,'linear',frame='global')
    arrays=dict(x=axes[0],z=axes[2][axes[2]<=.84],velocity=plane.velocity.reshape(*xx.shape,3),
        valid=plane.valid.reshape(xx.shape),sampled_velocity=sampled.velocity,sampled_points=sampled.sampled_points,
        grid_x=result.x,grid_y=result.y,grid_z=result.z,z_faces=result.z_faces,origin=result.origin,
        solid_mask_centre=solid[:,len(result.y)//2,:])
    if use_turbulence:
        arrays.update(stress=plane.stress.reshape(*xx.shape,6),stress_valid=plane.stress_valid.reshape(xx.shape),sampled_stress=sampled.stress)
    np.savez_compressed(output/'fields.npz',**arrays)
    print(descriptor['name'],'guards',guards,'wall_seconds',round(elapsed,3),flush=True)


def compare_runs(a,b):
    lookup={r['id']:r for r in a['predictions']}
    if set(lookup)!={r['id'] for r in b['predictions']}:raise ValueError('Paired observation identity changed')
    output={}
    for q in ('U','V','W','k','uu','vv','ww','f_w'):
        flag='velocity_valid' if q in MEANS else 'stress_valid'
        output[q]=score([r[q] for r in b['predictions']], [lookup[r['id']][q] for r in b['predictions']],
            [r[flag] and lookup[r['id']][flag] for r in b['predictions']])
    output['both_execution_guards_pass']=all(a['guards'].values()) and all(b['guards'].values())
    return output


def analyse(output,manifest):
    runs={}
    for event in json.loads((output/'ledger.json').read_text()):
        p=output/event['name']/'worker.json'
        if event['complete'] and p.exists():runs[event['name']]=json.loads(p.read_text())
    pairs={}
    for label,a,b in (('empty_grid','empty-coarse','empty-fine'),('street_grid','street-coarse','street-fine'),
        ('block_grid','block-coarse','block-fine'),('coarse_phase','street-coarse','block-coarse'),
        ('fine_phase','street-fine','block-fine'),('width','street-coarse','street-wide'),
        ('streamwise_extent','street-coarse','street-long'),('ceiling_height','street-coarse','street-tunnel-height'),
        ('parameterizations','street-coarse','street-projection'),('geometry_coarse','empty-coarse','street-coarse'),
        ('geometry_fine','empty-fine','street-fine')):
        if a in runs and b in runs:pairs[label]=dict(first=a,second=b,changes=compare_runs(runs[a],runs[b]))
    write_json(output/'report.json',dict(schema='surrey-transition-results-v1',
        planned_runs=len(manifest['protocol']['matrix']),completed_workers=len(runs),
        execution_qualified=[name for name,r in runs.items() if all(r['guards'].values())],
        failed_execution_guards={name:[k for k,v in r['guards'].items() if not v] for name,r in runs.items() if not all(r['guards'].values())},
        physical_qualification=False,pedestrian_qualification=False,
        scores={name:r['scores'] for name,r in runs.items()},paired_changes=pairs,
        runtime={name:dict(wall_seconds=r['wall_seconds'],peak_rss_bytes=r['peak_rss_bytes'],iterations=r['diagnostics']['iterations']) for name,r in runs.items()}))


def run(output,protocol_path,identity_path,prepare_only=False):
    from dtcc_qes import wind
    protocol=json.loads(protocol_path.read_text());background=json.loads((ROOT/protocol['background_protocol']).read_text())
    if os.environ.get('OMP_NUM_THREADS')!=str(protocol['threads']['openmp']):raise ValueError('Unexpected OpenMP thread count')
    observed=observations(background,ROOT/background['source']);profile=inlet(observed,background)
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(schema='surrey-transition-run-v1',protocol=protocol,protocol_path=str(protocol_path.resolve()),
        identity_path=str(identity_path.resolve()),epoch=epoch(protocol_path,identity_path),
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_export_sha256=digest(ROOT/background['source']),new_aij_launches=0,measured_energy_input=False,
        prepared_only=prepare_only,environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform()))
    write_json(output/'manifest.json',manifest);write_csv(output/'observations.csv',observed)
    for name in manifest['epoch']['sources']:
        dest=output/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    shutil.copyfile(identity_path,output/'build-identity.txt')
    for descriptor in protocol['matrix']:
        folder=output/descriptor['name'];folder.mkdir();rectangles=blocks(descriptor,protocol)
        preview=wind.preview_grid(city_from_blocks(rectangles),profile,resolution=descriptor['spacing_m'],
            bounds=bounds(descriptor,protocol),vertical_grid=wind.VerticalGrid.from_faces(layers(descriptor,protocol)),
            turbulence=turbulence_settings(protocol['turbulence']) if descriptor.get('turbulence',True) else None,
            footprints=wind.Footprints(**protocol['footprints']),parameterizations=parameters(descriptor,protocol))
        write_json(folder/'descriptor.json',descriptor)
        write_json(folder/'geometry.json',dict(blocks=rectangles,requested_bounds=bounds(descriptor,protocol),
            preview=dict(shape=preview.shape,cell_count=preview.cell_count,domain=preview.domain),
            reference_line_y_m=0,phase_interpretation=protocol['geometry_status']))
        print('Prepared',descriptor['name'],len(rectangles),'blocks',preview.cell_count,'cells',flush=True)
    if prepare_only:return
    ledger=[]
    for descriptor in protocol['matrix']:
        folder=output/descriptor['name'];ledger.append(dict(name=descriptor['name'],status='launched'))
        write_json(output/'ledger.json',ledger)
        outcome=run_worker([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',str(folder.resolve())],
            folder/'stderr.log',deadline=protocol['worker_deadline_seconds'])
        ledger[-1].update(outcome);write_json(output/'ledger.json',ledger)
        print(descriptor['name'],outcome['status'],round(outcome['wall_seconds'],2),flush=True)
        if not outcome['complete']:break
    analyse(output,manifest)
    write_json(output/'checksums.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path)
    p.add_argument('--protocol',type=Path,default=PROTOCOL);p.add_argument('--build-identity',type=Path)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--worker',type=Path)
    a=p.parse_args()
    if a.worker:worker(a.worker,json.loads((a.worker.parent/'manifest.json').read_text()))
    else:
        if a.output is None or a.build_identity is None:p.error('--output and --build-identity are required')
        run(a.output,a.protocol,a.build_identity,a.prepare_only)


if __name__=='__main__':main()
