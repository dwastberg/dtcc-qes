import numpy as np, logging
logging.disable(logging.CRITICAL)
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind
def city(h=20.):
    c=City(); b=Building(id="b"); b.measured_height=h
    b.add_geometry(Surface(vertices=np.array([[90.,90,0],[90,110,0],[110,110,0],[110,90,0]])),GeometryType.LOD0)
    c.add_building(b); return c
for ml in ("height","wall_distance"):
    r=wind.run(city(),speed=5.,direction=270.,resolution=2.,bounds=(0,0,0,200,200,80),turbulence=wind.Turbulence(ml))
    t=r.metadata["turbulence"]; bound=t["cap"]["value"]
    s=r.streamwise_std; sp=np.linalg.norm(r.velocity,axis=-1)
    over=s**2>bound*1.001
    k,j,i=np.unravel_index(np.nanargmax(s),s.shape)
    print(ml,"cells sigma^2>bound:",over.sum(),"by layer",over.sum(axis=(1,2))[:14])
    print("  max sigma %.2f at z=%.0f y=%.0f x=%.0f speed %.2f stress"%(s[k,j,i],r.z[k],r.y[j],r.x[i],sp[k,j,i]),np.round(r.turbulence.stress[k,j,i]/bound,2), "Lm",r.turbulence.mixing_length[k,j,i])
    for h in (1.5,1.75):
        sm=r.sample(h,"linear"); ss=sm.streamwise_std; gem=(sm.speed+3*ss)/1.85
        print("  h",h,"sigma p50 %.2f p99 %.2f max %.2f | speed max %.2f | GEM max %.2f at speed %.2f sigma %.2f | frac GEM>mean %.2f"%(np.nanmedian(ss),np.nanpercentile(ss,99),np.nanmax(ss),np.nanmax(sm.speed),np.nanmax(gem),sm.speed.flat[np.nanargmax(gem)],ss.flat[np.nanargmax(gem)],np.nanmean(gem>sm.speed)))
        jj,ii=np.unravel_index(np.nanargmax(ss),ss.shape); print("    max sigma at x=%.0f y=%.0f"%(sm.x[ii],sm.y[jj]), "invalid stress frac among fluid %.4f"%(np.mean(~sm.stress_valid[sm.valid])))
# power law profile aloft, no building influence: far upstream column
try:
    p=wind.PowerLawProfile(5.,270.,exponent=0.25)
except Exception as e:
    print("powerlaw ctor:",e); p=None
if p is not None:
    r=wind.run(city(),p,resolution=2.,bounds=(0,0,0,200,200,80),turbulence=wind.Turbulence("height"))
    s=r.streamwise_std; sp=np.linalg.norm(r.velocity,axis=-1)
    print("powerlaw z",r.z[[0,1,2,5,10,20,30,37]],"sigma",np.round(s[[0,1,2,5,10,20,30,37],5,5],2),"TI",np.round((s/sp)[[0,1,2,5,10,20,30,37],5,5],3))
r=wind.run(city(),speed=5.,direction=270.,resolution=2.,bounds=(0,0,0,200,200,80),turbulence=wind.Turbulence("height"))
s=r.streamwise_std; sp=np.linalg.norm(r.velocity,axis=-1)
print("log z",r.z[[0,1,2,5,10,20,30,37]],"sigma",np.round(s[[0,1,2,5,10,20,30,37],5,5],2),"TI",np.round((s/sp)[[0,1,2,5,10,20,30,37],5,5],3))
