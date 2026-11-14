"""The x3 tower-effect diagnostic, reading current immutable validation archives."""
import argparse
from pathlib import Path
import numpy as np
import shapely
from aij import campaigns, compare, conventions, runner, cityutil


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    args=parser.parse_args()
    records=compare.load_records(args.archive/'runs',campaigns.baseline(2.))
    comparisons={c.name:c for c in compare.case_e_comparisons(records)}
    before=comparisons['E-before-thermistor-K'];after=comparisons['E-after-thermistor-K']
    rb=cityutil.footprints(runner.city('E','before'));ra=cityutil.footprints(runner.city('E','after'))
    union=shapely.unary_union([p for _,p,_ in rb])
    new=[(p,h) for _,p,h in ra if p.difference(union.buffer(.5)).area>.5*p.area]
    tower=max(new,key=lambda item:item[1])[0];centre=np.array(tower.centroid.coords[0])
    record=next(r for (case,state,label),r in records.items() if case=='E' and state=='after')
    ids=list(record['probes']['ids']);xyz=np.asarray(record['probes']['xyz'])
    xy=xyz[[ids.index(i) for i in after.ids],:2]
    dist=np.array([shapely.Point(*p).distance(tower) for p in xy])
    delta=after.simulated-before.simulated;measured=after.measured-before.measured
    flow=conventions.flow_vector(after.directions)
    rel=xy[:,None,:]-centre[None,None,:];along=(rel*flow[None]).sum(-1)
    cross=np.abs(rel[...,0]*flow[None,:,1]-rel[...,1]*flow[None,:,0])
    near=np.broadcast_to((dist<30)[:,None],delta.shape)
    for name,mask in [('within 30 m',near),('upwind',near&(along<-10)&(cross<25)),
                      ('beside',near&(np.abs(along)<25)&(cross>10)&(cross<50)),
                      ('downwind',near&(along>10)&(cross<25))]:
        valid=mask&np.isfinite(delta)&np.isfinite(measured)
        print(name,'pairs',valid.sum(),'measured',np.mean(measured[valid]),'simulated',np.mean(delta[valid]))


if __name__=='__main__':main()
