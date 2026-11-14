"""Archive the wind-comfort example's directional gust-equivalent-mean maps."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'examples'))
from wind_comfort import directional_results,example_city,PEDESTRIAN_HEIGHT,PEAK_FACTOR,GUST_RATIO
from dtcc_qes import comfort,_qes
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    directions=np.arange(0.,360.,30.)
    results=directional_results(example_city(),directions)
    fields=[];invalid=[]
    fig,axes=plt.subplots(3,4,figsize=(12,8),constrained_layout=True)
    for direction,result,ax in zip(directions,results,axes.flat):
        sample=result.sample(PEDESTRIAN_HEIGHT,'linear')
        gem=comfort.gust_equivalent_mean(sample.speed,sample.streamwise_std,peak_factor=PEAK_FACTOR,gust_ratio=GUST_RATIO)
        fields.append(gem)
        layer=int(np.argmin(abs(result.z-PEDESTRIAN_HEIGHT)))
        computed=result.turbulence.computed[layer]
        invalid.append(float(np.mean(~result.turbulence.stress_valid[layer][computed])))
        plot=ax.pcolormesh(result.x,result.y,gem,vmin=0,vmax=8,shading='nearest',cmap='viridis')
        ax.set_title(f'{direction:g} degrees');ax.set_aspect('equal')
    fig.colorbar(plot,ax=axes.ravel().tolist(),label='Gust-equivalent mean (m/s)')
    fig.savefig(args.output/'gust-equivalent-mean.png',dpi=150);plt.close(fig)
    np.savez_compressed(args.output/'fields.npz',directions=directions,x=results[0].x,y=results[0].y,gem=fields,
                        nonrealizable_share=invalid)
    (args.output/'metadata.json').write_text(json.dumps(dict(height=PEDESTRIAN_HEIGHT,
        native_sha256=hashlib.sha256(Path(_qes.__file__).read_bytes()).hexdigest(),
        nonrealizable_share=invalid,peak_factor=PEAK_FACTOR,gust_ratio=GUST_RATIO),indent=2)+'\n')
    print(args.output,'non-realizable share per direction',invalid)


if __name__=='__main__':main()
