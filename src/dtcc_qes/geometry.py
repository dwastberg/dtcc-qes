"""Opt-in horizontal geometry witnesses checked against the solver's mask.

No grid is changed and no wind solve is launched. Physical free-space checks
also work on previews, whose raster evidence is explicitly unavailable.
"""
from dataclasses import dataclass
import hashlib
import json
from numbers import Integral
import time

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from ._validation import real


class _BudgetReached(Exception):
    pass


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise _BudgetReached


def bounded_passage(solid, index, spacing):
    """Width needs solid cells at both ends of the containing row/column run."""
    index = int(index)
    if solid[index]:
        return dict(width=0., cells=0, bounded=False, solid=True)
    lo = hi = index
    while lo > 0 and not solid[lo-1]:
        lo -= 1
    while hi < len(solid)-1 and not solid[hi+1]:
        hi += 1
    bounded = lo > 0 and hi < len(solid)-1
    return dict(width=(hi-lo+1)*spacing if bounded else None,
                cells=hi-lo+1, bounded=bounded, solid=False)


def _raster_labels(fluid, deadline=float('inf')):
    """Four-face components; fixed numeric arrays, no per-cell Python graph."""
    ny, nx = fluid.shape
    labels = np.zeros(fluid.size, np.int32)
    queue = np.empty(fluid.size, np.int64)
    flat = fluid.reshape(-1)
    component = 0
    for seed in np.flatnonzero(flat):
        if labels[seed]:
            continue
        component += 1
        head, tail = 0, 1
        queue[0] = seed
        labels[seed] = component
        while head < tail:
            if head % 4096 == 0:
                _deadline(deadline)
            index = int(queue[head]); head += 1
            j, i = divmod(index, nx)
            for other in (index-1 if i else -1, index+1 if i+1<nx else -1,
                          index-nx if j else -1, index+nx if j+1<ny else -1):
                if other >= 0 and flat[other] and not labels[other]:
                    labels[other] = component
                    queue[tail] = other; tail += 1
    return labels.reshape(fluid.shape)


def _component_labels(polygons, xy, deadline):
    labels = np.zeros(len(xy), np.int32)
    tree = STRtree(polygons)
    for start in range(0, len(xy), 65536):
        _deadline(deadline)
        point_index, polygon_index = tree.query(shapely.points(xy[start:start+65536]), predicate='within')
        labels[start+point_index] = polygon_index+1
    return labels


def _polygons(prepared):
    arrays = prepared.arrays
    vertices, offsets = arrays['vertices'], arrays['offsets']
    ring_offsets = arrays.get('ring_offsets')
    polygons = []
    for lo, hi in zip(offsets[:-1], offsets[1:]):
        if ring_offsets is None:
            polygons.append(Polygon(vertices[lo:hi]))
        else:
            begin, end = np.searchsorted(ring_offsets, [lo, hi])
            rings = [vertices[a:b] for a,b in zip(ring_offsets[begin:end], ring_offsets[begin+1:end+1])]
            polygons.append(Polygon(rings[0],rings[1:]))
    return polygons


def _gap_line(first, second):
    """Choose the midpoint when parallel facing edges have tied shortest gaps.

    GEOS can choose a wall-end vertex for parallel walls. That witnesses the
    detour rather than the passage interior; a parallel-edge midpoint avoids
    that degeneracy while retaining the exact minimum physical gap.
    """
    shortest = shapely.shortest_line(first, second)
    distance = shortest.length
    if distance == 0:
        return shortest
    def edges(polygon):
        for ring in (polygon.exterior, *polygon.interiors):
            vertices = np.asarray(ring.coords)
            yield from zip(vertices[:-1],vertices[1:])
    for a,b in edges(first):
        vector = b-a
        length = np.linalg.norm(vector)
        direction = vector/length
        for c,d in edges(second):
            other = d-c
            if abs(direction[0]*other[1]-direction[1]*other[0])/np.linalg.norm(other) > 1e-12:
                continue
            start,stop = sorted((np.dot(c-a,direction),np.dot(d-a,direction)))
            lo,hi = max(0,start), min(length,stop)
            if hi <= lo:
                continue
            middle = a+.5*(lo+hi)*direction
            foot = c+np.dot(middle-c,other)/np.dot(other,other)*other
            if np.isclose(np.linalg.norm(foot-middle),distance,rtol=1e-12,atol=1e-12):
                return shapely.LineString([middle,foot])
    return shortest


