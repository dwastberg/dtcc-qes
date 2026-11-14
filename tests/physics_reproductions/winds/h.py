import numpy as np, logging
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind
from dtcc_qes.footprints import Footprints
from dtcc_qes.parameterizations import Parameterizations
logging.disable(logging.CRITICAL)
def rect(x0,y0,x1,y1): return [(x0,y0),(x0,y1),(x1,y1),(x1,y0)]
def rot(cx,cy,L,W,ang):
    a=np.radians(ang); c,s=np.cos(a),np.sin(a)
    pts=[(-L/2,-W/2),(-L/2,W/2),(L/2,W/2),(L/2,-W/2)]
    return [(cx+x*c-y*s, cy+x*s+y*c) for x,y in pts]
def run(blds, direction, bounds, exposed=None, res=2.0, **par):
    city=City()
    for n,(ring,h) in enumerate(blds):
        b=Building(id=f"b{n}"); b.measured_height=float(h)
        b.add_geometry(Surface(vertices=np.array([[x,y,0.0] for x,y in ring])), GeometryType.LOD0)
        city.add_building(b)
    kw={}
    if exposed is not None: kw['footprints']=Footprints(exposed_faces=exposed)
    if par: kw['parameterizations']=Parameterizations(**par)
    return wind.run(city, speed=5.0, direction=direction, resolution=res, bounds=bounds, **kw)
