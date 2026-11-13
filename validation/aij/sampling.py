"""Probe values from a dtcc-qes WindResult (AIJ_VALIDATION_PLAN.md, Sampling).

Probes are sampled with ``WindResult.sample_points(..., "linear", frame="global")``.
The vertical faces put a cell centre at the probe height (``grids``), so the
interpolation is bilinear in the probe layer. ``sample_points`` marks a probe
invalid when any contributing cell is solid; such a probe then takes the
nearest valid fluid centre within one cell, flagged ``nearest_fluid``. Probes
closer to a wall than half a cell are the usual cause.
"""

import numpy as np
import shapely

LINEAR, NEAREST_FLUID, NONE = "linear", "nearest_fluid", "none"


def wall_distance(points_xy, polygons) -> np.ndarray:
    """Horizontal distance from each point to the nearest footprint; 0 inside one."""
    points = shapely.points(np.asarray(points_xy, dtype=np.float64))
    union = shapely.union_all(polygons)
    return shapely.distance(points, union)


def _offsets(resolution, radius):
    steps = int(np.floor(radius / resolution + 1e-9))
    grid = np.arange(-steps, steps + 1) * resolution
    xy = np.array([(dx, dy) for dx in grid for dy in grid if np.hypot(dx, dy) <= radius + 1e-9])
    return np.column_stack([xy, np.zeros(len(xy))])


def k_from_stress(stress) -> np.ndarray:
    """Turbulence kinetic energy ½(σxx + σyy + σzz) from (n, 6) stresses ordered xx,xy,xz,yy,yz,zz."""
    stress = np.asarray(stress, dtype=np.float64)
    return 0.5 * (stress[:, 0] + stress[:, 3] + stress[:, 5])


def provenance(probes):
    """Read sampling provenance, retaining unknown support for older records."""
    if 'sampling_provenance' in probes:
        value=probes['sampling_provenance']
        if value.get('schema_version')!=1:raise ValueError('Unsupported sampling provenance version')
        return value
    requested=np.asarray(probes['xyz'],float)
    actual=np.asarray(probes.get('sampled',np.full_like(requested,np.nan)),float)
    methods=np.asarray(probes.get('method',['unknown']*len(requested)),str)
    return dict(schema_version=1,requested=requested,sampled=actual,method=methods,
        horizontal_displacement=np.linalg.norm(actual[:,:2]-requested[:,:2],axis=1),
        height_change=actual[:,2]-requested[:,2],requested_support=None,sampled_support=None)


def probe_sample(result, xyz, *, radius: float | None = None) -> dict:
    """Velocity, speed, stress and sampling provenance at global probe coordinates.

    ``speed_min``/``speed_max`` span the valid cell centres within ``radius``
    (default max(1 m, the grid spacing)) of each probe, plus the probe value:
    the spatial tolerance of the comparison. With wake code 3, ``wake_deficit``
    and ``wake_tke`` come from the same samples as the velocity.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    resolution = float(result.resolution)
    radius = max(1.0, resolution) if radius is None else radius
    linear = result.sample_points(xyz, "linear", frame="global", diagnostics=True)
    requested_support=linear.support.to_dict();sampled_support=linear.support.to_dict()
    velocity = linear.velocity.copy()
    sampled = linear.sampled_points.copy()
    method = np.where(linear.valid, LINEAR, NONE).astype(object)
    stress = None if linear.stress is None else linear.stress.copy()
    stress_valid = None if linear.stress_valid is None else linear.stress_valid.copy()
    wake = None if linear.wake_deficit is None else dict(wake_deficit=linear.wake_deficit.copy(),
                                                          wake_tke=linear.wake_tke.copy())

    # Fallback: the nearest valid fluid centre within one cell of the probe.
    missing = np.flatnonzero(~linear.valid)
    if len(missing):
        candidates = _offsets(resolution, resolution * np.sqrt(2.0))
        best = np.full(len(missing), np.inf)
        for offset in candidates:
            near = result.sample_points(xyz[missing] + offset, "nearest", frame="global",diagnostics=True)
            near_support=near.support.to_dict()
            distance = np.linalg.norm(near.sampled_points - xyz[missing], axis=1)
            take = near.valid & (distance < best) & (distance <= resolution * np.sqrt(2.0) + 1e-9)
            for row in np.flatnonzero(take):
                i = missing[row]
                best[row] = distance[row]
                velocity[i] = near.velocity[row]
                sampled[i] = near.sampled_points[row]
                method[i] = NEAREST_FLUID
                for key in ('geometric','solid_weight','computed','contributors_valid','interpolant_valid','reasons'):
                    if sampled_support[key] is not None:sampled_support[key][i]=near_support[key][row]
                if stress is not None:
                    stress[i] = near.stress[row]
                    stress_valid[i] = near.stress_valid[row]
                if wake is not None:
                    wake["wake_deficit"][i] = near.wake_deficit[row]
                    wake["wake_tke"][i] = near.wake_tke[row]

    speed = np.linalg.norm(velocity, axis=1)
    speed_min, speed_max = speed.copy(), speed.copy()
    for offset in _offsets(resolution, radius):
        near = result.sample_points(xyz + offset, "nearest", frame="global")
        ok = near.valid & np.isfinite(near.speed)
        speed_min = np.where(ok, np.fmin(speed_min, near.speed), speed_min)
        speed_max = np.where(ok, np.fmax(speed_max, near.speed), speed_max)
    out = dict(velocity=velocity, speed=speed, method=method.astype(str), sampled=sampled,
               speed_min=speed_min, speed_max=speed_max, radius=radius)
    out['sampling_provenance']=dict(schema_version=1,requested=xyz.copy(),sampled=sampled.copy(),
        method=method.astype(str),horizontal_displacement=np.linalg.norm(sampled[:,:2]-xyz[:,:2],axis=1),
        height_change=sampled[:,2]-xyz[:,2],requested_support=requested_support,sampled_support=sampled_support)
    if stress is not None:
        k = k_from_stress(stress)
        out.update(stress=stress, stress_valid=stress_valid, k=np.where(stress_valid, k, np.nan))
    if wake is not None:
        out.update(wake)  # wake code 3: deficit D and wake turbulence k_w (m²/s²)
    return out
