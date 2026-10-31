"""Plot solve residuals, analytical sampling bias and accepted fixed-point fields."""
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator
import numpy as np
from run_vertical_refinement import audit_point, gate, read, reference_data
from run_joint_grid_verification import atomic_json


def main():
    root=Path('docs/data/vertical-refinement')
    manifest=read(root/'manifest.json');summary=read(root/'summary.json');raw=read(root/'raw.json.gz')
    if not summary['complete']:raise ValueError('Require completed bounded matrix')
    refs,_=reference_data(manifest['references_sha256'])
    runs={'base':refs['openmp']['base'],**{r['task']['family']:r for r in raw['openmp']['runs']}}
    colors={'base':'#666666','split-2':'#2563a6','split-4':'#b34028','aligned-1.75':'#25825c'}
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    residual_ax,bias_ax=axes[0];field_axes=axes[1]
    for family in ('split-2','split-4','aligned-1.75'):
        records=[r for r in raw['openmp']['attempts']+raw['openmp']['runs'] if r['task']['family']==family]
        points={c['iterations']:(max(c['max_divergence']*r['hmax']/5/1e-3,
                                     c['rms_divergence']*r['hmax']/5/1e-4)) for r in records for c in r['checkpoints']}
        residual_ax.plot(sorted(points),[points[i] for i in sorted(points)],'o-',color=colors[family],label=family)
    residual_ax.axhline(1,color='black',linestyle='--',label='residual limits')
    residual_ax.set(xscale='log',yscale='log',xlabel='Independent zero-start sweeps',
                    ylabel='Largest scaled residual / its limit',title='All executed residual checkpoints')
    residual_ax.set_xticks([8000,16000,32000,64000],['8k','16k','32k','64k'])
    residual_ax.xaxis.set_minor_locator(NullLocator())
    residual_ax.legend(fontsize=8)
    families=('base','split-2','split-4','aligned-1.75');x=np.arange(4)
    for height,offset,color in ((1.5,-.18,'#2563a6'),(1.75,.18,'#b34028')):
        bias_ax.bar(x+offset,[abs(summary['flat_profile'][f][str(height)]['bias_K']) for f in families],
                    width=.35,label=f'{height:g} m',color=color)
    bias_ax.set_xticks(x,['92 base','184 split','368 split','92 aligned'])
    bias_ax.set(ylabel='Absolute interpolation bias K',title='Analytical log profile; no flow correction')
    bias_ax.legend(fontsize=8)
    for ax,height,point in zip(field_axes,(1.5,1.75),([15,47],[15,29])):
        yy=[]
        for family in ('base','split-2','split-4'):
            r=runs[family]
            if gate(r)['accepted']:
                p=audit_point(r,height,point,'final');yy.append(p['K'] if p['valid'] else np.nan)
            else:yy.append(np.nan)
        ax.plot([1,2,4],yy,'o-',color='#2563a6',label='systematic subdivisions')
        aligned=runs['aligned-1.75']
        if gate(aligned)['accepted']:
            p=audit_point(aligned,height,point,'final')
            ax.plot([1],[p['K'] if p['valid'] else np.nan],'*',markersize=13,color=colors['aligned-1.75'],label='same-count alignment')
        for q,value in zip((1,2,4),yy):
            if not np.isfinite(value):ax.text(q,.05,'withheld',transform=ax.get_xaxis_transform(),ha='right' if q==4 else 'center',color='#b34028')
        ax.set_xticks([1,2,4],['92','184','368'])
        ax.set(xlabel='Vertical layers',ylabel='K = mean vector speed / Uref',
               title=f'Accepted fields only: {tuple(point)}, {height:g} m')
        ax.legend(fontsize=8)
    for ax in axes.ravel():ax.grid(alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Vertical refinement and native centre alignment • fixed x/y = 0.5 m\nTower / 270° / 160 m extent • prescribed failures retained')
    image=root/'refinement.png';fig.savefig(image,dpi=160);plt.close(fig)
    inputs=[root/name for name in ('manifest.json','summary.json','raw.json.gz')]+[Path(__file__)]
    atomic_json(root/'figure.json',dict(inputs_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        image_sha256=hashlib.sha256(image.read_bytes()).hexdigest()))


if __name__=='__main__':main()
