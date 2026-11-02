"""3DFACE geometry from the AIJ DXF files.

The AIJ drawings contain only 3DFACE and INSERT entities. Case E nests blocks
inside each other in a way that would duplicate the whole city when resolved
recursively, so callers take each block's *own* faces exactly once and place
them with an explicitly chosen insertion matrix.
"""

import ezdxf
import numpy as np
from ezdxf.math import Matrix44


def read(path):
    return ezdxf.readfile(path)


def faces(entities, matrix: Matrix44 | None = None) -> list[np.ndarray]:
    """Return the 3DFACEs of a layout or block as (3|4, 3) arrays.

    Nested INSERTs are skipped. Repeated consecutive vertices are dropped, so a
    triangle stored as a quad (vtx3 == vtx2) comes back with three vertices.
    """
    out = []
    for entity in entities:
        kind = entity.dxftype()
        if kind == "INSERT":
            continue
        if kind != "3DFACE":
            raise ValueError(f"Unsupported DXF entity {kind}; only 3DFACE and INSERT are expected")
        points = [entity.dxf.vtx0, entity.dxf.vtx1, entity.dxf.vtx2, entity.dxf.vtx3]
        if matrix is not None:
            points = list(matrix.transform_vertices(points))
        array = np.array([tuple(p) for p in points], dtype=np.float64)
        keep = np.r_[True, np.any(np.abs(np.diff(array, axis=0)) > 1e-12, axis=1)]
        array = array[keep]
        if len(array) > 3 and np.allclose(array[-1], array[0]):
            array = array[:-1]
        if len(array) >= 3:
            out.append(array)
    return out


def insert_matrix(entities, name: str) -> Matrix44:
    """Insertion matrix of block ``name`` in a layout or block.

    Raises unless the block is inserted exactly once, because otherwise the
    caller could not tell which placement is meant.
    """
    found = [e.matrix44() for e in entities if e.dxftype() == "INSERT" and e.dxf.name == name]
    if len(found) != 1:
        raise ValueError(f"Block {name!r} is inserted {len(found)} times, expected once")
    return found[0]


def block_faces(doc, name: str, matrix: Matrix44) -> list[np.ndarray]:
    """The block's own 3DFACEs (no nested INSERTs), placed with ``matrix``."""
    return faces(doc.blocks.get(name), matrix)


def chain(*matrices: Matrix44) -> Matrix44:
    """Compose insertion matrices, innermost first."""
    return Matrix44.chain(*matrices)
