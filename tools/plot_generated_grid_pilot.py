"""Plot fixed-x/y vertical comparisons, cell counts and observed worker memory."""
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from run_joint_grid_verification import atomic_json, read


def main():
    root=Path('docs/data/generated-grid-pilot')
    summary=read(root/'summary.json')
    if not summary['complete']: raise ValueError('Require complete pilot before plotting')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
    colors={'serial':'#2563a6','openmp':'#cf640a'}
    for backend,offset in (('serial',-.12),('openmp',.12)):
        data=summary['backends'][backend]
        rows=[r for r in data['comparisons'] if r['region']=='all']
        maxima=[]
        for row in rows:
            if not row['matched_accuracy']: raise ValueError('Plot cannot use failed solves')
            # The selected fixture's mandatory reference K values all exceed .1.
            rel=[p['relative_difference'] for p in row['mandatory_local_checks']]
            if any(v is None for v in rel): raise ValueError('Need separate low-speed plot')
            maxima.append(100*max(rel))
        axes[0].plot(np.arange(len(rows))+offset,maxima,'o',label=backend,color=colors[backend])
        costs=sorted(data['runs'],key=lambda r:r['extent'])
        axes[2].bar(np.arange(2)+offset,[r['peak_rss_bytes']/1e9 for r in costs],width=.23,
                    label=backend,color=colors[backend])
    labels=[r['comparison'].replace('vertical_at_','z @ ').replace('generated_extent_160_to_240','extent')+
            f"\n{r['height']:g} m" for r in rows]
    axes[0].set_xticks(range(6),labels,rotation=30,ha='right')
    axes[0].axhline(5,color='black',linestyle='--',label='5% local budget')
    axes[0].set_ylabel('Largest mandatory local relative K change (%)')
    axes[0].set_title('All three near-wall points retained'); axes[0].legend(fontsize=8)
    x=np.arange(2)
    axes[1].bar(x-.18,[r['cells']/1e6 for r in costs],width=.36,label='generated (92 layers)',color='#2563a6')
    axes[1].bar(x+.18,[r['reference_cells']/1e6 for r in costs],width=.36,label='uniform (128 layers)',color='#868e96')
    axes[1].set_xticks(x,['160 m','240 m']); axes[1].set_ylabel('Physical cells (millions)')
    axes[1].set_title('28.1% cell reduction'); axes[1].legend(fontsize=8)
    axes[2].set_xticks(x,['160 m','240 m']); axes[2].set_ylabel('Maximum generated-grid worker RSS (GB)')
    axes[2].set_title('Observed memory; native study worker'); axes[2].legend(fontsize=8)
    for ax in axes: ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True)
    fig.suptitle('Generated z at x/y = 0.5 m • tower / 270°\nVertical agreement does not qualify horizontal or physical comfort accuracy')
    target=root/'pilot.png'; fig.savefig(target,dpi=160); plt.close(fig)
    sources=[root/'summary.json',root/'manifest.json',Path(__file__)]
    atomic_json(root/'figure.json',dict(inputs_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        image_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))


if __name__=='__main__':
    main()
