import numpy as np, logging
logging.disable(logging.CRITICAL)
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind
def city(h=20.):
    c=City(); b=Building(id="b"); b.measured_height=h
    b.add_geometry(Surface(vertices=np.array([[90.,90,0],[90,110,0],[110,110,0],[110,90,0]])),GeometryType.LOD0)
    c.add_building(b); return c
for ml in ("height","wall_distance"):
  for d in (270.,225.,247.5):
    r=wind.run(city(),speed=5.,direction=d,resolution=2.,bounds=(0,0,0,200,200,80),turbulence=wind.Turbulence(ml))
    t=r.metadata["turbulence"]; us=t["reference"]["friction_velocity"]; bound=t["cap"]["value"]
    s=r.streamwise_std; pk=r.physical_k
    us_in=0.4*5/np.log((10+.1)/.1)
    print(ml,d,"u*morph %.3f u*inflow %.3f uref %.3f zref %.1f cap %.3f capped %d/%d"%(us,us_in,t["reference"]["speed"],t["reference"]["height"],bound,t["cap"]["capped_cells"],t["cap"]["computed_cells"]))
    print("   max sigma^2/bound %.3f  max physk/bound %.3f  max tke/bound %.3f invalid %d"%(np.nanmax(s**2)/bound,np.nanmax(pk)/bound,np.nanmax(r.turbulence.tke)/bound,t["validity"]["invalid_stress_cells"]))
    # upstream column profile
    if d==270.:
        j=5; i=5
        print("   upstream sigma/u*_in by layer:",np.round(s[:8,j,i]/us_in,2), "z",r.z[:8])
        print("   upstream sqrt(tke)/u*_in:",np.round(np.sqrt(r.turbulence.tke[:8,j,i])/us_in,2))
        # pedestrian plane stats
        sm=r.sample(1.5,"linear") if r.z[0]<=1.5 else r.sample(float(r.z[0]),"nearest")
        ti=sm.turbulence_intensity; sp=sm.speed
        print("   ped plane: frac sigma<0.5*upstream:",np.nanmean(sm.streamwise_std<0.5*sm.streamwise_std[5,5]), "upstream sigma",sm.streamwise_std[5,5],"speed",sp[5,5])
        # wake centreline behind building (x=112..160,y=100)
        jj=np.argmin(abs(r.y-100));
        for x in (113,121,131,151,181):
            ii=np.argmin(abs(r.x-x)); print("     x=%d speed %.2f sigma %.3f"%(x,sp[jj,ii],sm.streamwise_std[jj,ii]))
