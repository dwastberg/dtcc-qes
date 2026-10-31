"""Physical wind arrays, height sampling and DTCC uniform-grid conversion."""

from dataclasses import dataclass
from numbers import Real

import numpy as np
from dtcc_core.model import Bounds, Field, Transform, VolumeGrid


@dataclass(frozen=True)
class SolveDiagnostics:
    """Convergence uses multiplier change; divergence metrics are in s^-1.

    Divergence excludes prescribed lateral cells and the highest physical layer.
    The last solved band has an uncorrected upper face and is reported separately.
    Metrics are None when no fluid cells were assessed in the respective region.
    """
    iterations: int
    max_lagrange_multiplier_change: float
    tolerance: float
    converged: bool
    max_divergence: float | None = None
    rms_divergence: float | None = None
    top_band_max_divergence: float | None = None
    divergence_cell_count: int | None = None
    top_band_cell_count: int | None = None
    precision: str = "float32"


class ConvergenceError(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__(f"Wind solve did not converge after {diagnostics.iterations} iterations: "
                         f"maximum Lagrange multiplier change {diagnostics.max_lagrange_multiplier_change:g} "
                         f"> tolerance {diagnostics.tolerance:g}")


@dataclass(frozen=True)
class WindSample:
    """Owned horizontal sample at native x/y centres, in the result's frame.

    ``velocity`` is float64 (y, x, component), in m/s. Invalid vectors and
    speeds are NaN; ``valid`` is a (y, x) boolean mask. Heights are metres above
    flat ground. Linear samples outside the centre range have no sampled height.
    Widen x/y to float64 before adding ``origin`` for global coordinates;
    add origin[2] to sampled height for global elevation.
    Arrays remain editable and do not share storage with the source result.
    """
    velocity: np.ndarray
    valid: np.ndarray
    x: np.ndarray
    y: np.ndarray
    requested_height: float
    sampled_height: float | None
    method: str
    origin: tuple[float, float, float]
    crs: str | None

    @property
    def speed(self):
        """Magnitude of the sampled mean velocity vector, in m/s."""
        return np.linalg.norm(self.velocity, axis=-1)


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
    z_faces: np.ndarray | None = None

    @property
    def dz(self):
        """Effective physical layer heights from the returned face coordinates."""
        if self.z_faces is not None:
            return np.diff(self.z_faces)
        return np.diff(np.r_[np.float32(0), np.cumsum(
            np.full(len(self.z), self.resolution, dtype=np.float32), dtype=np.float32)])

    @property
    def vertical_uniform(self):
        """Whether solver layer thicknesses are equal (before coordinate rounding)."""
        record = self.metadata.get("domain", {}).get("vertical_grid", {})
        if "uniform" in record:
            return record["uniform"]
        return self.z_faces is None or bool(np.all(self.dz == self.dz[0]))

    @property
    def solid_mask(self):
        return (self.cell_flags == 0) | (self.cell_flags == 2)

    def sample(self, height, method="nearest") -> WindSample:
        """Sample a horizontal plane at a height above flat ground.

        Nearest selects one centre (lower index on ties), clipping to endpoint
        centres within the physical domain. Linear interpolates components
        between centres, then computes speed; exact centres use only that cell.
        Linear sampling outside the centre range returns invalid values without
        extrapolation. Every contributing cell must be fluid with finite
        velocity. Flags 0/2 are solid; air parameterization flags remain valid.
        Requested heights are compared in float64, without snapping to float32.
        """
        if not isinstance(method, str) or method not in ("nearest", "linear"):
            raise ValueError("method must be 'nearest' or 'linear'")
        if isinstance(height, (bool, np.bool_)) or not isinstance(height, Real):
            raise ValueError("height must be a finite number")
        try:
            requested = float(height)
        except (ValueError, OverflowError) as error:
            raise ValueError("height must be a finite number") from error
        if not np.isfinite(requested):
            raise ValueError("height must be a finite number")
        # Widen the stored coordinates, not the request: NumPy's weak scalar
        # promotion would otherwise round a Python float to a float32 centre.
        centres = np.asarray(self.z, dtype=np.float64)
        if (centres.ndim != 1 or not len(centres) or not np.isfinite(centres).all()
                or np.any(np.diff(centres) <= 0)):
            raise ValueError("z must contain finite, strictly increasing cell centres")
        shape = (len(centres), len(self.y), len(self.x))
        if self.velocity.shape != shape + (3,) or self.cell_flags.shape != shape:
            raise ValueError("Velocity and cell flags must match the result's coordinate axes")
        if self.z_faces is None:
            faces = np.cumsum(np.full(len(centres), self.resolution, dtype=np.float32), dtype=np.float32)
        else:
            faces = np.asarray(self.z_faces)
        top = float(faces[-1])
        if not np.isfinite(top) or not 0 <= requested <= top:
            raise ValueError("height must be inside the physical domain above flat ground")

        upper = int(np.searchsorted(centres, requested))
        sampled = None
        indices = None
        if method == "nearest":
            if upper == 0:
                selected = 0
            elif upper == len(centres):
                selected = upper - 1
            else:
                selected = upper - 1 if requested - centres[upper-1] <= centres[upper] - requested else upper
            indices = (selected, selected)
            sampled = float(centres[selected])
        elif upper < len(centres) and requested == centres[upper]:
            indices = (upper, upper)
            sampled = requested
        elif 0 < upper < len(centres):
            indices = (upper-1, upper)
            sampled = requested

        plane_shape = shape[1:]
        if indices is None:
            velocity = np.full(plane_shape + (3,), np.nan, dtype=np.float64)
            valid = np.zeros(plane_shape, dtype=bool)
        else:
            lo, hi = indices
            velocity = self.velocity[lo].astype(np.float64, copy=True)
            flags = self.cell_flags[lo]
            valid = (flags != 0) & (flags != 2) & np.isfinite(velocity).all(axis=-1)
            if hi != lo:
                other = self.velocity[hi].astype(np.float64)
                flags = self.cell_flags[hi]
                valid &= (flags != 0) & (flags != 2) & np.isfinite(other).all(axis=-1)
                weight = (requested - centres[lo]) / (centres[hi] - centres[lo])
                with np.errstate(invalid="ignore", over="ignore"):
                    velocity += weight * (other - velocity)
                valid &= np.isfinite(velocity).all(axis=-1)
            velocity[~valid] = np.nan
        return WindSample(velocity, valid, np.array(self.x, copy=True), np.array(self.y, copy=True),
                          requested, sampled, method, self.origin, self.crs)

    def to_dtcc(self):
        """Return independent cell fields in DTCC's y, x, z-fastest order.

        This matches VolumeGrid.coordinates()'s current meshgrid ``xy`` order.
        Grid bounds are local; its Transform carries origin and CRS. Cell
        ordering is isolated here so a future DTCC convention can replace it.
        """
        if not self.vertical_uniform:
            raise ValueError("Nonuniform vertical layers cannot be represented by a uniform VolumeGrid; "
                             "use result.sample(height, method='linear') or the native arrays and z_faces")
        nz, ny, nx, _ = self.velocity.shape
        transform = Transform(srs=self.crs or "")
        transform.set_translation(*self.origin)
        grid = VolumeGrid(width=nx, height=ny, depth=nz, transform=transform)
        grid.bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=nx * self.resolution,
                             ymax=ny * self.resolution,
                             zmax=float(self.z_faces[-1]) if self.z_faces is not None else nz * self.resolution)
        velocity = self.velocity.transpose(1, 2, 0, 3).reshape(-1, 3).copy()
        flags = self.cell_flags.transpose(1, 2, 0).reshape(-1).copy()
        grid.add_field(Field(name="velocity", unit="m/s", values=velocity, dim=3, association="cell",
                             description="Wind velocity (u, v, w); cell order y, x, z fastest"))
        grid.add_field(Field(name="speed", unit="m/s", values=np.linalg.norm(velocity.astype(np.float64), axis=1),
                             association="cell", description="Wind speed magnitude"))
        grid.add_field(Field(name="cell_flags", unit="1", values=flags, association="cell",
                             description="QES cell classification; 0 building, 2 terrain"))
        return grid
