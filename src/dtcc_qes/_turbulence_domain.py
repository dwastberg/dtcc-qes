"""Format the native coordinate-only turbulence reference/margin contract."""
import numpy as np
from . import _qes


def turbulence_reference_height(heights,roughness_length):
    """Native ascending float32 accumulation, shared with QES-Turb."""
    with np.errstate(over="ignore",invalid="ignore"):
        values=np.asarray(heights,dtype=np.float32)
    if values.ndim!=1:
        raise ValueError("Turbulence building heights must be positive finite float32 values")
    return _qes._turbulence_reference(values.tolist(),roughness_length)["reference_height"]


def turbulence_top(z_ref,spacing):
    """Initial uniform-grid target; effective faces determine final acceptance."""
    return max(z_ref+3*spacing,15.)


def _analysis(faces,z_ref,thickness,nx,ny,max_cells):
    with np.errstate(over="ignore",invalid="ignore"):
        faces=np.asarray(faces,dtype=np.float32)
    if faces.ndim!=1:
        raise ValueError("Turbulence faces must be finite increasing float32 heights starting at zero")
    return faces,_qes._turbulence_extension(faces.tolist(),z_ref,thickness,nx,ny,max_cells)


def _margin_message(faces,reference,analysis):
    return (f"Turbulence domain top {faces[-1]:.9g} m is insufficient for zRef {reference:.9g} m "
        "and the 15 m rotation reference; layer margin requires two physical layers "
        f"above the sampled layer (reference index {analysis['reference_index']}, maximum {analysis['maximum_index']}). ")


def _limit_message(faces,reference,thickness,analysis):
    return (_margin_message(faces,reference,analysis)+f"A constant-thickness tail of {thickness:.9g} m cannot "
        f"satisfy the margin within the {analysis['limit']}.")


def extend_turbulence_faces(faces,z_ref,thickness,*,nx=1,ny=1,max_cells=2**63-1):
    """Shortest prefix-preserving native constant tail; coordinate storage only."""
    faces,analysis=_analysis(faces,z_ref,thickness,nx,ny,max_cells)
    if analysis["limit"]:
        raise ValueError(_limit_message(faces,z_ref,thickness,analysis))
    return np.asarray(analysis["faces"],dtype=np.float32)


def check_turbulence_faces(faces,z_ref,*,last_thickness=None,nx=1,ny=1,max_cells=2**63-1):
    """Check fixed faces and explain the native sufficient top or limiting reason."""
    if last_thickness is None:
        values=np.asarray(faces,dtype=np.float32)
        last_thickness=float(values[-1]-values[-2])
    faces,analysis=_analysis(faces,z_ref,last_thickness,nx,ny,max_cells)
    if analysis["has_margin"]:
        return
    if analysis["limit"]:
        raise ValueError(_limit_message(faces,z_ref,last_thickness,analysis))
    raise ValueError(_margin_message(faces,z_ref,analysis)+f"Appending {analysis['added_layers']} layers of "
        f"{last_thickness:.9g} m while preserving the existing layers gives a sufficient top of {analysis['faces'][-1]:.9g} m.")
