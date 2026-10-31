"""Bounded execution and versioned, opt-in pedestrian numerical assessment."""
from dataclasses import asdict, dataclass
import math
from numbers import Integral, Real


def _number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return float(value)


def _integer(value, name, *, minimum=1):
    if isinstance(value, bool) or not isinstance(value, Integral) or not minimum <= value <= 2**31-1:
        raise ValueError(f"{name} must be an integer in [{minimum}, {2**31-1}]")
    return int(value)


@dataclass(frozen=True)
class Receptor:
    id: str
    x: float
    y: float
    height_agl: float
    required: bool = True

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Receptor ID must be a nonempty string")
        for name in ("x", "y"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v):
                raise ValueError(f"Receptor {name} must be finite")
            object.__setattr__(self, name, float(v))
        object.__setattr__(self, "height_agl", _number(self.height_agl, "height_agl"))
        if not isinstance(self.required, bool):
            raise ValueError("required must be boolean")


@dataclass(frozen=True)
class MassRegion:
    name: str
    i_first: int = 1
    i_last: int = -1
    j_first: int = 1
    j_last: int = -1
    k_first: int = 0
    k_last: int = -1

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Mass region requires a name")
        for name in ("i_first", "j_first", "k_first", "i_last", "j_last", "k_last"):
            object.__setattr__(self, name, _integer(getattr(self, name), name, minimum=-1 if name.endswith("last") else 0))


@dataclass(frozen=True)
class MonitorSpec:
    """Half-open ROI (xmin,xmax,ymin,ymax), native x/y centers, AGL heights.

    ``frame`` applies to x/y only. World origin/CRS come from the prepared city.
    Window spans count checkpoints; history stores summaries, never full fields.
    An explicit low_flow_fraction is experimental and supplies no accuracy claim.
    """
    region: tuple[float, float, float, float]
    heights: tuple[float, ...] = (1.5, 1.75)
    receptors: tuple[Receptor, ...] = ()
    frame: str = "local"
    short_window: int = 1
    long_window: int = 2
    history_limit: int = 64
    memory_limit_bytes: int = 64*1024*1024
    global_mass: bool = False
    mass_regions: tuple[MassRegion, ...] = ()
    low_flow_fraction: float | None = None

    def __post_init__(self):
        region = tuple(self.region)
        if len(region) != 4 or any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in region):
            raise ValueError("Monitor region requires four finite coordinates")
        region = tuple(map(float, region))
        if region[0] >= region[1] or region[2] >= region[3]:
            raise ValueError("Monitor region requires increasing x/y bounds")
        object.__setattr__(self, "region", region)
        heights = tuple(_number(v, "monitor height") for v in self.heights)
        if len(set(heights)) != len(heights):
            raise ValueError("Monitor heights must be unique")
        object.__setattr__(self, "heights", heights)
        for name, cls in (("receptors", Receptor), ("mass_regions", MassRegion)):
            values = tuple(getattr(self, name))
            if any(not isinstance(v, cls) for v in values):
                raise TypeError(f"{name} must contain {cls.__name__} objects")
            object.__setattr__(self, name, values)
        if not heights and not self.receptors:
            raise ValueError("Monitor requires heights or receptors")
        for values in ([r.id for r in self.receptors], [r.name for r in self.mass_regions]):
            if len(set(values)) != len(values):
                raise ValueError("Monitor IDs/names must be unique")
        if self.frame not in ("local", "world") or not isinstance(self.global_mass, bool):
            raise ValueError("Monitor frame must be local/world and global_mass boolean")
        for name in ("short_window", "long_window", "history_limit", "memory_limit_bytes"):
            object.__setattr__(self, name, _integer(getattr(self, name), name))
        if self.long_window <= self.short_window or self.history_limit < self.long_window+1:
            raise ValueError("Require short_window < long_window < history_limit")
        if self.low_flow_fraction is not None:
            object.__setattr__(self, "low_flow_fraction", _number(self.low_flow_fraction, "low_flow_fraction", positive=True))


@dataclass(frozen=True)
class SolverControl:
    """Native solve budget, including mutex wait, initialization and monitoring.

    Preparation and necessary output/turbulence follow separate timing scopes.
    A whole native phase can exceed the cooperative budget. Every sweep checks
    time; checkpoint_interval controls expensive observations independently.
    residual_interval=0 disables algebraic trend collection.

    mode='adaptive' selects the frozen pedestrian-v1 numerical policy. Its
    qualified scope is documented in docs/solver-control-s7.md. The policy
    fixes cadence 25 and effective windows 1/4, adds global safeguards, and
    requires history_limit >= 5. Unsupported configurations remain unaccepted.
    Public bounded/legacy calls retain relaxation 1.78; qualified adaptive
    calls use 1.90. Acceptance never qualifies the full volume or turbulence.
    """
    max_solve_seconds: float
    monitor: MonitorSpec
    checkpoint_interval: int = 25
    residual_interval: int = 0
    mode: str = "bounded"
    policy: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "max_solve_seconds", _number(self.max_solve_seconds, "max_solve_seconds", positive=True))
        if not isinstance(self.monitor, MonitorSpec):
            raise TypeError("monitor must be MonitorSpec")
        if self.mode not in ("bounded", "adaptive"):
            raise ValueError("Solver mode must be bounded or adaptive")
        if self.mode == "adaptive":
            if self.policy not in (None, "pedestrian-v1"):
                raise ValueError("Unknown adaptive policy; expected pedestrian-v1")
            object.__setattr__(self, "policy", "pedestrian-v1")
            if self.checkpoint_interval != 25 or self.monitor.history_limit < 5:
                raise ValueError("pedestrian-v1 requires cadence 25 and history_limit >= 5")
        elif self.policy is not None:
            raise ValueError("Bounded controls have no acceptance policy")
        for name in ("checkpoint_interval", "residual_interval"):
            object.__setattr__(self, name, _integer(getattr(self, name), name, minimum=0 if name.startswith("residual") else 1))

    def _native(self, origin, crs):
        value = asdict(self)
        value["monitor"]["origin"] = tuple(origin)
        value["monitor"]["crs"] = crs or ""
        # Native input containers are copied while holding the GIL.
        for name in ("receptors", "mass_regions"):
            value["monitor"][name] = list(value["monitor"][name])
        return value

    @classmethod
    def from_dict(cls, value):
        try:
            value = dict(value)
            monitor = dict(value.pop("monitor"))
            monitor["receptors"] = tuple(Receptor(**r) for r in monitor.get("receptors", ()))
            monitor["mass_regions"] = tuple(MassRegion(**r) for r in monitor.get("mass_regions", ()))
            return cls(monitor=MonitorSpec(**monitor), **value)
        except (KeyError, TypeError) as error:
            raise ValueError(f"Invalid solver control settings: {error}") from error


class BudgetExhaustedError(RuntimeError):
    """No whole sweep completed; ``record`` contains phase and timing evidence."""
    def __init__(self, record):
        self.record = record
        super().__init__(f"Wind solve budget exhausted before any complete sweep ({record['phase']})")


class NumericalFailureError(RuntimeError):
    """Adaptive numerical execution failed; no finite output is fabricated."""
    def __init__(self, record):
        self.record = record
        super().__init__(f"Wind numerical failure: {record['assessment_reason']}")


class UnacceptedResultError(RuntimeError):
    """An adaptive result did not qualify its explicitly requested output scope."""
    def __init__(self, diagnostics, control):
        self.diagnostics = diagnostics
        self.control = control
        super().__init__(f"Wind result unaccepted by {control['policy']}: "
                         f"{control['assessment_reason']} (termination: {control['termination_reason']})")
