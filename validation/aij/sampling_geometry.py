"""Opt-in physical/voxel geometry summaries; ambiguous ownership stays unknown."""
import numpy as np
import shapely


def bounded_passage(solid,index,spacing):
    """A finite width requires solid cells at both ends of the same row/column."""
    if solid[index]:return dict(width=0.,cells=0,bounded=False,solid=True)
    lo=hi=index
    while lo>0 and not solid[lo-1]:lo-=1
    while hi<len(solid)-1 and not solid[hi+1]:hi+=1
    bounded=lo>0 and hi<len(solid)-1
    return dict(width=(hi-lo+1)*spacing if bounded else None,cells=hi-lo+1,bounded=bounded,solid=False)


def summarize(occupancy,buildings,points):
    """Physical rectangles versus existing mask, roof faces and local passages.

    Per-building ownership is qualified only for isolated axis-aligned ground
    rectangles whose expanded neighbourhood intersects no other footprint.
    General/overlapping geometry is explicitly unavailable; a public solid
    mask cannot recover source ownership in those cases. No rasterization or
    sampling rule is changed. Positions and footprints use world coordinates.
    """
    axes=occupancy['axes'];solid=occupancy['solid'];origin=np.asarray(occupancy['origin'],float)
    faces=np.asarray(occupancy['z_faces'],float)+origin[2]
    dx=float(axes[0][1]-axes[0][0]);dy=float(axes[1][1]-axes[1][0])
    rows=[];polygons=[row[1] for row in buildings]
    for n,(source,polygon,height) in enumerate(buildings):
        bounds=np.array(polygon.bounds);window=shapely.box(*(bounds+[-dx,-dy,dx,dy]))
        row=dict(source_id=source,physical_bounds=bounds,physical_height=height,status='unavailable')
        if not polygon.equals(shapely.box(*bounds)):
            row['reason']='nonrectangular_ownership_not_available';rows.append(row);continue
        if any(i!=n and window.intersects(p) for i,p in enumerate(polygons)):
            row['reason']='nearby_footprint_ownership_ambiguous';rows.append(row);continue
        ix=np.flatnonzero((axes[0]>=bounds[0]-dx)&(axes[0]<=bounds[2]+dx))
        iy=np.flatnonzero((axes[1]>=bounds[1]-dy)&(axes[1]<=bounds[3]+dy))
        patch=solid[:,iy[:,None],ix]
        footprint=patch.any(axis=0);jj,ii=np.where(footprint)
        if not len(ii) or not np.array_equal(footprint,patch[0]):
            row['reason']='missing_or_elevated_voxel_footprint';rows.append(row);continue
        represented=np.array([axes[0][ix[ii]].min()-dx/2,axes[1][iy[jj]].min()-dy/2,
            axes[0][ix[ii]].max()+dx/2,axes[1][iy[jj]].max()+dy/2])
        roof=np.max(np.where(patch,faces[1:,None,None],-np.inf),axis=0)[footprint]-origin[2]
        row.update(status='qualified_isolated_rectangle',voxel_bounds=represented,edge_displacement=represented-bounds,
            represented_roof_heights=np.unique(roof),solid_columns=int(footprint.sum()))
        rows.append(row)
    queries=[];union=shapely.union_all(polygons)
    for point in np.asarray(points,float):
        row=dict(point=point,horizontal_clearance=float(shapely.Point(point[:2]).distance(union)))
        i=int(np.floor((point[0]-(axes[0][0]-dx/2))/dx))
        j=int(np.floor((point[1]-(axes[1][0]-dy/2))/dy))
        k=int(np.searchsorted(faces,point[2],side='right')-1)
        if not (0<=i<len(axes[0]) and 0<=j<len(axes[1]) and 0<=k<len(axes[2])):
            row['reason']='outside_physical_voxels'
        else:
            row.update(containing_cell=[i,j,k],containing_voxel_solid=bool(solid[k,j,i]),
                passage_x=bounded_passage(solid[k,j],i,dx),passage_y=bounded_passage(solid[k,:,i],j,dy))
        queries.append(row)
    return dict(schema_version=1,clearance_definition='horizontal distance to physical footprint; not 3D surface distance',
        buildings=rows,points=queries)


def summarize_result(result,buildings,points):
    axes=[np.asarray(a,float)+result.origin[i] for i,a in enumerate((result.x,result.y,result.z))]
    return summarize(dict(axes=axes,solid=result.solid_mask,z_faces=result.z_faces,origin=result.origin),buildings,points)
