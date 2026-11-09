"""Data-only summary and plots for the native reference-sampling investigation."""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from benchmark_evidence import digest,write_json
from surrey_background import write_csv


def analyse(study,output):
    checks=json.loads((study/'checksums.json').read_text())
    for name,sha in checks.items():
        if digest(study/name)!=sha:raise ValueError('Study evidence changed: '+name)
    report=json.loads((study/'report.json').read_text());cases={r['name']:r for r in report['cases']}
    output.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,output/'analysis-source.py')
    table=[];grid={};effects={}
    for name,c in cases.items():
        for arm,a in c['arms'].items():
            row=dict(case=name,arm=arm,declared_height_m=c['reference_height'],legacy_height_m=c['legacy_height'],
                reference_speed_m_s=a['speed'],friction_velocity_m_s=a['friction_velocity'],bound_m2_s2=a['bound'],
                bound_relative_change=a['bound']/c['arms']['legacy']['bound']-1,
                invalid_sources=a['invalid_sources'],invalid_probes=a['invalid_probes'])
            for group in ('urban_developing','urban_developed'):
                m=a['scores'][group+'/all'];row[group+'_k_ratio']=m['k'].get('ratio_of_sums')
                row[group+'_k_raw_ratio']=m['k_raw_diagnostic'].get('ratio_of_sums');row[group+'_k_rmse']=m['k'].get('rmse')
            table.append(row)
        with np.load(study/name/'replays.npz') as arrays:
            old=arrays['legacy_sources'];new=arrays['interpolate_wide_sources']
            effects[name]=dict(source_instances=len(old),changed_sources=int(np.any(old!=new,axis=1).sum()),
                maximum_source_component_change=float(np.max(np.abs(old-new))),
                sampled_stresses_bitwise_equal=bool(np.array_equal(arrays['legacy_sampled'],arrays['interpolate_wide_sampled'])))
    for layout in ('empty','street','block'):
        a,b=cases[layout+'-coarse'],cases[layout+'-fine'];grid[layout]={}
        for arm in a['arms']:
            x,y=a['arms'][arm],b['arms'][arm]
            grid[layout][arm]=dict(reference_speed_relative_gap=x['speed']/y['speed']-1,
                bound_relative_gap=x['bound']/y['bound']-1,
                developed_k_relative_gap=(x['scores']['urban_developed/all']['k']['ratio_of_sums']/y['scores']['urban_developed/all']['k']['ratio_of_sums']-1)
                    if x['scores']['urban_developed/all']['k']['complete'] and y['scores']['urban_developed/all']['k']['complete'] else None)
    write_csv(output/'summary.csv',table)
    write_json(output/'report.json',dict(schema='reference-sampling-analysis-v1',verified_files=len(checks),
        study_checksums_sha256=digest(study/'checksums.json'),analysis_sha256=digest(__file__),
        summary=table,grid_comparisons=grid,source_effects=effects,physical_qualification=False,default_reference_changed=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4))
    m=report['manufactured']
    for field in ('affine','curved'):
        rows=m['errors'][field];h=np.array([float(k) for k in rows])
        axes[0].loglog(h,[v['legacy_max_error'] for v in rows.values()],'o--',label=field+' legacy')
        axes[0].loglog(h,[v['candidate_max_error'] for v in rows.values()],'o-',label=field+' interpolation')
    axes[0].set_xlabel('Vertical spacing (m)');axes[0].set_ylabel('Point speed error (m/s)');axes[0].legend(fontsize=7)
    raw=json.loads((study/'manufactured.json').read_text())
    rows=[r for r in raw['cases'] if r['field']=='affine' and r['spacing']==.0175]
    axes[1].plot([r['face_phase'] for r in rows],[r['legacy_float_mean'] for r in rows],'o-',label='legacy')
    axes[1].plot([r['face_phase'] for r in rows],[r['interpolation']['double_mean'] for r in rows],'o-',label='interpolation')
    axes[1].set_xlabel('Face perturbation (micrometres)');axes[1].set_ylabel('Reference speed (m/s)');axes[1].legend()
    const=raw['constant_reductions']
    for key,label in (('float_mean','float32 sum'),('double_mean','float64 sum before export')):
        axes[2].loglog([r['columns'] for r in const],[abs(r[key]-r['oracle']) for r in const],'o-',label=label)
    axes[2].set_xlabel('Horizontal columns');axes[2].set_ylabel('Constant-field mean error (m/s)');axes[2].legend(fontsize=7)
    for ax in axes:ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(output/'manufactured.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    labels=('Reference speed','Turbulence cap','Developed physical k')
    keys=('reference_speed_relative_gap','bound_relative_gap','developed_k_relative_gap');positions=np.arange(3)
    for offset,arm in ((-.18,'legacy'),(.18,'interpolate_wide')):
        axes[0].bar(positions+offset,[100*abs(grid['street'][arm][k]) for k in keys],width=.36,label=arm)
    axes[0].set_xticks(positions,labels);axes[0].set_ylabel('Absolute coarse/fine difference (%)');axes[0].legend()
    names=('empty-coarse','empty-fine','street-coarse','street-fine');positions=np.arange(4)
    for offset,arm in ((-.18,'legacy'),(.18,'interpolate_wide')):
        axes[1].bar(positions+offset,[cases[n]['arms'][arm]['scores']['urban_developed/all']['k']['ratio_of_sums'] for n in names],width=.36,label=arm)
    axes[1].set_xticks(positions,names,rotation=20);axes[1].set_ylabel('Developed physical k: predicted/measured');axes[1].axhline(1,color='k',ls=':');axes[1].legend()
    for ax in axes:ax.grid(axis='y',alpha=.25)
    fig.tight_layout();fig.savefig(output/'surrey_effect.png',dpi=170);plt.close(fig)
    write_json(output/'checksums.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    print('Summarized',len(cases),'fixed means and',len(table),'reference arms')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyse(a.study,a.output)


if __name__=='__main__':main()
