"""Bounded execution and versioned, opt-in pedestrian numerical assessment."""
from dataclasses import asdict, dataclass
from typing import Literal
from ._validation import real as _number, integer as _integer, versioned_mapping


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
            object.__setattr__(self, name, _number(getattr(self,name),f"Receptor {name}"))
        object.__setattr__(self, "height_agl", _number(self.height_agl, "height_agl", nonnegative=True))
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
    turbulence: bool = False

    def __post_init__(self):
        region = tuple(self.region)
        if len(region) != 4:
            raise ValueError("Monitor region requires four finite coordinates")
        region = tuple(_number(v,"Monitor region coordinate") for v in region)
        if region[0] >= region[1] or region[2] >= region[3]:
            raise ValueError("Monitor region requires increasing x/y bounds")
        object.__setattr__(self, "region", region)
        heights = tuple(_number(v, "monitor height", nonnegative=True) for v in self.heights)
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
        if self.frame not in ("local", "world") or not isinstance(self.global_mass, bool) or not isinstance(self.turbulence, bool):
            raise ValueError("Monitor frame must be local/world and global_mass boolean")
        for name in ("short_window", "long_window", "history_limit", "memory_limit_bytes"):
            object.__setattr__(self, name, _integer(getattr(self, name), name))
        if self.long_window <= self.short_window or self.history_limit < self.long_window+1:
            raise ValueError("Require short_window < long_window < history_limit")
        if self.low_flow_fraction is not None:
            object.__setattr__(self, "low_flow_fraction", _number(self.low_flow_fraction, "low_flow_fraction", positive=True))


class _RuleDefault:
    """Marks a Solver setting left out, resolved from the stop rule and policy."""
    __slots__ = ()

    def __repr__(self):
        return "<rule default>"


_RULE_DEFAULT = _RuleDefault()


class _ResolvedStr(str):
    """A rule setting filled in by default: a plain string, re-resolved by dataclasses.replace."""
    __slots__ = ()


class _ResolvedInt(int):
    """A sweep cap filled in by default: a plain integer, re-resolved by dataclasses.replace."""
    __slots__ = ()


def _left_out(value):
    return value is _RULE_DEFAULT or isinstance(value, (_ResolvedStr, _ResolvedInt))


