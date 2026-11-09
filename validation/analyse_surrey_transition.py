"""Data-only geometry, profile and exact-height increment review of Surrey runs."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from benchmark_evidence import digest,write_json
from surrey_background import ROOT,QUANTITIES,observations,score,summarize,write_csv


def difference(a,b):
    return float(a-b) if a is not None and b is not None else float('nan')


def shared_increments(observed,predicted):
    """Use only identical measured heights; never invent an upstream value."""
    upstream={r['Z_mm']:r for r in observed if r['station']==-10}
    lookup={r['id']:r for r in predicted}
    if len(lookup)!=len(predicted) or set(lookup)!={r['id'] for r in observed}:
        raise ValueError('Increment prediction IDs differ from the frozen population')
    targets=[];values=[]
    for row in observed:
        if row['station']==-10 or row['Z_mm'] not in upstream:continue
        base=upstream[row['Z_mm']];a,b=lookup[row['id']],lookup[base['id']]
        target=dict(row,upstream_id=base['id'])
        target.update({q:row[q]-base[q] for q in QUANTITIES})
        predicted_row=dict(id=row['id'],upstream_id=base['id'],station=row['station'],z_m=row['z_m'],
            velocity_valid=a['velocity_valid'] and b['velocity_valid'],
            computed=a['computed'] and b['computed'],stress_valid=a['stress_valid'] and b['stress_valid'],
            internal_k=difference(a['internal_k'],b['internal_k']))
        predicted_row.update({q:difference(a[q],b[q]) for q in QUANTITIES})
        targets.append(target);values.append(predicted_row)
    return targets,values


def station_variation(observed,predicted):
    lookup={r['id']:r for r in predicted};result={}
    for height in (.09,.12):
        rows=[r for r in observed if r['station'] in (8,9,15,20) and r['z_m']==height]
        a=np.array([r['U'] for r in rows]);b=np.array([lookup[r['id']]['U'] for r in rows])
        result[str(height)]=dict(stations=[r['station'] for r in rows],
            measured_peak_to_peak_over_mean=float(np.ptp(a)/a.mean()),
            predicted_peak_to_peak_over_mean=float(np.ptp(b)/b.mean()),
            measured_maximum_deviation_from_mean=float(np.max(np.abs(a/a.mean()-1))),
            predicted_maximum_deviation_from_mean=float(np.max(np.abs(b/b.mean()-1))),measured=a,predicted=b)
    return result


def plots(output,campaign,observed,runs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(2,1,figsize=(13,6),sharex=True)
    for ax,name in zip(axes,('street-coarse','block-coarse'),strict=True):
        g=json.loads((campaign/name/'geometry.json').read_text());b=g['requested_bounds']
        for r in g['blocks']:
            ax.add_patch(Rectangle((r['xmin'],r['ymin']),r['xmax']-r['xmin'],r['ymax']-r['ymin'],facecolor='.65',edgecolor='.25',lw=.5))
        ax.scatter([r['x_hat_m'] for r in observed],[r['y_m'] for r in observed],s=12,c='C3',zorder=4)
        ax.axvline(0,color='C0',ls='--');ax.axhline(0,color='C3',lw=.6)
        ax.set_xlim(b[0],b[3]);ax.set_ylim(b[1],b[4]);ax.set_aspect('equal');ax.set_ylabel('y (m)');ax.set_title(name+'; dots: profile stations')
    axes[-1].set_xlabel('x-hat from start of Urban blocks (m)')
    fig.tight_layout();fig.savefig(output/'geometry.png',dpi=170);plt.close(fig)
    names=('empty-fine','street-fine','block-fine','street-wide')
    colors=dict(zip(names,('C0','C1','C2','C4'),strict=True))
    fig,axes=plt.subplots(2,3,figsize=(13,9),sharey=True)
    for line,station in enumerate((3,20)):
        rows=[r for r in observed if r['station']==station]
        for ax,q in zip(axes[line],('U','W','k'),strict=True):
            ax.plot([r[q] for r in rows],[r['z_m'] for r in rows],'ko',label='measured')
            for name in names:
                if name not in runs:continue
                lookup={r['id']:r for r in runs[name]['predictions']}
                values=[lookup[r['id']][q] for r in rows]
                ax.plot(values,[r['z_m'] for r in rows],color=colors[name],label=name)
                if q=='k':
                    bad=[r for r in rows if not lookup[r['id']]['stress_valid']]
                    ax.scatter([lookup[r['id']][q] for r in bad],[r['z_m'] for r in bad],marker='x',c=colors[name],s=60,zorder=5)
            ax.grid(alpha=.25);ax.set_xlabel(q+'/Uref' if q!='k' else 'Physical k/Uref² (cross: invalid covariance)')
            ax.set_title(f'x-hat/l_D={station}');ax.legend(fontsize=8)
        axes[line,0].set_ylabel('Height above floor (m)')
    fig.tight_layout();fig.savefig(output/'profiles.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,8))
    for line,height in enumerate((.09,.12)):
        rows=[r for r in observed if r['station']>0 and r['z_m']==height]
        for ax,q in zip(axes[line],('U','W','k'),strict=True):
            ax.plot([r['station'] for r in rows],[r[q] for r in rows],'ko-',label='measured')
            for name in names:
                if name not in runs:continue
                lookup={r['id']:r for r in runs[name]['predictions']}
                ax.plot([r['station'] for r in rows],[lookup[r['id']][q] for r in rows],'-o',ms=3,color=colors[name],label=name)
            ax.grid(alpha=.25);ax.set_xlabel('x-hat/l_D');ax.set_ylabel(q+' normalized');ax.set_title(f'z={height*1000:g} mm')
    axes[0,0].legend(fontsize=8);fig.tight_layout();fig.savefig(output/'fetch_response.png',dpi=170);plt.close(fig)
    if 'street-fine' in runs:
        with np.load(campaign/'street-fine/fields.npz') as a:
            fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,sharey=True)
            for ax,component,label in zip(axes,(0,2),('U/Uref','W/Uref'),strict=True):
                field=np.where(a['valid'],a['velocity'][:,:,component]/2,np.nan)
                image=ax.pcolormesh(a['x'],a['z'],field,shading='nearest',cmap='viridis' if component==0 else 'coolwarm')
                ax.scatter([r['x_hat_m'] for r in observed],[r['z_m'] for r in observed],s=5,c='k')
                ax.set_ylabel('z (m)');fig.colorbar(image,ax=ax,label=label)
            axes[-1].set_xlabel('x-hat (m)');fig.tight_layout();fig.savefig(output/'street_centreline.png',dpi=170);plt.close(fig)


def analyse(campaign,output):
    checks=json.loads((campaign/'checksums.json').read_text())
    for name,sha in checks.items():
        if digest(campaign/name)!=sha:raise ValueError('Campaign evidence changed: '+name)
    manifest=json.loads((campaign/'manifest.json').read_text());protocol=manifest['protocol']
    background=json.loads((ROOT/protocol['background_protocol']).read_text())
    observed=observations(background,ROOT/background['source'])
    ledger=json.loads((campaign/'ledger.json').read_text())
    runs={e['name']:json.loads((campaign/e['name']/'worker.json').read_text()) for e in ledger if e['complete']}
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(__file__,output/'analysis-source.py')
    increments={};increment_rows=[];variation={};summary=[];reference_support={}
    for name,r in runs.items():
        target,predicted=shared_increments(observed,r['predictions'])
        increments[name]=summarize(target,predicted);variation[name]=station_variation(observed,r['predictions'])
        increment_rows.extend(dict(run=name,**p) for p in predicted)
        if name==next(iter(runs)):write_csv(output/'increment-observations.csv',target)
        row=dict(name=name,execution_guards_pass=all(r['guards'].values()),
            wall_seconds=r['wall_seconds'],peak_rss_bytes=r['peak_rss_bytes'],invalid_stress_observations=r['invalid_stress_observations'])
        for group in ('urban_developing','urban_developed'):
            m=r['scores'][group+'/all'];delta=increments[name][group+'/all']
            row.update({group+'_U_rmse':m['U'].get('rmse'),group+'_W_rmse':m['W'].get('rmse'),
                group+'_k_ratio':m['k'].get('ratio_of_sums'),group+'_k_raw_ratio':m['k_raw_diagnostic'].get('ratio_of_sums'),
                group+'_increment_U_rmse':delta['U'].get('rmse'),group+'_increment_W_rmse':delta['W'].get('rmse'),
                group+'_increment_k_rmse':delta['k'].get('rmse')})
        summary.append(row)
        if r['metadata'].get('turbulence'):
            reference=r['metadata']['turbulence']['reference']
            # Native frictionVelocity uses lower_bound on faces, then the cell
            # above that face. Float32 face accumulation and mean height matter.
            with np.load(campaign/name/'fields.npz') as fields:
                index=int(np.searchsorted(fields['z_faces'],reference['height']))
                reference_support[name]=dict(reference,
                    effective_sample_face_m=float(fields['z_faces'][index]),
                    effective_sample_centre_m=float(fields['grid_z'][index]),
                    physical_cell_index=index,
                    capped_observations=sum(p['capped_source_weight']>0 for p in r['predictions']))
    write_csv(output/'summary.csv',summary);write_csv(output/'increment-predictions.csv',increment_rows)
    write_json(output/'report.json',dict(schema='surrey-transition-analysis-v1',
        campaign_manifest_sha256=digest(campaign/'manifest.json'),campaign_checksums_sha256=digest(campaign/'checksums.json'),
        script_sha256=digest(__file__),verified_campaign_files=len(checks),summary=summary,
        shared_increment_heights_m=sorted({r['z_m'] for r in target}),increment_population_per_run=len(target),
        increments=increments,station_variation=variation,reference_support=reference_support,physical_qualification=False))
    plots(output,campaign,observed,runs)
    write_json(output/'checksums.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    print('Analysed',len(runs),'runs;',len(target),'exact-height increment targets per run')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyse(a.campaign,a.output)


if __name__=='__main__':main()
