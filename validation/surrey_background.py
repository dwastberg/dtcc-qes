"""Pinned Surrey background profiles and conditional native turbulence benchmark."""
import argparse
import csv
from dataclasses import asdict
import gzip
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import numpy as np

from benchmark_evidence import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'validation/specifications/surrey_background_v1.json'
MEANS = ('U', 'V', 'W')
VARIANCES = ('uu', 'vv', 'ww')
QUANTITIES = ('U', 'V', 'W', 'uu', 'vv', 'ww', 'k', 'f_u', 'f_v', 'f_w')


def observations(protocol, source):
    """Preserve original rows/units and assign stable physical observation IDs."""
    if digest(source) != protocol['source_sha256']:
        raise ValueError('Surrey source identity changed')
    raw = list(csv.DictReader(io.StringIO(gzip.decompress(source.read_bytes()).decode())))
    rows = []
    for item in raw:
        a = {k: float(v) for k, v in item.items()}
        if not np.isfinite(list(a.values())).all() or a['Reference_speed'] <= 0:
            raise ValueError('Invalid Surrey observation')
        station = round(a['X_mm'] / protocol['roughness_length_scale_mm'])
        if abs(a['X_mm'] - station * protocol['roughness_length_scale_mm']) > .05 or abs(a['Y_mm']) > .01:
            raise ValueError('Unexpected Surrey station coordinate')
        regime = 'suburban' if station == -10 else 'urban'
        group = 'suburban' if station == -10 else 'urban_developed' if station in protocol['developed_stations'] else 'urban_developing'
        z, ref = a['Z_mm'] / 1000, a['Reference_speed']
        variance = np.array([a[c + '_variance'] for c in MEANS])
        if np.any(variance < 0) or variance.sum() <= 0 or z <= 0:
            raise ValueError('Invalid Surrey variance/height')
        row = dict(id=f'S{station:+03d}-Z{a["Z_mm"]:04.0f}', station=station,
            regime=regime, group=group, x_hat_m=a['X_mm']/1000,
            x_cluster_m=(a['X_mm']-protocol['coordinate_offset_mm'])/1000,
            y_m=a['Y_mm']/1000, z_m=z, reference_speed_m_s=ref,
            height_stratum='above_3h' if z >= (0.06 if regime == 'suburban' else .21) else 'below_3h',
            **a)
        row.update({c: a[c+'_mean']/ref for c in MEANS})
        row.update(dict(zip(VARIANCES, variance/ref**2, strict=True)))
        row['k'] = float(.5*variance.sum()/ref**2)
        row.update(dict(zip(('f_u','f_v','f_w'), variance/variance.sum(), strict=True)))
        rows.append(row)
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate Surrey observation ID')
    if sorted({r['station'] for r in rows}) != protocol['stations']:
        raise ValueError('Surrey station inventory changed')
    for station in protocol['stations']:
        actual = sorted(r['Z_mm'] for r in rows if r['station'] == station)
        if actual != protocol['suburban_heights_mm' if station == -10 else 'urban_heights_mm']:
            raise ValueError('Surrey height inventory changed')
    return sorted(rows, key=lambda r: (r['station'], r['z_m']))


def published_log(z, regime, protocol):
    p = protocol['published_parameters'][regime]
    z = np.asarray(z, float)
    if np.any(z <= p['displacement_m']):
        raise ValueError('Published log law has no support below displacement')
    return p['u_star_over_Uref']/protocol['von_karman']*np.log((z-p['displacement_m'])/p['z0_m'])


def vertical_faces(dz, protocol):
    d = protocol['domain']
    n = round(d['fine_top_m']/dz)
    faces = list(np.linspace(0, d['fine_top_m'], n+1))
    step = dz
    while faces[-1] < d['top_m']:
        step *= d['upper_growth']
        faces.append(min(d['top_m'], faces[-1]+step))
    return np.array(faces)


