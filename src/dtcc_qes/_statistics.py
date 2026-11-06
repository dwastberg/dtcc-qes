"""Covariance validity and derived wind statistics shared by result consumers."""

import numpy as np

_STRESS_RELATIVE_TOLERANCE = 32 * float(np.finfo(np.float32).eps)
_STRESS_CHUNK_SIZE = 65536


def _stress_validity(stress):
    """Native raw-and-mask policy, in bounded float64 eigensolver batches.

    Use the stored tensors, including float64 interpolants, without narrowing
    or repairing them. Normalization protects the spectral calculation across
    scales. The returned tolerance is in squared-velocity units.
    """
    raw = np.asarray(stress)
    if raw.ndim < 1 or raw.shape[-1] != 6:
        raise ValueError("stress must have six components: xx, xy, xz, yy, yz, zz")
    flat = raw.reshape(-1,6)
    valid = np.zeros(len(flat),dtype=bool)
    tolerance = np.full(len(flat),np.nan,dtype=np.float64)
    for start in range(0,len(flat),_STRESS_CHUNK_SIZE):
        values = np.asarray(flat[start:start+_STRESS_CHUNK_SIZE],dtype=np.float64)
        finite = np.isfinite(values).all(axis=-1)
        values = values[finite]
        scale = np.max(np.abs(values),axis=-1)
        normalized = values/np.where(scale > 0,scale,1)[:,None]
        eigenvalues = np.linalg.eigvalsh(normalized[:,(0,1,2,1,3,4,2,4,5)].reshape(-1,3,3))
        relative = _STRESS_RELATIVE_TOLERANCE*np.max(np.abs(eigenvalues),axis=-1)
        locations = start+np.flatnonzero(finite)
        valid[locations] = eigenvalues[:,0] >= -relative
        tolerance[locations] = relative*scale
    return valid.reshape(raw.shape[:-1]),tolerance.reshape(raw.shape[:-1])


def _velocity_magnitude(velocity):
    with np.errstate(over="ignore",invalid="ignore"):
        return np.hypot.reduce(np.asarray(velocity,dtype=np.float64),axis=-1)


def _streamwise_std(stress, velocity, covered, *, validity=None):
    """Reclassify current tensors, then project only covered, directed cells."""
    raw,velocity,covered = np.asarray(stress),np.asarray(velocity),np.asarray(covered,dtype=bool)
    if raw.shape != (*covered.shape,6) or velocity.shape != (*covered.shape,3):
        raise ValueError("Stress, velocity and coverage must have matching cell shapes")
    valid,tolerance = _stress_validity(raw) if validity is None else validity
    speed = _velocity_magnitude(velocity)
    usable = covered & valid & np.isfinite(velocity).all(axis=-1) & np.isfinite(speed) & (speed > 0)
    result = np.full(covered.shape,np.nan,dtype=np.float64)
    flat = raw.reshape(-1,6)
    mean = velocity.reshape(-1,3)
    for start in range(0,len(flat),_STRESS_CHUNK_SIZE):
        locations = start+np.flatnonzero(usable.reshape(-1)[start:start+_STRESS_CHUNK_SIZE])
        s = np.asarray(flat[locations],dtype=np.float64)
        n = np.asarray(mean[locations],dtype=np.float64)/speed.reshape(-1)[locations,None]
        x,y,z = n.T
        projected = (s[:,0]*x*x+s[:,3]*y*y+s[:,5]*z*z
                     +2*(s[:,1]*x*y+s[:,2]*x*z+s[:,4]*y*z))
        accepted = np.isfinite(projected) & (projected >= -tolerance.reshape(-1)[locations])
        result.reshape(-1)[locations[accepted]] = np.sqrt(np.maximum(0,projected[accepted]))
    return result


def _turbulence_intensity(std, velocity):
    with np.errstate(over="ignore",invalid="ignore",divide="ignore"):
        intensity = std/_velocity_magnitude(velocity)
    intensity[~np.isfinite(intensity)] = np.nan
    return intensity
