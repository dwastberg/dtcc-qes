"""Physical wind arrays and conversion to DTCC's uniform VolumeGrid."""

from dataclasses import dataclass

import numpy as np
from dtcc_core.model import Bounds, Field, Transform, VolumeGrid


@dataclass(frozen=True)
class SolveDiagnostics:
    """Maximum Lagrange multiplier change is not a mass-conservation residual."""
    iterations: int
    max_lagrange_multiplier_change: float
    tolerance: float
    converged: bool


class ConvergenceError(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__(f"Wind solve did not converge after {diagnostics.iterations} iterations: "
                         f"maximum Lagrange multiplier change {diagnostics.max_lagrange_multiplier_change:g} "
                         f"> tolerance {diagnostics.tolerance:g}")


@dataclass(frozen=True)
class WindResult:
    """Owned arrays in the local frame; global coordinates add ``origin``.

    Velocity is float32 (z, y, x, component), in m/s, with components u/v/w.
    Axes are physical cell centres, without ghost layers. ``solid_mask`` marks
    QES classifications 0 (building) and 2 (terrain), excluding wake/cavity
    classifications, which describe air. Arrays and metadata remain editable.
    """
    velocity: np.ndarray
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    cell_flags: np.ndarray
    origin: tuple[float, float, float]
    crs: str | None
    resolution: float
    diagnostics: SolveDiagnostics
    metadata: dict

    @property
    def solid_mask(self):
        return (self.cell_flags == 0) | (self.cell_flags == 2)

    def to_dtcc(self):
        """Return independent cell fields in DTCC's y, x, z-fastest order.

        This matches VolumeGrid.coordinates()'s current meshgrid ``xy`` order.
        Grid bounds are local; its Transform carries origin and CRS. Cell
        ordering is isolated here so a future DTCC convention can replace it.
        """
        nz, ny, nx, _ = self.velocity.shape
        transform = Transform(srs=self.crs or "")
        transform.set_translation(*self.origin)
        grid = VolumeGrid(width=nx, height=ny, depth=nz, transform=transform)
        grid.bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=nx * self.resolution,
                             ymax=ny * self.resolution, zmax=nz * self.resolution)
        velocity = self.velocity.transpose(1, 2, 0, 3).reshape(-1, 3).copy()
        flags = self.cell_flags.transpose(1, 2, 0).reshape(-1).copy()
        grid.add_field(Field(name="velocity", unit="m/s", values=velocity, dim=3, association="cell",
                             description="Wind velocity (u, v, w); cell order y, x, z fastest"))
        grid.add_field(Field(name="speed", unit="m/s", values=np.linalg.norm(velocity.astype(np.float64), axis=1),
                             association="cell", description="Wind speed magnitude"))
        grid.add_field(Field(name="cell_flags", unit="1", values=flags, association="cell",
                             description="QES cell classification; 0 building, 2 terrain"))
        return grid
