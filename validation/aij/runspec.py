"""Run specifications (AIJ_VALIDATION_PLAN.md, Runs); the campaign matrices are in ``campaigns``.

A RunSpec fixes everything that changes a result. Its canonical JSON hashes to
the run key, so a stored record is reused only for an identical request.
Fields added after runs were stored (``LATER_FIELDS``) are left out of the
JSON at their defaults, so earlier runs keep their keys. Building
parameterizations are stored as their changes from the dtcc-qes defaults.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

from dtcc_qes import wind

SCHEMA = "aij-runspec-v1"
FINE_TOP = {"D": 24.0, "E": 36.0}  # m: uniform layers up to 2.4 x the 10 m blocks (D), 1.2 x the 30 m existing roofs (E)
MAX_ASPECT = 4.0  # stretched layers grow to at most this multiple of the probe-layer thickness
CITIES = ("exact", "qes_ready", "slabs_filled")
INFLOWS = ("measured", "power_law", "log", "canopy")
LATER_FIELDS = dict(parameterizations=(), canopy_roughness=None, blending_height=None, ground_roughness=None)


@dataclass(frozen=True)
class RunSpec:
    case: str  # "D" or "E"
    label: str  # the AIJ direction label
    direction: float  # meteorological degrees
    state: str = "-"  # Case E: "before" or "after"
    city: str = "exact"  # Case E: "exact", "qes_ready" (merged envelopes) or "slabs_filled" (slabs down to the ground)
    resolution: float = 2.0  # m, horizontal spacing
    layer: float | None = None  # m, probe-layer and fine-region thickness; None: min(resolution, 4)
    vertical: str = "stretched"  # "stretched" or "uniform"
    inflow: str = "measured"  # "measured", "power_law", "log" or "canopy" (measured, with an in-canopy log law)
    interpolation: str = "log_height"  # measured-profile interpolation
    min_detail: float | None = None  # wind.Footprints cleaning detail; None = strict footprints
    padding: float = 20.0  # m, Case D horizontal padding around the footprints
    clearance: float = 20.0  # m above the tallest roof
    tolerance: float = 1e-4
    max_iterations: int = 1000
    precision: str = "float32"
    monitor: bool = False  # bounded run recording probe histories (same iterates as legacy)
    checkpoint_interval: int = 25
    turbulence: bool = True
    max_cells: int = 20_000_000
    # wind.Parameterizations fields that differ from the defaults, as sorted (name, value) pairs;
    # a mapping is accepted and normalised.
    parameterizations: tuple = ()
    canopy_roughness: float | None = None  # m, z0 of the in-canopy log law (inflow "canopy")
    blending_height: float | None = None  # m, where the in-canopy law meets the approach profile
    ground_roughness: float | None = None  # m, replaces the profile's tail z0 (QES-Turb wall model, lower tail)

    def __post_init__(self):
        object.__setattr__(self, "parameterizations", parameterization_changes(dict(self.parameterizations)))
        if self.city not in CITIES or self.inflow not in INFLOWS:
            raise ValueError(f"city must be one of {CITIES} and inflow one of {INFLOWS}")
        canopy = (self.canopy_roughness, self.blending_height)
        if self.inflow == "canopy":
            if None in canopy or not 0 < self.canopy_roughness < self.blending_height:
                raise ValueError("The canopy inflow needs 0 < canopy_roughness < blending_height")
        elif canopy != (None, None):
            raise ValueError("canopy_roughness and blending_height require inflow='canopy'")
        if self.ground_roughness is not None and not (self.ground_roughness > 0 and self.inflow in ("measured", "canopy")):
            raise ValueError("ground_roughness must be positive and needs a measured or canopy inflow")

    def parameterization_spec(self) -> "wind.Parameterizations":
        return wind.Parameterizations(**dict(self.parameterizations))

    @property
    def probe_layer(self) -> float:
        return min(self.resolution, 4.0) if self.layer is None else self.layer

    def to_dict(self) -> dict:
        payload = dict(schema=SCHEMA, **asdict(self))
        for name, default in LATER_FIELDS.items():
            if payload[name] == default:
                del payload[name]
        if self.parameterizations:
            payload["parameterizations"] = dict(self.parameterizations)
        return payload

    @property
    def key(self) -> str:
        text = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @property
    def name(self) -> str:
        parts = [self.case, self.state if self.case == "E" else None, self.label.replace(" deg.", "deg"),
                 f"r{self.resolution:g}", self.inflow, self.precision,
                 f"it{self.max_iterations}", "mon" if self.monitor else None, None if self.turbulence else "noturb"]
        parts += [None if self.city == "exact" else self.city,
                  f"delta{self.min_detail:g}" if self.case == "E" and self.min_detail not in (None, 0.1) else None,
                  f"pad{self.padding:g}" if self.padding != 20.0 else None,
                  f"top{self.clearance:g}" if self.clearance != 20.0 else None,
                  None if self.vertical == "stretched" else self.vertical,
                  None if self.interpolation == "log_height" else self.interpolation,
                  None if self.ground_roughness is None else f"z0g{self.ground_roughness:g}"]
        if self.inflow == "canopy":
            parts.append(f"z0u{self.canopy_roughness:.3g}-zb{self.blending_height:.3g}")
        parts += [f"{name}{value:g}" for name, value in self.parameterizations]
        return "-".join(p for p in parts if p)

    @classmethod
    def from_dict(cls, payload: dict) -> "RunSpec":
        payload = dict(payload)
        if payload.pop("schema", None) != SCHEMA:
            raise ValueError(f"RunSpec schema must be {SCHEMA}")
        return cls(**payload)


def parameterization_changes(values: dict) -> tuple:
    """Validated wind.Parameterizations settings that differ from the defaults, sorted by name."""
    spec = wind.Parameterizations(**values).to_dict()
    default = wind.Parameterizations().to_dict()
    return tuple(sorted((name, value) for name, value in spec.items() if value != default[name]))