def _line_cells(line, nx, ny, spacing):
    """Supercover of a shortest segment via crossings, without cell overlays."""
    a, b = np.asarray(line.coords)
    delta = b-a
    parameters = [np.array([0.,1.])]
    for axis, size in enumerate((nx,ny)):
        if delta[axis] != 0:
            crossings = (np.arange(size+1)*spacing-a[axis])/delta[axis]
            parameters.append(crossings[(crossings>0)&(crossings<1)])
    t = np.unique(np.concatenate(parameters))
    # Endpoints are on footprints. Examine the open gap, including face contacts.
    t = np.r_[t[1:-1], .5*(t[:-1]+t[1:])]
    positions = (a+t[:,None]*delta)/spacing
    cells = []
    for position in positions:
        choices = []
        for coordinate in position:
            index = int(np.floor(coordinate))
            choices.append((index-1,index) if coordinate == index else (index,))
        cells.extend((j,i) for i in choices[0] for j in choices[1] if 0<=i<nx and 0<=j<ny)
    return sorted(set(cells))


@dataclass(frozen=True)
class GeometryReport:
    """Immutable, deterministic schema-v1 diagnostic; never accessibility approval."""
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    def summary(self):
        data = self.to_dict()
        return (f"Geometry {data['status']}; {len(data['slices'])} horizontal slices; "
                'examined scope only, not validated pedestrian accessibility')


def _slice(polygons, bases, roofs, source_ids, grid, height, points, routes, flags,
           deadline, max_witnesses):
    spacing = grid.resolution
    ny, nx = len(grid.y), len(grid.x)
    faces = np.asarray(grid.z_faces if grid.z_faces is not None else
                          np.arange(len(grid.z)+1)*spacing, float)
    k = int(np.searchsorted(faces,height,side='right')-1)
    row = dict(height=height, layer=k, status='unavailable', reason=None, witnesses=[], points=[], routes=[])
    if not 0 <= k < len(grid.z):
        row['reason'] = 'outside_domain'; return row
    active_indices = np.flatnonzero((bases <= height) & (height < roofs))
    active = [polygons[i] for i in active_indices]
    row['footprints'] = [source_ids[i] for i in active_indices]
    union = shapely.union_all(active)
    domain = shapely.box(0,0,nx*spacing,ny*spacing)
    free = shapely.difference(domain,union)
    components = sorted((p for p in shapely.get_parts(free) if p.geom_type == 'Polygon'),
                        key=lambda p:(p.bounds,p.wkb_hex))
    row['physical_components'] = len(components)
    _deadline(deadline)
    issue = False
    def witness(kind, **evidence):
        nonlocal issue
        issue = True
        if len(row['witnesses']) >= max_witnesses:
            raise _BudgetReached
        row['witnesses'].append(dict(kind=kind, **evidence))
    pairs = []
    tree = STRtree(active)
    for i, polygon in enumerate(active):
        _deadline(deadline)
        for j in sorted(tree.query(polygon, predicate='dwithin', distance=2*spacing)):
            if j <= i:
                continue
            width = float(polygon.distance(active[j]))
            if width < 2*spacing:
                pair = dict(footprints=[source_ids[active_indices[i]],source_ids[active_indices[j]]],
                            physical_width=width)
                pairs.append((i,int(j),pair))
                witness('under_resolved', **pair, represented_width=None)
    raster = None
    solid = None
    if flags is None:
        row['reason'] = 'solver_mask_not_prepared'
    elif np.any(flags[k] == 2):
        row['reason'] = 'terrain_not_supported'
    elif np.any(((bases > faces[k]) & (bases < faces[k+1])) |
                ((roofs > faces[k]) & (roofs < faces[k+1]))):
        row['reason'] = 'roof_crossing'
    else:
        solid = (flags[k] == 0) | (flags[k] == 2)
        xy = np.column_stack((np.tile(grid.x,ny),np.repeat(grid.y,nx))).astype(float)
        physical = _component_labels(components,xy,deadline).reshape(ny,nx)
        inside = np.zeros(len(xy),bool)
        for start in range(0,len(xy),65536):
            _deadline(deadline)
            inside[start:start+65536] = shapely.contains_xy(union,*xy[start:start+65536].T)
        if not np.array_equal(inside.reshape(ny,nx),solid):
            row['reason'] = 'mapping_not_reproduced'
            row['mapping_mismatches'] = int(np.count_nonzero(inside.reshape(ny,nx) != solid))
            solid = None
        elif np.any((physical == 0) & ~solid):
            row['reason'] = 'boundary_centres_unknown'; solid = None
        else:
            row['mask_hash'] = hashlib.sha256(np.ascontiguousarray(solid).tobytes()).hexdigest()
            raster = _raster_labels(~solid,deadline)
            row['raster_components'] = int(raster.max())
            for axis in (0,1):
                a,b = ((np.s_[:-1,:],np.s_[1:,:]) if axis == 0 else (np.s_[:,:-1],np.s_[:,1:]))
                joins = (physical[a] != physical[b]) & ~solid[a] & ~solid[b]
                for j,i in np.argwhere(joins):
                    first = [int(i),int(j),k]
                    second = [int(i+(axis==1)),int(j+(axis==0)),k]
                    witness('false_join', cells=[first,second],
                            physical_labels=[int(physical[j,i]), int(physical[second[1],second[0]])])
            ownership = np.unique(np.column_stack((physical[~solid],raster[~solid])),axis=0)
            for component, polygon in enumerate(components,1):
                labels = ownership[ownership[:,0] == component,1]
                if len(labels)>1:
                    witness('disconnection',physical_component=component,raster_components=labels.tolist())
                if not len(labels) and polygon.area >= spacing**2:
                    witness('erased_space',physical_component=component,area=float(polygon.area))
            for i,j,pair in pairs:
                cells = _line_cells(_gap_line(active[i],active[j]),nx,ny,spacing)
                fluid_cells = [(y,x) for y,x in cells if not solid[y,x]]
                represented = len(fluid_cells)*spacing
                evidence = dict(pair, represented_width=represented,
                    cells=[[x,y,k] for y,x in cells])
                if cells and not fluid_cells:
                    witness('closed_passage',**evidence)
                # A cell count along an oblique segment is not a normal width.
                evidence['represented_width_definition'] = 'crossed_fluid_cells_times_spacing'
                row.setdefault('passages',[]).append(evidence)
            row['status'] = 'issue' if issue else 'no_issue_in_examined_scope'
    for index, point in enumerate(points):
        _deadline(deadline)
        xy = point[:2]
        label = int(_component_labels(components,np.asarray([xy]),deadline)[0])
        clearance = float(shapely.distance(shapely.Point(xy),union)) if active else None
        evidence = dict(id=index,point=point.tolist(),physical_component=label or None,
                        horizontal_clearance=clearance,near_footprint=bool(active and clearance<spacing))
        if evidence['near_footprint']:
            witness('critical_point_near_footprint',id=index,horizontal_clearance=clearance)
        i,j = np.floor(xy/spacing).astype(int)
        if len(point)==3 and point[2] != height:
            evidence['reason'] = 'point_height_not_in_examined_slice'
        elif solid is not None and 0<=i<nx and 0<=j<ny:
            evidence.update(containing_cell=[int(i),int(j),k],containing_cell_solid=bool(solid[j,i]),
                passage_x=bounded_passage(solid[j],i,spacing),passage_y=bounded_passage(solid[:,i],j,spacing))
        else:
            evidence['reason'] = row['reason'] or 'outside_domain'
        row['points'].append(evidence)
    for index, route in enumerate(routes):
        labels = _component_labels(components,route[:,:2],deadline)
        connected = bool(labels[0] and labels[0] == labels[1])
        evidence = dict(id=index,endpoints=route.tolist(),physical_connected=connected,represented_connected=None)
        if np.any(labels == 0):
            evidence.update(physical_connected=None,reason='endpoint_not_in_free_interior')
        elif raster is not None:
            i,j = np.floor(route[:,:2].T/spacing).astype(int)
            if (len(route[0])==3 and np.any(route[:,2] != height)):
                evidence['reason'] = 'route_height_not_in_examined_slice'
            elif ((i>=0)&(i<nx)&(j>=0)&(j<ny)).all():
                values = raster[j,i]
                evidence['represented_connected'] = bool(values[0] and values[0] == values[1])
                if connected != evidence['represented_connected']:
                    witness('route_connectivity_mismatch',id=index,**{k:v for k,v in evidence.items() if k!='id'})
        if connected is False and evidence['physical_connected'] is not None:
            witness('physically_disconnected_route',id=index)
        row['routes'].append(evidence)
    if raster is not None:
        row['status'] = 'issue' if issue else 'no_issue_in_examined_scope'
    return row