def score(predicted, measured, valid):
    """Never silently shrink a requested experimental population."""
    predicted, measured, valid = np.asarray(predicted, float), np.asarray(measured, float), np.asarray(valid, bool)
    if predicted.shape != measured.shape or valid.shape != measured.shape:
        raise ValueError('Score population shape mismatch')
    supported = valid & np.isfinite(predicted) & np.isfinite(measured)
    result = dict(count=len(measured), valid=int(supported.sum()), missing_or_invalid=int((~supported).sum()),
        complete=bool(supported.all() and len(measured)))
    if result['complete']:
        delta = predicted-measured
        result.update(bias=float(delta.mean()), mae=float(np.abs(delta).mean()),
            rmse=float(np.sqrt(np.mean(delta**2))),
            ratio_of_sums=float(predicted.sum()/measured.sum()) if measured.sum() != 0 else None)
    return result


def scores_for_rows(observed, predicted):
    lookup = {p['id']: p for p in predicted}
    if len(lookup) != len(predicted) or set(lookup)-{r['id'] for r in observed}:
        raise ValueError('Duplicate or unknown prediction ID')
    result = {}
    for quantity in QUANTITIES:
        p = [lookup.get(r['id'], {}) for r in observed]
        flag = 'velocity_valid' if quantity in MEANS else 'stress_valid'
        values = [r.get(quantity, np.nan) for r in p]
        target = [r[quantity] for r in observed]
        result[quantity] = score(values, target, [r.get(flag, False) for r in p])
        if quantity not in MEANS:
            result[quantity+'_raw_diagnostic'] = score(values, target, [r.get('computed', False) for r in p])
    result['internal_k_diagnostic'] = score([lookup.get(r['id'], {}).get('internal_k', np.nan) for r in observed],
        [r['k'] for r in observed], [lookup.get(r['id'], {}).get('computed', False) for r in observed])
    return result


def summarize(observed, predicted):
    output = {}
    for group in ('suburban', 'urban_developing', 'urban_developed'):
        population = [r for r in observed if r['group'] == group]
        if not population:
            continue
        for stratum in ('all', 'below_3h', 'above_3h'):
            rows = population if stratum == 'all' else [r for r in population if r['height_stratum'] == stratum]
            ids = {r['id'] for r in rows}
            output[group+'/'+stratum] = scores_for_rows(rows, [r for r in predicted if r['id'] in ids])
    return output


def turbulence_settings(settings):
    """Read the frozen legacy protocol without requiring research-only APIs."""
    from dtcc_qes import wind
    settings = dict(settings)
    if settings.pop('covariance_model', 'legacy') != 'legacy':
        raise ValueError('This benchmark supports the production legacy covariance only')
    return wind.Turbulence(**settings)


