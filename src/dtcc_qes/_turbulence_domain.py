"""Reference-height and prefix-preserving domain policy for QES turbulence."""

import numpy as np


def turbulence_reference_height(heights, roughness_length):
    """Match QES's float32 mean in ascending native building-height order."""
    with np.errstate(over="ignore", invalid="ignore"):
        native = np.sort(np.asarray(heights, dtype=np.float32))
        if native.size:
            if native.ndim != 1 or not np.isfinite(native).all() or np.any(native <= 0):
                raise ValueError("Turbulence building heights must be positive finite float32 values")
            total = np.cumsum(native, dtype=np.float32)[-1]
            reference = np.float32(3 * float(np.float32(total / np.float32(len(native)))))
        else:
            reference = np.float32(100 * float(np.float32(roughness_length)))
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError("Turbulence reference height must be positive and finite in float32")
    return float(reference)


def turbulence_top(z_ref, spacing):
    """Initial uniform-grid target; effective faces determine final acceptance."""
    return max(z_ref + 3 * spacing, 15.0)


def _has_margin(faces, reference):
    return len(faces) >= 4 and faces[-4] >= reference and faces[-1] >= 15


def _margin_message(faces, reference):
    index = int(np.searchsorted(faces, reference)) + 1  # QES has a ground ghost face.
    return (f"Turbulence domain top {faces[-1]:.9g} m is insufficient for zRef {reference:.9g} m "
            "and the 15 m rotation reference; layer margin requires two physical layers "
            f"above the sampled layer (reference index {index}, maximum {len(faces)-3}). ")


def extend_turbulence_faces(faces, z_ref, thickness, *, nx=1, ny=1, max_cells=2**63-1):
    """Return the shortest constant tail satisfying the native layer margin.

    Faces and thickness are actual float32 operands. Only coordinate storage is
    allocated. Both face and centre arithmetic follow qes::Domain; the existing
    final-layer coefficient checks also cover the repeated thickness.
    """
    faces = np.asarray(faces, dtype=np.float32)
    if (faces.ndim != 1 or not 3 <= len(faces) <= 10001 or faces[0] != 0
            or not np.isfinite(faces).all() or np.any(np.diff(faces) <= 0)):
        raise ValueError("Turbulence faces must be finite increasing float32 heights starting at zero")
    reference, thickness = float(z_ref), np.float32(thickness)
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError("Turbulence reference height must be positive and finite")
    if not np.isfinite(thickness) or thickness <= 0:
        raise ValueError("Turbulence tail thickness must be positive and finite in float32")
    if _has_margin(faces, reference):
        return faces
    message = _margin_message(faces, reference)
    extended = list(faces)
    with np.errstate(over="ignore", invalid="ignore"):
        while not _has_margin(extended, reference):
            layers = len(extended)-1
            limit = None
            if layers >= 10000:
                limit = "10000-layer limit"
            elif nx*ny*(layers+1) > max_cells:
                limit = "max_cells limit"
            elif (nx+1)*(ny+1)*(layers+3) > np.iinfo(np.int32).max:
                limit = "native index limit"
            top = np.float32(extended[-1]+thickness)
            previous_centre = np.float32(.5)*np.float32(extended[-2]+extended[-1])
            centre = np.float32(.5)*np.float32(extended[-1]+top)
            if limit is None and (not np.isfinite(top) or top <= extended[-1]):
                limit = "float32 coordinate progress limit"
            if limit is None and (not np.isfinite(centre) or centre <= previous_centre):
                limit = "float32 cell-centre progress limit"
            if limit is not None:
                raise ValueError(message + f"A constant-thickness tail of {thickness:.9g} m cannot "
                                 f"satisfy the margin within the {limit}.")
            extended.append(top)
    return np.asarray(extended, dtype=np.float32)


def check_turbulence_faces(faces, z_ref, *, last_thickness=None, nx=1, ny=1, max_cells=2**63-1):
    """Check explicit faces; report a sufficient prefix-preserving extension.

    Supply last_thickness when native solver operands are available: subtraction
    of accumulated faces can differ from the original layer thickness.
    """
    faces = np.asarray(faces, dtype=np.float32)
    if faces.ndim != 1 or len(faces) < 3:
        raise ValueError("Turbulence faces require at least two physical layers")
    thickness = (faces[-1]-faces[-2]) if last_thickness is None else last_thickness
    extended = extend_turbulence_faces(faces, z_ref, thickness, nx=nx, ny=ny, max_cells=max_cells)
    if len(extended) != len(faces):
        raise ValueError(_margin_message(faces, z_ref) +
                         f"Appending {len(extended)-len(faces)} layers of {np.float32(thickness):.9g} m "
                         f"while preserving the existing layers gives a sufficient top of {extended[-1]:.9g} m.")