def check_geometry(city, grid, *, points=(), routes=(), heights=(1.5,), footprints=None,
                   height_policy='measured', terrain=None, max_queries=64, max_slices=4,
                   max_seconds=30., max_witnesses=256):
    """Examine local-metre points/routes against prepared physical geometry.

    Points have shape (n,2) or (n,3); routes (n,2,2) or (n,2,3). Input order is
    the observation ID. Optional z coordinates must equal the slice height.
    Heights are local metres above flat ground. All requested IDs are retained,
    including unavailable and budget-limited ones. Previews have physical
    evidence only. Roof-crossing layers are conservatively unavailable in v1.
    Preparation time is reported separately from the analysis time limit.
    """
    from .wind import _prepare_city, _validate_grid
    from .result import WindResult
    from .vertical_grid import GridPreview, VerticalGrid
    if not isinstance(grid,(WindResult,GridPreview)):
        raise TypeError('grid must be GridPreview or WindResult')
    for name,value in (('max_queries',max_queries),('max_slices',max_slices),('max_witnesses',max_witnesses)):
        if isinstance(value,bool) or not isinstance(value,Integral) or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    max_seconds = real(max_seconds,'max_seconds',positive=True)
    heights = tuple(real(z,'height') for z in heights)
    def coordinates(values, route=False):
        array = np.asarray(values,float)
        if array.size==0:
            return np.empty((0,2,2) if route else (0,2))
        if (array.ndim != (3 if route else 2) or array.shape[-1] not in (2,3)
                or (route and array.shape[1]!=2) or not np.isfinite(array).all()):
            raise ValueError('points/routes require finite local coordinate arrays')
        return array
    points, routes = coordinates(points), coordinates(routes,True)
    start = time.monotonic()
    domain = grid.metadata.get('domain',{}) if isinstance(grid,WindResult) else grid.domain
    faces = grid.z_faces
    if faces is None:
        faces = np.arange(len(grid.z)+1)*grid.resolution
    origin = np.asarray(grid.origin,float)
    bounds = (*origin, origin[0]+len(grid.x)*grid.resolution,
              origin[1]+len(grid.y)*grid.resolution,origin[2]+float(faces[-1]))
    options = _validate_grid(grid.resolution,bounds,20.,20.,max(len(grid.z)*len(grid.y)*len(grid.x), 1),vertical_grid=VerticalGrid.from_faces(faces))
    geometry, prepared = _prepare_city(city,None,options,terrain,height_policy,footprints=footprints)
    prep_seconds = time.monotonic()-start
    analysis_start = time.monotonic(); deadline=analysis_start+max_seconds
    polygons = _polygons(prepared)
    bases = np.asarray(prepared.arrays['base_heights'],float)
    roofs = bases+prepared.arrays['heights']
    ids = ([list(c.source_ids) for c in prepared.footprints.solids] if prepared.footprints else
           [[s] for s in geometry.source_ids])
    expected_x = (np.arange(len(grid.x),dtype=np.float32)+np.float32(.5))*np.float32(grid.resolution)
    expected_y = (np.arange(len(grid.y),dtype=np.float32)+np.float32(.5))*np.float32(grid.resolution)
    aligned = (np.array_equal(grid.x,expected_x) and np.array_equal(grid.y,expected_y) and
        np.array_equal(grid.origin,prepared.origin) and np.array_equal(faces,
            prepared.domain['vertical_grid']['effective_faces']) and
        tuple(domain.get('shape', (len(grid.z),len(grid.y),len(grid.x)))) ==
            (len(grid.z),len(grid.y),len(grid.x)))
    flags = grid.cell_flags if isinstance(grid,WindResult) else None
    aligned = (aligned and np.array_equal(grid.z, np.float32(.5)*(np.asarray(faces[:-1],np.float32)+
        np.asarray(faces[1:],np.float32))) and
        (flags is None or flags.shape == (len(grid.z),len(grid.y),len(grid.x))))
    slices=[]; limited=False
    for index,height in enumerate(heights):
        row = dict(height=height,status='unavailable',reason='grid_alignment_mismatch')
        try:
            if index >= max_slices or len(points)+len(routes)>max_queries:
                raise _BudgetReached
            _deadline(deadline)
            if aligned:
                row = _slice(polygons,bases,roofs,ids,grid,height,points,routes,flags,deadline,max_witnesses)
        except _BudgetReached:
            limited=True;row=dict(height=height,status='budget_limited',reason='analysis_limit_reached')
        # IDs remain present even when no work was possible.
        if not row.get('points'):
            row['points'] = [dict(id=i,point=p.tolist(),reason=row['reason']) for i,p in enumerate(points)]
        if not row.get('routes'):
            row['routes'] = [dict(id=i,endpoints=p.tolist(),reason=row['reason']) for i,p in enumerate(routes)]
        slices.append(row)
    status = ('budget_limited' if limited else 'unavailable' if not slices or
        any(r['status']=='unavailable' for r in slices) else 'issue' if
        any(r['status']=='issue' for r in slices) else 'no_issue_in_examined_scope')
    payload = dict(schema_version=1,status=status,frame='local',origin=list(grid.origin),crs=grid.crs,
        resolution=grid.resolution,shape=[len(grid.z),len(grid.y),len(grid.x)],
        preparation_seconds=prep_seconds,analysis_seconds=time.monotonic()-analysis_start,
        limits=dict(max_queries=max_queries,max_slices=max_slices,max_seconds=max_seconds,max_witnesses=max_witnesses),
        mask_hash=None if flags is None else hashlib.sha256(np.ascontiguousarray((flags==0)|(flags==2)).tobytes()).hexdigest(),
        slices=slices,terrain=prepared.terrain,
        scope='horizontal flat-terrain geometry diagnostic; not validated pedestrian accessibility')
    return GeometryReport(json.dumps(payload,sort_keys=True,allow_nan=False))
