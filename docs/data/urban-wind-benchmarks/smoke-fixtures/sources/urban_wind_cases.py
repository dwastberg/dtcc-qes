"""Deterministic flat-ground neighbourhoods for solver cost comparisons.

These are synthetic urban morphologies, with explicit metre coordinates and
constant-height, separate footprints. They are not measured city reconstructions.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

SCHEMA = "dtcc-qes-urban-case-v1"
NAMES = ("perimeter_neighbourhood", "mixed_downtown", "slab_estate", "industrial_residential")


def make_case(name):
    rng = np.random.default_rng(7301 + NAMES.index(name))
    buildings = []

    def polygon(points, height):
        buildings.append(dict(id=f"b{len(buildings):03d}", height=float(height),
                              vertices=np.asarray(points, float).tolist()))

    def box(x, y, w, d, h, angle=0):
        p = np.array([[-w/2,-d/2],[-w/2,d/2],[w/2,d/2],[w/2,-d/2]])
        a = np.deg2rad(angle); rotation = np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        polygon(p @ rotation.T + [x+w/2,y+d/2], h)

    if name == "perimeter_neighbourhood":
        # Sixteen courtyard blocks. Separate frontages leave gates and alleys;
        # every footprint is hole-free and separated from its neighbours.
        for j in range(4):
            for i in range(4):
                x,y = 120+80*i,120+80*j
                for side in (0,1):
                    for segment in range(3):
                        box(x+22*segment,y+52*side,20,12,rng.integers(15,29))
                for side in (0,1):
                    for segment in range(2):
                        box(x+52*side,y+15+20*segment,12,14,rng.integers(15,29))
        extent, top = 560, 100
        description = "16 perimeter blocks, 160 separate frontage buildings, courtyards, gates and intersecting 16 m streets"
    elif name == "mixed_downtown":
        for j in range(5):
            for i in range(5):
                x,y = 120+64*i,120+64*j
                # A central plaza and differing setbacks/open sites.
                for dy in (0,29):
                    for dx in (0,29):
                        if (i,j,dx,dy) in ((2,2,0,0),(2,2,29,0),(2,1,29,29)):
                            continue
                        h = rng.integers(10,36)
                        if (i+j+int(dx+dy))%7 == 0: h = rng.integers(42,73)
                        w,d = rng.integers(17,24,size=2)
                        if (i+j)%3 == 0:
                            # L-shaped office frontage, within its own parcel.
                            polygon([(x+dx,y+dy),(x+dx,y+dy+d),(x+dx+9,y+dy+d),
                                     (x+dx+9,y+dy+10),(x+dx+w,y+dy+10),(x+dx+w,y+dy)],h)
                        else: box(x+dx,y+dy,w,d,h)
        extent,top = 560,160
        description = "25 mixed-use blocks, 97 footprints, offices and L-shaped frontages, 42–72 m towers, a plaza and height transitions"
    elif name == "slab_estate":
        for j in range(6):
            for i in range(6):
                box(110+66*i+7*(j%2),110+58*j,43,13,rng.integers(15,37),22)
        for i in range(6):
            box(120+60*i,465,32,18,rng.integers(5,10))
        extent,top = 600,120
        description = "36 staggered rotated apartment slabs, six community/retail buildings and broad open pedestrian spaces"
    else:
        for j in range(4):
            for i in range(4):
                box(110+94*i,110+65*j,66,39,rng.integers(7,15))
                box(180+94*i,114+65*j,13,18,rng.integers(10,19))
        for j in range(4):
            for i in range(12):
                box(115+31*i,405+29*j,22,15,rng.integers(7,14))
        for i in range(4): box(120+94*i,545,58,13,rng.integers(19,31))
        extent,top = 640,120
        description = "16 warehouses with separate offices/service yards, 48 housing frontages and four apartment slabs"
    # Required fixed receptors are selected in open streets/yards, not by peak
    # values observed after solving. All are retained even if sampling is invalid.
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union
    occupied = unary_union([Polygon(b["vertices"]) for b in buildings])
    candidates = [(x,y) for y in range(100,extent-95,12) for x in range(100,extent-95,12)
                  if occupied.distance(Point(x,y)) >= 3]
    receptors = []
    for y in (100,200,300,400):
        for x in (100,200,300,400):
            chosen = min((p for p in candidates if list(p) not in receptors),key=lambda p:(p[0]-x)**2+(p[1]-y)**2)
            receptors.append(list(chosen))
    return dict(schema=SCHEMA,name=name,description=description,synthetic=True,seed=7301+NAMES.index(name),
        origin=[0,0,0],crs=None,bounds=[0,0,0,extent,extent,top],
        roi=[90,extent-90,90,extent-90],heights=[1.5,1.75],receptors=receptors,buildings=buildings,
        geometry_limitations=["Flat ground", "Constant heights per footprint", "No vegetation, balconies, roof shape or measured inflow"],
        source=dict(kind="procedural",license="GPL-3.0-only",generator="urban-wind-v1"))


def city(case):
    from dtcc_core.model import Building, City, GeometryType, Surface, Transform
    value = City(transform=Transform(srs=case.get("crs") or ""))
    origin = np.asarray(case["origin"],float)
    for item in case["buildings"]:
        b = Building(id=item["id"]); b.measured_height = item["height"]
        points = np.c_[np.asarray(item["vertices"],float),np.zeros(len(item["vertices"]))]+origin
        b.add_geometry(Surface(vertices=points), GeometryType.LOD0); value.add_building(b)
    return value


def validate(case):
    from dtcc_qes import wind
    if case.get("schema") != SCHEMA or not case.get("source") or len(case["buildings"]) < 20:
        raise ValueError("Urban cases require schema, source provenance and at least 20 buildings")
    for b in case["buildings"]:
        if not np.isfinite(b["height"]) or b["height"] <= 0:
            raise ValueError("Every building requires a measured or explicitly declared positive height")
    bounds = np.asarray(case["bounds"],float)+np.tile(case["origin"],2)
    # The normal product validator checks self intersections, overlaps, bases
    # and domain containment. Geometry validation performs no solver work.
    wind.preview_grid(city(case),bounds=tuple(bounds),resolution=4,max_cells=40_000_000,terrain="flat")


def preview_svg(case,path):
    extent = max(case["bounds"][3:5]); scale=720/extent
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="850" viewBox="0 0 800 850">',
             '<rect width="800" height="850" fill="#f3f1eb"/>',
             f'<text x="40" y="28" font-family="sans-serif" font-size="19">{case["name"]}</text>',
             f'<text x="40" y="49" font-family="sans-serif" font-size="13">{len(case["buildings"])} buildings · metres · height shading</text>',
             '<g transform="translate(40 780) scale(1 -1)">']
    for b in case["buildings"]:
        height=min(1,b["height"]/75); color=f'rgb({int(185-140*height)},{int(195-100*height)},{int(204-25*height)})'
        points=" ".join(f'{x*scale:.2f},{y*scale:.2f}' for x,y in b["vertices"])
        parts.append(f'<polygon points="{points}" fill="{color}" stroke="#26394a" stroke-width="0.65"/>')
    r=case["roi"]
    parts.append(f'<rect x="{r[0]*scale}" y="{r[2]*scale}" width="{(r[1]-r[0])*scale}" height="{(r[3]-r[2])*scale}" fill="none" stroke="#c66022" stroke-dasharray="6 4"/>')
    for x,y in case["receptors"]: parts.append(f'<circle cx="{x*scale}" cy="{y*scale}" r="2.5" fill="#c43b29"/>')
    parts += ['</g>',f'<path d="M40 814 h{100*scale}" stroke="#26394a" stroke-width="3"/>',
              '<text x="40" y="836" font-family="sans-serif" font-size="13">100 m; orange: ROI, red: fixed receptors. North is up.</text>','</svg>']
    Path(path).write_text("\n".join(parts))


def write_case(case,path):
    validate(case)
    Path(path).write_text(json.dumps(case,indent=2,allow_nan=False)+"\n")
    preview_svg(case,Path(path).with_suffix(".svg"))
