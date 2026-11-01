"""Shifted logarithm shared by inflow profiles and exposure transfer."""
import math
import numpy as np


def shifted_log(z, roughness):
    # log1p preserves tiny ratios; the fallback avoids overflow for large ones.
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        ratio = np.asarray(z) / roughness
        return np.where(np.isfinite(ratio), np.log1p(ratio), np.log(z) - math.log(roughness))
