"""Physical wind arrays, plane/probe sampling and DTCC grid conversion."""

from dataclasses import dataclass, field
from copy import deepcopy
from itertools import product
import json
from numbers import Real

import numpy as np
from dtcc_core.model import Bounds, Field, Transform, VolumeGrid
from . import _qes


from ._statistics import _stress_validity, _velocity_magnitude, _streamwise_std, _turbulence_intensity


def _qualification(metadata, diagnostics):
    """Fresh public views of existing evidence; never a second live record."""
    solver = metadata.get("solver") or {}
    spec, record = solver.get("spec", {}), solver.get("record")
    mode = "adaptive" if spec.get("policy") is not None else (
        "bounded" if spec.get("max_solve_seconds") is not None else "legacy")
    termination = record["termination_reason"] if record is not None else (
        "legacy_tolerance" if diagnostics.converged else "iteration_limit")
    assessment = ("not_requested" if mode != "adaptive" else record["accuracy_status"])
    reason = record.get("assessment_reason") if record is not None else None
    solver_view = dict(mode=mode, method=record["method"] if record is not None else _qes.legacy_method_id,
        execution=termination if termination in ("iteration_limit", "time_limit") else "completed",
        termination_reason=termination, legacy_converged=diagnostics.converged,
        assessment=assessment, assessment_scope=record.get("assessment_scope") if record is not None else None,
        assessment_reason=reason, exclusions=record.get("exclusions",[]) if record is not None else [],
        pending_runtime_checks=[])
    profile, turbulence = metadata.get("profile") or {}, metadata.get("turbulence")
    grid = metadata.get("domain", {}).get("vertical_grid", {})
    return deepcopy(dict(solver=solver_view,
        profile=dict(kind=profile.get("kind"), experimental=profile.get("experimental"),
                     caveats=profile.get("caveats", [])),
        turbulence=None if turbulence is None else dict(status="screening",
            mixing_length=turbulence.get("mixing_length"), numerics_version=turbulence.get("numerics_version"),
            caveats=turbulence.get("caveats", []), wind_basis={key:solver_view[key] for key in
                ("execution", "legacy_converged", "assessment", "assessment_scope")}),
        vertical_grid=dict(mode=grid.get("mode", "uniform"),
                           policy_status=grid.get("policy_status", "fixed"))))


@dataclass(frozen=True)
class TurbulenceFields:
    """Owned raw float32 turbulence and independent bool masks on (z,y,x).

    Stress order is xx,xy,xz,yy,yz,zz in m²/s²; tke is QES's separately
    scaled kinetic energy, co_eps is C0*epsilon (m²/s³), and mixing_length is
    in metres. Uncomputed float entries are NaN. stress_valid is a snapshot;
    derived properties reclassify edited tensors. Scalars describe the solve.
    """
    stress: np.ndarray
    tke: np.ndarray
    co_eps: np.ndarray
    mixing_length: np.ndarray
    computed: np.ndarray
    capped: np.ndarray
    stress_valid: np.ndarray
    friction_velocity: float
    reference_speed: float
    reference_height: float
    roughness_length: float
    displacement_height: float


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
    def __init__(self, diagnostics, record=None):
        self.diagnostics = diagnostics
        self.record = record
        super().__init__(f"Wind solve did not converge after {diagnostics.iterations} iterations: "
                         f"maximum Lagrange multiplier change {diagnostics.max_lagrange_multiplier_change:g} "
                         f"> tolerance {diagnostics.tolerance:g}"
                         + (f" (termination: {record['termination_reason']})" if record else ""))


class _SampleStatistics:
    """Derived values recheck mutable tensors and retain contributor validity."""

    @property
    def streamwise_std(self):
        if self.stress is None:
            raise ValueError("Sample has no turbulence; run with turbulence=Turbulence()")
        contributors = self._stress_contributors_valid
        if contributors is None:
            contributors = self.stress_valid if self.stress_valid is not None else True
        return _streamwise_std(self.stress,self.velocity,self.valid & contributors)

    @property
    def turbulence_intensity(self):
        return _turbulence_intensity(self.streamwise_std,self.velocity)