def native_case(observed, family, dz, protocol, output):
    from dtcc_core.model import City
    from dtcc_qes import wind
    regime = observed[0]['regime']
    ref = protocol['nominal_reference_speed_m_s']
    roughness = protocol['published_parameters'][regime]['z0_m']
    if family == 'measured_mean':
        profile = wind.MeasuredProfile.from_components([r['z_m'] for r in observed],
            [r['U']*ref for r in observed], [r['V']*ref for r in observed],
            reference_height=protocol['log_anchor_height_m'], roughness_length=roughness, below='log', above='constant')
    else:
        height = protocol['log_anchor_height_m']
        profile = wind.LogProfile(float(published_log(height, regime, protocol)*ref), 270,
            reference_height=height, roughness_length=roughness)
    domain = protocol['domain']; extent = domain['horizontal_extent_m']
    result = wind.run(City(), profile, bounds=(0,0,0,extent,extent,domain['top_m']),
        resolution=domain['horizontal_spacing_m'],
        vertical_grid=wind.VerticalGrid.from_faces(vertical_faces(dz, protocol)),
        turbulence=turbulence_settings(protocol['turbulence']), solver=wind.Solver(**protocol['solver']))
    points = np.array([[extent/2,extent/2,r['z_m']] for r in observed])
    sampled = result.sample_points(points, method='linear', diagnostics=True, include_contributors=True)
    # The horizontal flow is uniform. Archive and sample a central native column
    # for scalar diagnostics, with covariance support checked independently.
    j, i = len(result.y)//2, len(result.x)//2
    fields = result.turbulence
    internal = np.interp(points[:,2], result.z, fields.tke[:,j,i])/ref**2
    mixing = np.interp(points[:,2], result.z, fields.mixing_length[:,j,i])
    diagonal = sampled.stress[:,[0,3,5]]/ref**2
    physical = .5*diagonal.sum(axis=1)
    fractions = np.divide(diagonal, diagonal.sum(axis=1)[:,None], out=np.full_like(diagonal, np.nan),
        where=diagonal.sum(axis=1)[:,None]>0)
    expected = np.column_stack(wind.evaluate(profile, result.z))
    pipeline_error = float(np.max(np.abs(result.velocity[:,1:-1,1:-1,:2]-expected[:,None,None,:])))
    divergence = result.diagnostics.max_divergence
    guards = dict(converged=result.diagnostics.converged,
        complete_geometric_support=bool(sampled.valid.all() and sampled.support.geometric.all()),
        complete_computed_support=bool(sampled.support.computed.all()),
        finite_raw_stress=bool(np.isfinite(sampled.stress).all()),
        finite_internal_energy=bool(np.isfinite(internal).all()),
        prescribed_profile_preserved=pipeline_error <= protocol['guards']['profile_pipeline_absolute_m_s'],
        interior_divergence=divergence is not None and divergence <= protocol['guards']['maximum_interior_divergence_s_inv'])
    predicted = []
    for n, row in enumerate(observed):
        r = dict(id=row['id'], station=row['station'], z_m=row['z_m'],
            velocity_valid=bool(sampled.valid[n]), computed=bool(sampled.support.computed[n]),
            stress_valid=bool(sampled.stress_valid[n]), internal_k=float(internal[n]),
            k=float(physical[n]), mixing_length_m=float(mixing[n]))
        r.update(dict(zip(MEANS, sampled.velocity[n]/ref, strict=True)))
        r.update(dict(zip(VARIANCES, diagonal[n], strict=True)))
        r.update(dict(zip(('f_u','f_v','f_w'), fractions[n], strict=True)))
        r.update(dict(zip(('xx','xy','xz','yy','yz','zz'), sampled.stress[n]/ref**2, strict=True)))
        predicted.append(r)
    output.mkdir()
    write_json(output/'run.json', dict(family=family, regime=regime, dz_m=dz,
        profile=profile.to_dict(), metadata=result.metadata, diagnostics=asdict(result.diagnostics),
        guards=guards, profile_pipeline_max_error_m_s=pipeline_error,
        support=sampled.support.to_dict(), predictions=predicted,
        station_scores={str(s): scores_for_rows([r for r in observed if r['station']==s],
            [r for r in predicted if r['station']==s]) for s in sorted({r['station'] for r in observed})}))
    np.savez_compressed(output/'column.npz', z=result.z, z_faces=result.z_faces,
        velocity=result.velocity[:,j,i], stress=fields.stress[:,j,i], internal_tke=fields.tke[:,j,i],
        computed=fields.computed[:,j,i], capped=fields.capped[:,j,i], stress_valid=fields.stress_valid[:,j,i],
        mixing_length=fields.mixing_length[:,j,i], points=points, sampled_velocity=sampled.velocity,
        sampled_stress=sampled.stress)
    return dict(name=output.name, family=family, regime=regime, dz_m=dz, guards=guards,
        profile_pipeline_max_error_m_s=pipeline_error, predictions=predicted,
        invalid_stress_observations=int((~sampled.stress_valid).sum()),
        reference=result.metadata['turbulence']['reference'],
        cap=result.metadata['turbulence']['cap'], timings=result.metadata['timings'])


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def plots(output, observed, cases):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dz = min(c['dz_m'] for c in cases)
    fig, axes = plt.subplots(2,4,figsize=(15,9),sharey=True)
    for row, station in enumerate((-10,20)):
        obs = [r for r in observed if r['station']==station]
        regime = obs[0]['regime']; z = [r['z_m'] for r in obs]
        measured = next(c for c in cases if c['family']=='measured_mean' and c['dz_m']==dz and c['predictions'][0]['station']==station)
        log = next(c for c in cases if c['family']=='public_log' and c['dz_m']==dz and c['regime']==regime)
        for ax, names in zip(axes[row], (('U',),('k',),VARIANCES,('f_u','f_v','f_w')), strict=True):
            for q in names:
                color = dict(U='C0',k='C0',uu='C0',vv='C1',ww='C2',f_u='C0',f_v='C1',f_w='C2')[q]
                ax.plot([r[q] for r in obs],z,'o',color=color,label=q+' measured')
                lookup = {r['id']:r for r in measured['predictions']}
                ax.plot([lookup[r['id']][q] for r in obs],z,'-',color=color,label=q+' imposed-mean diagnostic')
            if names == ('U',):
                lookup = {r['id']:r for r in log['predictions']}
                ax.plot([lookup[r['id']]['U'] for r in obs],z,'--',color='C3',label='public log baseline')
            if names == ('k',):
                lookup = {r['id']:r for r in measured['predictions']}
                ax.plot([lookup[r['id']]['internal_k'] for r in obs],z,':',color='C4',label='QES internal energy')
            ax.grid(alpha=.25); ax.set_title(regime+' '+('/'.join(names)))
            ax.legend(fontsize=7)
        axes[row,0].set_ylabel('Height above floor (m)')
    for ax,label in zip(axes[-1],('U/Uref','k/Uref²','Component variance/Uref²','Directional energy fraction'), strict=True):
        ax.set_xlabel(label)
    fig.suptitle('Surrey local profiles: default closure, 5 mm grid; imposed means are inputs')
    fig.tight_layout(); fig.savefig(output/'profiles.png',dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1,3,figsize=(13,4),sharey=True)
    for station in sorted({r['station'] for r in observed}):
        rows = [r for r in observed if r['station']==station]
        for ax,q in zip(axes,('U','k','f_w'),strict=True):
            ax.plot([r[q] for r in rows],[r['z_m'] for r in rows],'-o',ms=3,label=str(station))
            ax.set_xlabel(q+' normalized' if q!='f_w' else 'Vertical energy fraction'); ax.grid(alpha=.25)
    axes[0].set_ylabel('Height above floor (m)'); axes[-1].legend(title='x-hat/l_D',fontsize=7,ncol=2)
    fig.tight_layout(); fig.savefig(output/'measured_adjustment.png',dpi=170); plt.close(fig)