@dataclass(frozen=True)
class Solver:
    """Immutable solver work, arithmetic and optional assessment specification.

    A budget and monitor together select bounded execution. Adding pedestrian-v1
    requests adaptive numerical assessment on its frozen scope. The cooperative
    budget covers the native solve, including mutex wait and monitoring; city
    preparation and output/turbulence calculation have separate timing scopes.

    Legacy and bounded solves stop by default when the estimated remaining
    face-velocity error is at most ``velocity_tolerance`` (1e-3) times the
    reference speed, with a grid-dependent SOR factor and a cap of 20,000 sweeps
    (SOLVER_STOP_RULE.md, stage 2). ``stop`` chooses the rule: ``"velocity"``
    (the default), ``"multiplier_change"`` (the former default: ``tolerance`` on
    the Lagrange multiplier change) or ``"fixed"`` (exactly ``max_iterations``
    sweeps, recording the estimate). ``relaxation`` is a number, None (1.78) or
    ``"grid"``: 2 - 16/N for N cells across the shorter horizontal side of the
    domain, clipped to [1.78, 1.98]; the value used is
    ``result.solver["relaxation"]``. ``max_iterations`` caps every rule.
    The velocity rule also stops at the arithmetic floor, including eight checks
    without a new minimum change while all eight remain within twice the floor.
    This reports ``precision_floor`` with ``floor_trigger="stagnation"``; the
    raw error estimate is retained even when it exceeds the requested tolerance.

    Settings left out depend on the rule: ``"velocity"`` uses ``"grid"`` and
    20,000 sweeps; the other rules and the pedestrian-v1 policy use 1.78 and
    1,000 sweeps, so ``Solver(stop="multiplier_change")`` is the former default
    exactly. The policy fixes its own factor and sweeps and rejects other rules
    and factors. A calm condition has no velocity scale: a ``"velocity"`` solve
    of one ends on the multiplier rule (``result.solver["calm_stop"]``).
    ``to_dict`` omits the rule options at their former defaults, and
    ``from_dict`` reads missing ones as those, so stored specs keep their meaning.
    """
    tolerance: float = 1e-4
    max_iterations: int = _RULE_DEFAULT
    precision: Literal["float32", "float64"] = "float32"
    max_solve_seconds: float | None = None
    monitor: MonitorSpec | None = None
    policy: Literal["pedestrian-v1"] | None = None
    checkpoint_interval: int = 25
    residual_interval: int = 0
    raise_on_failure: bool = False
    relaxation: float | Literal["grid"] | None = _RULE_DEFAULT
    stop: Literal["multiplier_change", "velocity", "fixed"] = _RULE_DEFAULT
    velocity_tolerance: float = 1e-3

    # The rule options before stage 2. to_dict omits them at these values, from_dict
    # fills them in when missing, and the policy accepts only these.
    _OPTIONAL_DEFAULTS = dict(relaxation=None, stop="multiplier_change", velocity_tolerance=1e-3)

    def _resolve_rule_defaults(self):
        """Fill the settings left out: the velocity rule outside the policy (D4, D6, D7).

        Filled values are marked, so that ``dataclasses.replace`` (which passes
        every current value back) resolves them again for the new settings, e.g.
        when a policy is added. A left-out relaxation resolved to None is not
        marked; None is also the policy's only accepted value.
        """
        if _left_out(self.stop):
            object.__setattr__(self, "stop", _ResolvedStr("multiplier_change" if self.policy is not None
                                                          else "velocity"))
        velocity = self.stop == "velocity"
        if _left_out(self.relaxation):
            object.__setattr__(self, "relaxation", _ResolvedStr("grid") if velocity else None)
        if _left_out(self.max_iterations):
            object.__setattr__(self, "max_iterations", _ResolvedInt(20000 if velocity else 1000))

    def __post_init__(self):
        import numpy as np
        self._resolve_rule_defaults()
        if not isinstance(self.precision, str) or self.precision not in ("float32", "float64"):
            raise ValueError("precision must be 'float32' or 'float64'")
        if self.relaxation is not None and not (isinstance(self.relaxation, str) and self.relaxation == "grid"):
            if isinstance(self.relaxation, str):
                raise ValueError("relaxation must be a number, 'grid' or None")
            relaxation = _number(self.relaxation, "relaxation", positive=True)
            if not relaxation < 2 or not 0 < np.float32(relaxation) < 2:
                raise ValueError("relaxation must be between zero and two")
            object.__setattr__(self, "relaxation", relaxation)
        if not isinstance(self.stop, str) or self.stop not in ("multiplier_change", "velocity", "fixed"):
            raise ValueError("stop must be 'multiplier_change', 'velocity' or 'fixed'")
        object.__setattr__(self, "velocity_tolerance",
                           _number(self.velocity_tolerance, "velocity_tolerance", positive=True))
        if self.policy is not None:
            changed = [name for name, default in self._OPTIONAL_DEFAULTS.items() if getattr(self, name) != default]
            if changed:
                raise ValueError(f"{', '.join(changed)} is fixed by the pedestrian-v1 policy; omit it")
        tolerance = _number(self.tolerance, "tolerance", positive=True)
        limits = np.finfo(self.precision)
        if not float(limits.eps) <= tolerance <= float(limits.max):
            raise ValueError(f"tolerance must be at least {self.precision} epsilon and finite in {self.precision}")
        object.__setattr__(self, "tolerance", tolerance)
        iterations = _integer(self.max_iterations, "max_iterations")
        object.__setattr__(self, "max_iterations", _ResolvedInt(iterations)
                           if isinstance(self.max_iterations, _ResolvedInt) else iterations)
        if not isinstance(self.raise_on_failure, bool):
            raise ValueError("raise_on_failure must be boolean")
        if self.policy is not None and (not isinstance(self.policy, str) or self.policy != "pedestrian-v1"):
            raise ValueError("Unknown policy; expected pedestrian-v1 or None")
        for name in ("checkpoint_interval", "residual_interval"):
            object.__setattr__(self, name, _integer(getattr(self, name), name,
                minimum=0 if name == "residual_interval" else 1))
        if self.max_solve_seconds is None and self.monitor is None and self.policy is None:
            if self.checkpoint_interval != 25 or self.residual_interval != 0:
                raise ValueError("Legacy solver requires checkpoint_interval=25 and residual_interval=0")
            return
        if self.max_solve_seconds is None or self.monitor is None:
            raise ValueError("Bounded/adaptive solver requires both max_solve_seconds and monitor")
        object.__setattr__(self, "max_solve_seconds",
                           _number(self.max_solve_seconds, "max_solve_seconds", positive=True))
        if not isinstance(self.monitor, MonitorSpec):
            raise TypeError("monitor must be MonitorSpec")
        if self.policy is not None and (self.checkpoint_interval != 25 or self.monitor.history_limit < 5):
            raise ValueError("pedestrian-v1 requires cadence 25 and history_limit >= 5")

    @property
    def mode(self):
        if self.max_solve_seconds is None:
            return "legacy"
        return "adaptive" if self.policy is not None else "bounded"

    def to_dict(self):
        import json
        fields = asdict(self)
        for name, default in self._OPTIONAL_DEFAULTS.items():
            if fields[name] == default:
                del fields[name]
        return json.loads(json.dumps(dict(schema_version=1, **fields), allow_nan=False))

    @classmethod
    def from_dict(cls, payload):
        value = versioned_mapping(payload, "solver")
        try:
            if value.get("monitor") is not None:
                monitor = dict(value.pop("monitor"))
                monitor["receptors"] = tuple(Receptor(**r) for r in monitor.get("receptors", ()))
                monitor["mass_regions"] = tuple(MassRegion(**r) for r in monitor.get("mass_regions", ()))
                value["monitor"] = MonitorSpec(**monitor)
            for name, legacy in cls._OPTIONAL_DEFAULTS.items():
                value.setdefault(name, legacy)  # payloads written before stage 2
            return cls(**value)
        except (KeyError, TypeError) as error:
            raise ValueError(f"Invalid solver settings: {error}") from error

    def _native(self, origin, crs):
        if self.mode == "legacy":
            raise ValueError("Legacy solver has no native control record")
        monitor = asdict(self.monitor)
        monitor.update(origin=tuple(origin), crs=crs or "")
        for name in ("receptors", "mass_regions"):
            monitor[name] = list(monitor[name])
        return dict(mode=self.mode, policy=self.policy, max_solve_seconds=self.max_solve_seconds,
                    checkpoint_interval=self.checkpoint_interval, residual_interval=self.residual_interval,
                    monitor=monitor)


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
    def __init__(self, diagnostics, record, *, exclusions=()):
        self.diagnostics = diagnostics
        self.record = record
        self.exclusions = tuple(exclusions)
        if record is None:
            message = ("Wind result excluded from pedestrian-v1 before preparation: "
                       + ", ".join(self.exclusions) + "; remaining checks run during the solve")
        else:
            message = (f"Wind result unaccepted by {record['policy']}: "
                       f"{record['assessment_reason']} (termination: {record['termination_reason']})")
        super().__init__(message)