@dataclass(frozen=True)
class WindSample(_SampleStatistics):
    """Owned horizontal sample at native x/y centres, in the result's frame.

    ``velocity`` is float64 (y, x, component), in m/s. Invalid vectors and
    speeds are NaN; ``valid`` is a (y, x) boolean mask. Heights are metres above
    flat ground. Linear samples outside the centre range have no sampled height.
    Widen x/y to float64 before adding ``origin`` for global coordinates;
    add origin[2] to sampled height for global elevation.
    Arrays remain editable and do not share storage with the source result.
    Optional stress is float64 (y,x,6) in xx,xy,xz,yy,yz,zz order.
    stress_valid is a sampling-time snapshot; statistics recheck current
    tensors and retain evidence of invalid contributing cells.
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
    stress: np.ndarray | None = None
    stress_valid: np.ndarray | None = None
    # Preserve invalid-contributor evidence independently of editable tensors
    # and their public validity snapshot. Rechecking an interpolant alone can
    # conceal a materially indefinite contributor.
    _stress_contributors_valid: np.ndarray | None = field(default=None,repr=False,compare=False,kw_only=True)

    @property
    def speed(self):
        """Magnitude of the sampled mean velocity vector, in m/s."""
        return np.linalg.norm(self.velocity, axis=-1)



@dataclass(frozen=True)
class WindPointSample(_SampleStatistics):
    """Owned probe arrays in input order, with coordinates in ``frame``.

    ``points`` and ``sampled_points`` are float64 (n,3), in metres. The latter
    contains selected centres for nearest sampling, requested positions for
    linear sampling, and NaN where geometric support is unavailable.
    ``velocity`` is float64 (n,3), in m/s; invalid vectors are NaN and ``valid``
    is a separate (n,) bool mask. Coordinates retain geometric support even
    when contributing cells are solid or have nonfinite velocity.
    Optional float64 ``stress`` is (n,6), ordered xx,xy,xz,yy,yz,zz in m²/s².
    Its validity and derived statistics follow the rules of ``WindSample``.
    All arrays are editable and independent of the input points and result.
    """
    points: np.ndarray
    sampled_points: np.ndarray
    velocity: np.ndarray
    valid: np.ndarray
    method: str
    frame: str
    origin: tuple[float, float, float]
    crs: str | None
    stress: np.ndarray | None = None
    stress_valid: np.ndarray | None = None
    _stress_contributors_valid: np.ndarray | None = field(default=None, repr=False, compare=False, kw_only=True)

    @property
    def speed(self):
        """Magnitude of the sampled mean velocity vector, in m/s."""
        return _velocity_magnitude(self.velocity)



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
    turbulence: TurbulenceFields | None = None

    @property
    def solver(self):
        """Authoritative solver specification, raw record and environment."""
        return self.metadata.get("solver")

    @property
    def qualification(self):
        """Derived numerical/model scope, independent of field validity masks.

        Every access returns a fresh dictionary. Native acceptance never implies
        turbulence/gust qualification or replaces legacy convergence evidence.
        """
        return _qualification(self.metadata, self.diagnostics)

    @property
    def speed(self):
        """Magnitude of mean velocity in float64, in m/s."""
        return _velocity_magnitude(self.velocity)

    @property
    def reference_speed(self):
        """Speed used to normalize this background shape, or None if unavailable."""
        reference = (self.metadata.get("profile") or {}).get("reference")
        if reference is not None:
            return reference["speed"]
        return None

    @property
    def reference_direction(self):
        """Declared meteorological direction, or None for a calm reference."""
        reference = (self.metadata.get("profile") or {}).get("reference")
        return reference.get("direction") if reference is not None and reference["speed"] > 0 else None

    @property
    def speedup(self):
        """Mean speed / declared reference speed; NaN for calm/missing reference."""
        reference = self.reference_speed
        speed = self.speed
        return speed / reference if reference is not None and reference > 0 else np.full_like(speed, np.nan)

    @property
    def streamwise_std(self):
        if self.turbulence is None:
            raise ValueError("Result has no turbulence; run with turbulence=Turbulence()")
        return _streamwise_std(self.turbulence.stress,self.velocity,
                               self.turbulence.computed & ~self.solid_mask)

    @property
    def turbulence_intensity(self):
        return _turbulence_intensity(self.streamwise_std,self.velocity)

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
        Optional stresses use the same contributors. Uncomputed stresses are
        NaN; invalid computed tensors remain available and disqualify derived
        statistics even when their interpolated tensor is positive semidefinite.
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
        stress = stress_valid = contributors = None
        if self.turbulence is not None:
            fields = self.turbulence
            if fields.stress.shape != (*shape,6) or fields.computed.shape != shape:
                raise ValueError("Turbulence stress and coverage must match the result's coordinate axes")
            stress = np.full((*plane_shape,6),np.nan,dtype=np.float64)
            contributors = np.zeros(plane_shape,dtype=bool)
            if indices is not None:
                lo,hi = indices
                covered = fields.computed[lo].copy()
                stress = fields.stress[lo].astype(np.float64,copy=True)
                contributors = _stress_validity(stress)[0] & covered
                if hi != lo:
                    other = fields.stress[hi].astype(np.float64)
                    covered &= fields.computed[hi]
                    contributors &= _stress_validity(other)[0] & covered
                    with np.errstate(invalid="ignore",over="ignore"):
                        stress += weight*(other-stress)
                stress[~covered] = np.nan
            stress_valid = contributors & _stress_validity(stress)[0]
        return WindSample(velocity, valid, np.array(self.x, copy=True), np.array(self.y, copy=True),
                          requested, sampled, method, self.origin, self.crs,stress,stress_valid,
                          _stress_contributors_valid=contributors)

    def sample_points(self, points, method="nearest", *, frame="local") -> WindPointSample:
        """Sample finite probe coordinates supplied as an (n,3) numeric array.

        Coordinates are local metres by default: z is height above flat ground.
        ``frame='global'`` translates centres and domain faces by ``origin``
        (including ground elevation). Comparisons and interpolation use float64
        in the requested frame, so represented global centres remain exact.
        A global frame must distinguish adjacent centres in float64. Returned
        point coordinates stay in the requested frame; no CRS reprojection is
        performed.

        Nearest chooses a centre on each axis, breaking ties toward the lower
        index and clipping within physical boundary faces. Linear performs
        trilinear component interpolation on the stored centres, including
        nonuniform z; exact centres use only that cell on the relevant axis.
        Points outside the physical domain, or outside the centre range with
        linear sampling, yield NaN vectors and false validity without raising.
        Every contributing cell must be fluid (flags other than 0/2) with finite
        velocity. Optional stresses follow ``sample``'s independent coverage
        and contributor validity rules. Work/storage scale with probe count,
        without copying or masking the full wind volume.
        """
        if not isinstance(method, str) or method not in ("nearest", "linear"):
            raise ValueError("method must be 'nearest' or 'linear'")
        if not isinstance(frame, str) or frame not in ("local", "global"):
            raise ValueError("frame must be 'local' or 'global'")
        try:
            requested = np.asarray(points)
            if requested.ndim != 2 or requested.shape[1] != 3 or requested.dtype.kind not in "iuf":
                raise ValueError
            requested = np.array(requested, dtype=np.float64, copy=True)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("points must be a finite numeric array with shape (n, 3)") from error
        if not np.isfinite(requested).all():
            raise ValueError("points must be a finite numeric array with shape (n, 3)")
        axes = [np.asarray(axis, dtype=np.float64) for axis in (self.x, self.y, self.z)]
        for name, axis in zip("xyz", axes):
            if (axis.ndim != 1 or not len(axis) or not np.isfinite(axis).all()
                    or np.any(np.diff(axis) <= 0)):
                raise ValueError(f"{name} must contain finite, strictly increasing cell centres")
        shape = tuple(len(axis) for axis in reversed(axes))
        if self.velocity.shape != (*shape, 3) or self.cell_flags.shape != shape:
            raise ValueError("Velocity and cell flags must match the result's coordinate axes")
        if isinstance(self.resolution, (bool, np.bool_)) or not isinstance(self.resolution, Real):
            raise ValueError("resolution must be finite and positive")
        try:
            spacing = float(self.resolution)
        except (ValueError, OverflowError) as error:
            raise ValueError("resolution must be finite and positive") from error
        if not np.isfinite(spacing) or spacing <= 0:
            raise ValueError("resolution must be finite and positive")
        if self.z_faces is None:
            top = float(np.cumsum(np.full(len(self.z), self.resolution, dtype=np.float32),
                                  dtype=np.float32)[-1])
        else:
            faces = np.asarray(self.z_faces, dtype=np.float64)
            if (faces.shape != (len(self.z) + 1,) or not np.isfinite(faces).all()
                    or faces[0] != 0 or np.any(np.diff(faces) <= 0)):
                raise ValueError("z_faces must contain increasing physical faces starting at zero")
            top = float(faces[-1])
        lower = np.array([axes[0][0] - spacing/2, axes[1][0] - spacing/2, 0])
        # Centre coordinates are rounded individually in native float32.
        # Count * spacing recovers physical extents without accumulating the
        # final centre's rounding error at the outer horizontal faces.
        upper = lower + np.array([len(self.x)*spacing, len(self.y)*spacing, top])
        if frame == "global":
            try:
                origin = np.asarray(self.origin, dtype=np.float64)
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("origin must contain three finite coordinates for global sampling") from error
            if origin.shape != (3,) or not np.isfinite(origin).all():
                raise ValueError("origin must contain three finite coordinates for global sampling")
            with np.errstate(over="ignore", invalid="ignore"):
                axes = [axis + offset for axis, offset in zip(axes, origin)]
                lower, upper = lower + origin, upper + origin
            if (not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(upper <= lower)
                    or any(not np.isfinite(axis).all() or np.any(axis[1:] <= axis[:-1]) for axis in axes)):
                raise ValueError("global coordinate precision must preserve finite, distinct cell centres and faces")
        supported = ((requested >= lower) & (requested <= upper)).all(axis=1)
        lows, highs, weights = [], [], []
        sampled = np.empty_like(requested)
        for dim, axis in enumerate(axes):
            values = requested[:, dim]
            insertion = np.searchsorted(axis, values)
            lo = np.clip(insertion - 1, 0, len(axis) - 1)
            hi = np.clip(insertion, 0, len(axis) - 1)
            if method == "nearest":
                selected = np.where(values - axis[lo] <= axis[hi] - values, lo, hi)
                lo = hi = selected
                sampled[:, dim] = axis[selected]
                weight = np.zeros(len(requested), dtype=np.float64)
            else:
                supported &= (values >= axis[0]) & (values <= axis[-1])
                lo = np.where(values == axis[hi], hi, lo)
                weight = np.divide(values - axis[lo], axis[hi] - axis[lo],
                                   out=np.zeros(len(requested)), where=hi != lo)
                sampled[:, dim] = values
            lows.append(lo)
            highs.append(hi)
            weights.append(weight)
        sampled[~supported] = np.nan

        velocity = np.zeros((len(requested), 3), dtype=np.float64)
        valid = supported.copy()
        fields = self.turbulence
        stress = stress_valid = contributors = None
        if fields is not None:
            if fields.stress.shape != (*shape, 6) or fields.computed.shape != shape:
                raise ValueError("Turbulence stress and coverage must match the result's coordinate axes")
            stress = np.zeros((len(requested), 6), dtype=np.float64)
            covered = supported.copy()
            contributors = supported.copy()
        for corner in product((0, 1), repeat=3):
            active = supported.copy()
            weight = np.ones(len(requested), dtype=np.float64)
            indices = []
            for dim, high in enumerate(corner):
                indices.append(highs[dim] if high else lows[dim])
                if high:
                    active &= highs[dim] != lows[dim]
                weight *= weights[dim] if high else 1 - weights[dim]
            rows = np.flatnonzero(active)
            if not len(rows):
                continue
            index = tuple(indices[dim][rows] for dim in (2, 1, 0))
            values = np.asarray(self.velocity[index], dtype=np.float64)
            flags = self.cell_flags[index]
            valid[rows] &= (flags != 0) & (flags != 2) & np.isfinite(values).all(axis=-1)
            with np.errstate(invalid="ignore", over="ignore"):
                velocity[rows] += weight[rows, None] * values
            if fields is not None:
                values = np.asarray(fields.stress[index], dtype=np.float64)
                covered[rows] &= fields.computed[index]
                contributors[rows] &= fields.computed[index] & _stress_validity(values)[0]
                with np.errstate(invalid="ignore", over="ignore"):
                    stress[rows] += weight[rows, None] * values
        valid &= np.isfinite(velocity).all(axis=-1)
        velocity[~valid] = np.nan
        if fields is not None:
            stress[~covered] = np.nan
            stress_valid = contributors & _stress_validity(stress)[0]
        return WindPointSample(requested, sampled, velocity, valid, method, frame, self.origin, self.crs,
                               stress, stress_valid, _stress_contributors_valid=contributors)

    def to_dtcc(self, *, include_speedup=False):
        """Return independent cell fields in DTCC's y, x, z-fastest order.

        This matches VolumeGrid.coordinates()'s current meshgrid ``xy`` order.
        Grid bounds are local; its Transform carries origin and CRS. Cell
        ordering is isolated here so a future DTCC convention can replace it.
        Optional turbulence exports raw stress/TKE, streamwise statistics and
        a freshly classified uint8 covariance-validity mask. Uncomputed floats
        are NaN. Invalid raw tensors are retained; their derived statistics and
        statistics with undefined mean direction are NaN. Field descriptions
        carry the model provenance and unvalidated-gust screening limitation.
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
        qualification = self.qualification
        qualification_json = json.dumps(qualification, sort_keys=True, allow_nan=False)
        grid.add_field(Field(name="velocity", unit="m/s", values=velocity, dim=3, association="cell",
                             description="Wind velocity (u, v, w); cell order y, x, z fastest; qualification=" + qualification_json))
        grid.add_field(Field(name="speed", unit="m/s", values=np.linalg.norm(velocity.astype(np.float64), axis=1),
                             association="cell", description="Wind speed magnitude"))
        grid.add_field(Field(name="cell_flags", unit="1", values=flags, association="cell",
                             description="QES cell classification; 0 building, 2 terrain"))
        if include_speedup:
            grid.add_field(Field(name="speedup", unit="1", values=self.speedup.transpose(1, 2, 0).reshape(-1).copy(),
                                 association="cell", description="Mean speed / declared profile reference; undefined for calm reference"))
        if self.turbulence is not None:
            fields = self.turbulence
            computed = fields.computed
            # Snapshot current tensors, independently of the editable native
            # validity snapshot. Covariance validity does not require a mean
            # direction and is independent of capping.
            validity = _stress_validity(fields.stress)
            valid = validity[0] & computed
            std = _streamwise_std(fields.stress,self.velocity,computed & ~self.solid_mask,validity=validity)
            intensity = _turbulence_intensity(std,self.velocity)
            metadata = self.metadata.get("turbulence",{})
            revision = self.metadata.get("versions",{}).get("qes",{}).get("revision","unspecified")
            provenance = ("QES-Turb algebraic mixing-length screening model; "
                f"numerics_version={metadata.get('numerics_version','unspecified')}; "
                f"mixing_length={metadata.get('mixing_length','unspecified')}; QES revision={revision}; "
                "not validated for pedestrian gusts; wind_basis=" +
                json.dumps(qualification["turbulence"]["wind_basis"] if qualification["turbulence"] is not None else
                    {key:qualification["solver"][key] for key in ("execution","legacy_converged","assessment","assessment_scope")},
                    sort_keys=True, allow_nan=False))
            exports = (
                ("stress","m^2/s^2",6,np.where(computed[...,None],fields.stress,np.nan),
                 "Raw stress (xx, xy, xz, yy, yz, zz); invalid computed tensors retained; uncomputed NaN"),
                ("tke","m^2/s^2",1,np.where(computed,fields.tke,np.nan),
                 "QES TKE before stress anisotropy scaling, not half the stress trace; uncomputed NaN"),
                ("streamwise_std","m/s",1,std,
                 "Standard deviation projected along the current 3D mean direction; uncomputed, invalid stress "
                 "and undefined direction NaN; roundoff-sized negative variance clamped to zero"),
                ("turbulence_intensity","1",1,intensity,
                 "Streamwise standard deviation / mean speed; uncomputed, invalid stress and undefined direction NaN"),
                ("stress_valid","1",1,valid.astype(np.uint8),
                 "Current covariance validity, encoded 0/1; finite lambda_min >= "
                 "-32 * eps(float32) * max(abs(eigenvalues)); finite zero valid; uncomputed 0; "
                 "independent of capping and mean direction"),
            )
            for name,unit,dim,values,description in exports:
                ordered = (values.transpose(1,2,0,3).reshape(-1,dim).copy() if dim > 1 else
                           values.transpose(1,2,0).reshape(-1).copy())
                grid.add_field(Field(name=name,unit=unit,dim=dim,values=ordered,association="cell",
                                     description=f"{description}; cell order y, x, z fastest. {provenance}"))
        return grid
