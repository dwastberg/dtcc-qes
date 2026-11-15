"""Stored 2 m planes: fluid-restricted Gaussian smoothing and probe sampling (post-hoc screens only)."""
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates


def smooth(field, valid, sigma_cells):
    """Normalised Gaussian over fluid cells only; ``field`` is (ny, nx) or (ny, nx, c). Solid cells stay NaN."""
    field = np.asarray(field, np.float64)
    if sigma_cells <= 0:
        return np.where(valid[..., None] if field.ndim == 3 else valid, field, np.nan)
    weight = gaussian_filter(valid.astype(np.float64), sigma_cells, mode="nearest")
    planes = field[..., None] if field.ndim == 2 else field
    out = np.empty_like(planes)
    for c in range(planes.shape[-1]):
        out[..., c] = gaussian_filter(np.where(valid, planes[..., c], 0.0), sigma_cells, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(valid[..., None] & (weight[..., None] > 1e-6), out / weight[..., None], np.nan)
    return out[..., 0] if field.ndim == 2 else out


def sample(field, x, y, points_xy):
    """Bilinear over the finite cells around each point, renormalised; nearest finite cell within 1.5 cells otherwise."""
    field = np.asarray(field, np.float64)
    planes = field[..., None] if field.ndim == 2 else field
    dx, dy = x[1] - x[0], y[1] - y[0]
    cx, cy = (points_xy[:, 0] - x[0]) / dx, (points_xy[:, 1] - y[0]) / dy
    finite = np.isfinite(planes[..., 0]).astype(np.float64)
    weight = map_coordinates(finite, [cy, cx], order=1, mode="nearest")
    out = np.empty((len(points_xy), planes.shape[-1]))
    for c in range(planes.shape[-1]):
        out[:, c] = map_coordinates(np.nan_to_num(planes[..., c]), [cy, cx], order=1, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(weight[:, None] > 0.999, out / weight[:, None], np.nan)
    for i in np.flatnonzero(~np.isfinite(out[:, 0])):
        j0, i0 = int(round(cy[i])), int(round(cx[i]))
        best = None
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                j, k = j0 + dj, i0 + di
                if 0 <= j < planes.shape[0] and 0 <= k < planes.shape[1] and finite[j, k]:
                    d = np.hypot(j - cy[i], k - cx[i])
                    if d <= 1.5 and (best is None or d < best[0]):
                        best = (d, j, k)
        if best:
            out[i] = planes[best[1], best[2]]
    return out[:, 0] if field.ndim == 2 else out
