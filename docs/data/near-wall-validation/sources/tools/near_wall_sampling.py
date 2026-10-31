"""Study-only point reconstruction from archived native face/cell patches.

No extrapolation, positive-weight solid support rejection, no renormalization.
This diagnostic does not change WindResult.sample or establish a new preset.
"""
from itertools import product

import numpy as np


def fluid(flag):
    return flag >= 0 and flag not in (0, 2)


def interpolate(records, point, *, field, valid):
    """Multilinear interpolation on an explicitly positioned tensor stencil."""
    if not records:
        return None
    lookup = {tuple(r["position"]): r for r in records}
    if len(lookup) != len(records):
        raise ValueError("Duplicate support positions")
    axes = [sorted({p[d] for p in lookup}) for d in range(3)]
    brackets = []
    for axis, p in zip(axes, point):
        if not np.isfinite(p) or p < axis[0] or p > axis[-1]:
            return None
        hi = int(np.searchsorted(axis, p))
        if axis[hi] == p:
            brackets.append([(axis[hi], 1.)])
        else:
            weight = (p-axis[hi-1])/(axis[hi]-axis[hi-1])
            brackets.append([(axis[hi-1], 1-weight), (axis[hi], weight)])
    result = None
    for corner in product(*brackets):
        key = tuple(c[0] for c in corner)
        weight = float(np.prod([c[1] for c in corner]))
        row = lookup.get(key)
        if row is None or not valid(row):
            return None
        value = np.asarray(row[field], dtype=float)
        if not np.isfinite(value).all():
            return None
        result = weight*value if result is None else result+weight*value
    return result


def reconstruct(patch, method):
    if not fluid(patch["query_flag"]):
        return None
    point = patch["local_point"]
    if method == "centred":
        return interpolate(patch["cells"], point, field="velocity", valid=lambda r: fluid(r["flag"]))
    if method != "staggered":
        raise ValueError("Unknown reconstruction")
    result = [interpolate(rows, point, field="value",
                          valid=lambda r: all(f >= 0 for f in r["flags"]) and any(map(fluid, r["flags"])))
              for rows in patch["faces"]]
    return None if any(v is None for v in result) else np.array(result)


def difference(a, b):
    if a is None or b is None:
        return dict(valid=False, within_budget=False)
    ka, kb = np.linalg.norm(a)/5, np.linalg.norm(b)/5
    absolute = abs(ka-kb)
    relative = absolute/kb if kb >= .1 else None
    return dict(valid=True, K=[float(ka), float(kb)], abs_delta_K=float(absolute),
                relative_delta=float(relative) if relative is not None else None,
                vector_delta_over_Uref=float(np.linalg.norm(np.asarray(b)-a)/5),
                within_budget=bool(relative < .05 if relative is not None else absolute < .05))
