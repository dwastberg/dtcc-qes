"""Constrained automatic-grid prototype; no solver or wind-condition inputs."""
import math

import numpy as np

from .vertical_grid import effective_faces

_FLOAT_TOL = 8 * float(np.finfo(np.float32).eps)


def _integer_bound(value, *, upward):
    """Remove only float64 quotient roundoff near an integer."""
    nearest = round(value)
    if abs(value-nearest) <= 16 * math.ulp(max(1.0, abs(value))):
        return nearest
    return math.ceil(value) if upward else math.floor(value)


@np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore")
def generate_auto_layers(settings, *, resolution, top, heights):
    """Return float64 solver layers and serializable effective policy details.

    The fine band is fixed first. The upper minimum-count fit follows maximal
    allowed growth until a constant tail can fill the remaining height. Since
    caps are nondecreasing, that tail remains feasible at every later face.
    Work is bounded by the native 10,000-layer limit.
    """
    r, zp = float(resolution), settings.pedestrian_height
    if not math.isfinite(top) or top <= 0 or top > float(np.finfo(np.float32).max):
        raise ValueError("Automatic domain top must be positive, finite and representable in float32")
    base = min(0.2, r) if settings.min_layer_thickness is None else settings.min_layer_thickness
    if base > r:
        if np.float32(base) == np.float32(r):
            base = r
        else:
            raise ValueError("min_layer_thickness exceeds resolution; lower the explicit min_layer_thickness")
    hmin = max(base, r/settings.max_aspect_ratio)
    upper_cap = 4*r if settings.upper_layer_cap is None else settings.upper_layer_cap
    if upper_cap < r:
        if np.float32(upper_cap) == np.float32(r):
            upper_cap = r  # Record the effective adjustment after spacing narrowing.
        else:
            raise ValueError("upper_layer_cap must be at least resolution")
    with np.errstate(over="ignore", under="ignore"):
        native_heights = np.asarray(heights, dtype=np.float32).astype(np.float64)
    if not np.isfinite(native_heights).all() or np.any(native_heights <= 0):
        raise ValueError("Building heights must be positive and finite in float32")
    # Sorted heights let searchsorted release constraints without an O(nlayers *
    # nbuildings) scan. All retained positive buildings contribute.
    native_heights.sort()
    thresholds = 1.5*native_heights

    def cap(z):
        first = int(np.searchsorted(thresholds, z, side="right"))
        if first == len(native_heights):
            return upper_cap
        return min(r, max(hmin, float(native_heights[first])/10))

    preferred = (min(0.5, zp/3.5, r) if settings.first_layer_thickness is None
                 else settings.first_layer_thickness)
    length = 2*zp if settings.fine_region_height is None else settings.fine_region_height
    if not math.isfinite(length):
        raise ValueError("fine_region_height is too large; choose a finite fine band")
    hmax = min(r, zp/2.5, cap(0))
    if hmin > hmax:
        raise ValueError("Automatic minimum thickness conflicts with the pedestrian/building limit; "
                         "reduce resolution, lower min_layer_thickness or increase max_aspect_ratio")
    target = min(hmax, max(hmin, preferred))
    if length/hmax > 10000+1e-10:
        raise ValueError("Automatic fine band exceeds 10000 layers; reduce fine_region_height or revise resolution")
    low = _integer_bound(length/hmax, upward=True)
    # Counts beyond 10001 are only needed to reject an over-fine target; this
    # bound avoids converting extreme but finite setting ratios to huge ints.
    high = _integer_bound(min(length/hmin, 10001), upward=False)
    if low > 10000:
        raise ValueError("Automatic fine band exceeds 10000 layers; reduce fine_region_height or revise resolution")
    if low <= high:
        guess = length/target
        if guess > 10001:
            raise ValueError("Preferred automatic fine band exceeds 10000 layers; revise first_layer_thickness or fine_region_height")
        choices = {max(low, min(high, math.floor(guess))), max(low, min(high, math.ceil(guess)))}
        best_error = min(abs(length/n-target) for n in choices)
        count = min(n for n in choices if abs(length/n-target) <= best_error+16*math.ulp(target))
        fine_h = length/count
        fine_top = length
    else:
        count, fine_h = low, hmin
        fine_top = count*fine_h
    if count > 10000:
        raise ValueError("Automatic fine band exceeds 10000 layers; revise first_layer_thickness or fine_region_height")
    tolerance64 = 32*math.ulp(max(top, fine_top))
    if fine_top > top+tolerance64:
        raise ValueError("Automatic fine band does not fit the domain; increase the domain top or reduce fine_region_height")
    # Validate the minimum coefficient scale before generating a large vector.
    effective_faces([fine_h, fine_h])
    fine = np.full(count, fine_h, dtype=np.float64)
    fine_actual_top = effective_faces(fine)[-1]
    remaining = top-fine_top

    def advance(z, actual_z, previous):
        # A float32 face just below a roof-buffer threshold must retain its cap.
        return min(previous*settings.growth_rate, cap(min(z, float(actual_z))))

    # The greedy path dominates every other feasible prefix because both caps
    # and thickness are nondecreasing. It determines the minimum upper count.
    slots, z, actual_z, previous = 0, fine_top, fine_actual_top, fine_h
    while z < top-tolerance64:
        if count+slots >= 10000:
            raise ValueError("Automatic grid exceeds 10000 layers; revise bounds or vertical settings")
        h = advance(z, actual_z, previous)
        z += h
        actual_z = np.float32(actual_z+np.float32(h))
        previous = h
        slots += 1
    if slots*fine_h > remaining+tolerance64:
        raise ValueError("Cannot fit the domain top with nondecreasing layers while preserving the fine band; "
                         "increase the top or adjust fine_region_height/first_layer_thickness")

    layers = list(fine)
    z, actual_z, previous = fine_top, fine_actual_top, fine_h
    tail_start = None
    for left in range(slots, 0, -1):
        ceiling = advance(z, actual_z, previous)
        average = (top-z)/left
        h = min(ceiling, average)
        if average <= ceiling and tail_start is None:
            tail_start = len(layers)
        layers.append(h)
        z += h
        actual_z = np.float32(actual_z+np.float32(h))
        previous = h
    layers = np.ascontiguousarray(layers, dtype=np.float64)
    faces = effective_faces(layers)
    native = layers.astype(np.float32).astype(np.float64)
    # Constraint tolerances cover narrowing of layer operands; they do not
    # permit skipping roof caps or accepting collapsed native coordinates.
    if (np.any(native < hmin*(1-_FLOAT_TOL))
            or np.any(native[1:] < native[:-1]*(1-_FLOAT_TOL))
            or np.any(native[1:] > native[:-1]*settings.growth_rate*(1+_FLOAT_TOL))):
        raise ValueError("Automatic float32 layers violate thickness/growth constraints; revise vertical settings")
    planned_faces = np.r_[0.0, np.cumsum(layers)]
    caps = np.array([cap(float(actual)) for actual in faces[:-1]])
    if np.any(native > caps*(1+_FLOAT_TOL)):
        raise ValueError("Automatic float32 layers cross a building-region cap; revise vertical settings")
    if np.any(native[:count] > hmax*(1+_FLOAT_TOL)):
        raise ValueError("Automatic fine layers exceed the pedestrian limit after float32 conversion")
    centres = np.float32(0.5)*(faces[:-1]+faces[1:])
    if len(centres) < 3 or float(centres[2]) > zp or not float(centres[0]) <= zp <= float(centres[-1]):
        raise ValueError("Automatic grid must bracket pedestrian_height at the third centre or higher; "
                         "increase the domain top or revise fine-band settings")
    unit_roundoff = float(np.finfo(np.float32).eps)/2
    gamma = (len(layers)+1)*unit_roundoff/(1-(len(layers)+1)*unit_roundoff)
    endpoint_tolerance = gamma*top
    if abs(float(faces[-1])-top) > endpoint_tolerance or abs(float(planned_faces[-1])-top) > tolerance64:
        raise ValueError("Automatic endpoint cannot be represented within accumulation tolerance")
    return layers, dict(
        uniform=bool(np.all(native == native[0])),
        effective_settings=dict(resolution=r, pedestrian_height=zp, growth_rate=settings.growth_rate,
            base_minimum_thickness=base, minimum_thickness=hmin, maximum_fine_thickness=hmax,
            max_aspect_ratio=settings.max_aspect_ratio, preferred_first_layer_thickness=preferred,
            constrained_target_thickness=target, planned_fine_thickness=fine_h,
            solver_fine_thickness=float(native[0]), fine_layer_count=count,
            requested_fine_region_height=length, planned_fine_region_height=fine_top,
            effective_fine_region_height=float(faces[count]), upper_layer_cap=upper_cap,
            fine_band_extended=bool(fine_top > length), first_layer_target_adjustment=float(native[0])-preferred),
        endpoint_fit=dict(method="greedy count with constant tail", tail_start_index=tail_start,
            requested_top=top, planned_top=float(planned_faces[-1]), effective_top=float(faces[-1]),
            coordinate_error=float(faces[-1])-top, accumulation_tolerance=endpoint_tolerance),
        constraint_relative_tolerance=_FLOAT_TOL,
        constraint_basis="solver thicknesses; conservative planning and effective lower-face cap checks",
        planned_faces=planned_faces.tolist(), solver_layer_thicknesses=native.tolist(),
    )
