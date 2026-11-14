import numpy as np, logging
logging.disable(logging.CRITICAL)
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind
def city(h=20.):
    c=City(); b=Building(id="b"); b.measured_height=h
    b.add_geometry(Surface(vertices=np.array([[90.,90,0],[90,110,0],[110,110,0],[110,90,0]])),GeometryType.LOD0)
    c.add_building(b); return c
idx=[0,1,2,5,10,20,30,37]
for name,p in (("power0.25",wind.PowerLawProfile(5.,270.,10.,0.25)),("uniform",wind.UniformProfile(5.,270.))):
  try:
    r=wind.run(city(),p,resolution=2.,bounds=(0,0,0,200,200,80),turbulence=wind.Turbulence("height"))
  except Exception as e:
    print(name,"ERR",e); continue
  s=r.streamwise_std; sp=np.linalg.norm(r.velocity,axis=-1); t=r.metadata["turbulence"]
  print(name,"u*",t["reference"]["friction_velocity"],"cap",t["cap"]["value"],"capped",t["cap"]["capped_cells"])
  print("  z",r.z[idx],"U",np.round(sp[idx,5,5],2),"sigma",np.round(s[idx,5,5],2),"TI",np.round((s/sp)[idx,5,5],3))
  sm=r.sample(1.5,"linear"); print("  ped sigma p50 %.3f min %.3f frac TI<0.05 %.2f"%(np.nanmedian(sm.streamwise_std),np.nanmin(sm.streamwise_std),np.nanmean(sm.turbulence_intensity<0.05)))
