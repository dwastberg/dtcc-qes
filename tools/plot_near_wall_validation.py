"""Plot fixed-point diagnostics and the independently checked sidewall branch."""
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator
import numpy as np

from run_joint_grid_verification import atomic_json, read
from diagnose_sidewall_transition import initialized_ratio


def main():
    root=Path("docs/data/near-wall-validation")
    summary=read(root/"summary.json")
    if not summary["complete"]: raise ValueError("Require complete diagnostic matrix")
    fig,axes=plt.subplots(2,3,figsize=(12,6),layout="constrained")
    for row,stage in enumerate(("initial","final")):
        for col,point in enumerate(([27,21],[21,23],[51,35])):
            ax=axes[row,col]
            for method,color in (("centred","#225ea8"),("staggered","#d95f0e")):
                for height,style in ((1.5,"-"),(1.75,"--")):
                    chosen=[r for r in summary["points"] if r["task"]["backend"]=="openmp"
                        and r["task"]["family"]=="auto" and r["task"]["direction"]==270
                        and r["task"]["disabled"]==0 and r["stage"]==stage
                        and bool(r["task"]["sweeps"])==(stage=="final") and r["point"]==[*point,height]]
                    chosen.sort(key=lambda r:-r["task"]["resolution"])
                    ax.plot([r["task"]["resolution"] for r in chosen],
                            [np.linalg.norm(r["vectors"][method])/5 for r in chosen],style+"o",
                            color=color,label=f"{method}, {height:g} m")
            ax.set(xscale="log",xlim=(1.1,.22),xticks=[1,.5,.25],title=f"{stage.capitalize()}: ({point[0]}, {point[1]})",
                   xlabel="Horizontal spacing (m)",ylabel="K = |mean vector| / Uref")
            ax.set_xticklabels(["1","0.5","0.25"]); ax.grid(alpha=.2)
            ax.xaxis.set_minor_locator(NullLocator())
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=4)
    fig.suptitle("Near-wall point diagnosis • automatic z, 270°, 160 m extent\n0.25 m values are initialization only")
    fig.savefig(root/"point-comparison.png",dpi=160); plt.close(fig)

    transition=read(root/"sidewall-transition.json")
    c=transition["scales"]; shell=c["shell"]
    fig,ax=plt.subplots(figsize=(9,4.5),layout="constrained")
    for x in (np.linspace(.4,shell,150),np.linspace(shell+1e-9,1.6,150)):
        ax.plot(x,[initialized_ratio(v,c) for v in x],color="black",lw=1.5)
    ax.plot([shell,shell],[0,transition["shell_outer_limit_ratio"]],":",color="black")
    for resolution,color,marker in ((1,"#7570b3","s"),(.5,"#1b9e77","o"),(.25,"#d95f02","^")):
        rows=[r for r in transition["raw_face_checks"] if r["resolution"]==resolution]
        ax.scatter([r["distance_from_wall"] for r in rows],[r["initialized_u_over_profile_u"] for r in rows],
                   label=f"Native faces, {resolution:g} m grid",color=color,marker=marker,zorder=3)
    ax.axvline(1,color="#225ea8",ls="--",label="Requested point: 1 m from wall")
    ax.annotate("Branch jump at 0.974 m\npoint only 0.026 m outside",xy=(shell,.48),xytext=(.45,.55),
                arrowprops=dict(arrowstyle="->",color=".3"))
    ax.set(xlabel="Distance from side wall (m)",ylabel="Initialized u / profile u",xlim=(.4,1.6),
           title="Native sidewall initialization at x=27 m, z=1.5 m\nSource formula checked against exported faces; not a solved wind profile")
    ax.grid(alpha=.2); ax.legend(loc="lower right",fontsize=9)
    fig.savefig(root/"sidewall-transition.png",dpi=160); plt.close(fig)
    inputs=[root/"summary.json",root/"sidewall-transition.json",Path(__file__),Path("tools/diagnose_sidewall_transition.py")]
    outputs=[root/"point-comparison.png",root/"sidewall-transition.png"]
    atomic_json(root/"figures.json",dict(input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        output_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}))


if __name__=="__main__": main()