def run(output, protocol_path, identity_path):
    from dtcc_qes import _qes
    import dtcc_qes
    if os.environ.get('OMP_NUM_THREADS') != '1':
        raise ValueError('Run this small benchmark with OMP_NUM_THREADS=1')
    protocol = json.loads(protocol_path.read_text())
    observed = observations(protocol, ROOT/protocol['source'])
    if digest(identity_path) != _qes.solver_policy_revision:
        raise ValueError('Native binary and supplied build identity differ; rebuild/stage the current extension')
    for line in identity_path.read_text().splitlines()[1:]:
        name, expected = line.rsplit(' ',1)
        if digest(ROOT/name) != expected:
            raise ValueError('Native build source identity changed: '+name)
    package = Path(dtcc_qes.__file__).parent
    for path in (ROOT/'src/dtcc_qes').glob('*.py'):
        if digest(path) != digest(package/path.name):
            raise ValueError('Imported Python package differs from source: '+path.name)
    output.mkdir(parents=True,exist_ok=False)
    started = time.perf_counter()
    sources = {p: digest(ROOT/p) for p in ('validation/surrey_background.py',
        'validation/SURREY_BACKGROUND_PROTOCOL.md','validation/specifications/surrey_background_v1.json')}
    manifest = dict(schema='surrey-background-run-v1', protocol=protocol,
        protocol_sha256=digest(protocol_path), source_sha256=digest(ROOT/protocol['source']),
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
        sources=sources, native=dict(path=str(_qes.__file__),sha256=digest(_qes.__file__),
            policy_revision=_qes.solver_policy_revision,build_identity_sha256=digest(identity_path)),
        python_sources={p.name:digest(p) for p in package.glob('*.py')},
        environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
            omp_num_threads=os.environ.get('OMP_NUM_THREADS'),openblas_num_threads=os.environ.get('OPENBLAS_NUM_THREADS')),
        new_aij_launches=0, measured_energy_input=False, model_unit_scale=1,
        experimental_tunnel_reconstructed=False, physical_acceptance_thresholds=None)
    write_json(output/'manifest.json',manifest)
    (output/'sources').mkdir()
    for name in sources:
        dest=output/'sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    shutil.copyfile(identity_path,output/'build-identity.txt')
    write_csv(output/'observations.csv',observed)
    context=[dict(id=r['id'],U=float(published_log(r['z_m'],r['regime'],protocol))) for r in observed]
    write_csv(output/'published-log-context.csv',context)
    cases=[]
    for dz in protocol['vertical_spacings_m']:
        for family in ('public_log','measured_mean'):
            labels=('suburban','urban') if family=='public_log' else protocol['stations']
            for label in labels:
                rows=[r for r in observed if r['regime']==label] if family=='public_log' else [r for r in observed if r['station']==label]
                case=native_case(rows,family,dz,protocol,output/f'{family}-{label}-dz{dz:g}')
                cases.append(case)
                print(case['name'],'guards',all(case['guards'].values()),'invalid stresses',case['invalid_stress_observations'],flush=True)
    metrics={}; predictions=[]; grids={}
    for family in ('public_log','measured_mean'):
        for dz in protocol['vertical_spacings_m']:
            rows=[r for c in cases if c['family']==family and c['dz_m']==dz for r in c['predictions']]
            metrics[f'{family}/dz{dz:g}']=summarize(observed,rows)
            predictions += [dict(family=family,dz_m=dz,**r) for r in rows]
        coarse,fine=([r for c in cases if c['family']==family and c['dz_m']==dz for r in c['predictions']]
            for dz in sorted(protocol['vertical_spacings_m'],reverse=True))
        lookup={r['id']:r for r in coarse}
        grids[family]={q:score([r[q] for r in fine],[lookup[r['id']][q] for r in fine],
            [r['velocity_valid'] and lookup[r['id']]['velocity_valid'] if q in MEANS else
             r['stress_valid'] and lookup[r['id']]['stress_valid'] for r in fine]) for q in QUANTITIES}
    write_csv(output/'predictions.csv',predictions)
    context_lookup={r['id']:r['U'] for r in context}
    report=dict(schema='surrey-background-results-v1',observations=len(observed),stations=len(protocol['stations']),
        native_solves=len(cases),numerical_guards_pass=all(all(c['guards'].values()) for c in cases),
        physical_qualification=False,pedestrian_qualification=False,
        metrics=metrics,paired_grid_changes=grids,
        published_log_context={g:score([context_lookup[r['id']] for r in observed if r['group']==g],
            [r['U'] for r in observed if r['group']==g],[True for r in observed if r['group']==g])
            for g in ('suburban','urban_developing','urban_developed')},
        cases=[{k:v for k,v in c.items() if k!='predictions'} for c in cases],
        wall_seconds=time.perf_counter()-started)
    write_json(output/'report.json',report)
    plots(output,observed,cases)
    write_json(output/'checksums.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    if not report['numerical_guards_pass']:
        raise ValueError('Benchmark execution guards failed; evidence retained')
    print('Complete:',len(observed),'observations;',len(cases),'native solves;',round(report['wall_seconds'],3),'s',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol',type=Path,default=PROTOCOL)
    p.add_argument('--build-identity',type=Path,required=True)
    args=p.parse_args();run(args.output,args.protocol,args.build_identity)


if __name__=='__main__':
    main()
