"""Frozen small canyon fixture; measurements are not used for qualification."""
from types import SimpleNamespace
import numpy as np
from dtcc_core.model import Building, City, Surface, GeometryType
from dtcc_qes import wind


def fixture(oblique=False, height=10., nonuniform=False):
    city = City(id="joint-canyon-qualification")
    for name, x in (("upstream", 16.), ("downstream", 36.)):
        b = Building(id=name); b.measured_height = height
        b.add_geometry(Surface(vertices=np.array([[x,25.,0.],[x,35.,0.],
            [x+10.,35.,0.],[x+10.,25.,0.]])), GeometryType.LOD0)
        city.add_building(b)
    xyz = np.array([[x,y,z] for z in (1.5,5.5,8.5,9.5,12.5)
        for y in (25.5,27.5,30.5,33.5,34.5) for x in (27.5,29.5,31.5,33.5,35.5)])
    grid = wind.VerticalGrid.from_faces(np.r_[0.,np.arange(1.,40.,2.),40.]) if nonuniform else None
    return dict(city=city, profile=wind.LogProfile(5.,250. if oblique else 270.,
        reference_height=10., roughness_length=.1), reference_speed=5.,
        probes=SimpleNamespace(xyz=xyz, ids=np.arange(len(xyz))),
        run=dict(resolution=1., bounds=(0.,0.,0.,80.,60.,40.), max_cells=np.iinfo(np.int32).max,
                 vertical_grid=grid, solver=wind.Solver(precision="float64", tolerance=1e-12,
                 max_iterations=8000), turbulence=None))
