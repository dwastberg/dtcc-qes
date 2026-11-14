import numpy as np, logging, time
logging.disable(logging.CRITICAL)
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind
c=City()
for n,(x,y) in enumerate([(60,60),(100,60),(140,60),(60,120),(100,120),(140,120)]):
    b=Building(id=str(n)); b.measured_height=20.
    b.add_geometry(Surface(vertices=np.array([[x,y,0.],[x,y+30,0],[x+20,y+30,0],[x+20,y,0]])),GeometryType.LOD0); c.add_building(b)
for turb in (None,wind.Turbulence("height"),wind.Turbulence("wall_distance")):
    best=1e9
    for _ in range(2):
        t=time.perf_counter(); r=wind.run(c,speed=5.,direction=250.,resolution=1.,bounds=(0,0,0,220,220,80),turbulence=turb); best=min(best,time.perf_counter()-t)
    tm={k:v for k,v in r.metadata.items() if "tim" in k.lower()}
    print(None if turb is None else turb.mixing_length, "cells",r.velocity.shape,"wall %.2fs"%best, tm if tm else "")
sm=r.sample(1.5,"linear"); print("canyon case: invalid-stress frac of fluid ped cells %.3f; capped %d of %d"%(np.mean(~sm.stress_valid[sm.valid]),r.metadata["turbulence"]["cap"]["capped_cells"],r.metadata["turbulence"]["cap"]["computed_cells"]))
