"""Settings for the QES-Winds empirical building parameterizations."""

from dataclasses import asdict, dataclass

from ._validation import integer, real, versioned_mapping

# Highest supported code per model; the native bridge enforces the same ranges
# (model_inputs.cpp). Field names map to the native ``<name>_flag`` settings.
_FLAG_MAXIMA = dict(rooftop=2, upwind_cavity=3, street_canyon=1, wake=2, high_rise=1, sidewall=1)


@dataclass(frozen=True)
class Parameterizations:
    """Empirical building models that shape the initial QES-Winds field.

    Codes follow QES: ``rooftop`` 0 none, 1 log profile, 2 vortex;
    ``upwind_cavity`` 0 none, 1 Röckle, 2 MVP, 3 HMVP; ``street_canyon`` 0 none,
    1 Röckle with Fackrell; ``wake`` 0 none, 1 Röckle, 2 modified Röckle;
    ``high_rise`` and ``sidewall`` 0 off, 1 on. ``wall_roughness`` is the wall
    roughness length in metres. Rooftop, street-canyon and sidewall models use
    the wake geometry, so they require ``wake > 0``.

    The defaults are the QES-Winds defaults used by every run before this
    setting existed, and the only values ``pedestrian-v1`` qualifies: any other
    value makes an adaptive run ``unqualified_model_settings``. QES's street
    intersection model is not implemented, so it is not offered.
    """

    rooftop: int = 1
    upwind_cavity: int = 2
    street_canyon: int = 1
    wake: int = 2
    high_rise: int = 0
    sidewall: int = 1
    wall_roughness: float = 0.001

    def __post_init__(self):
        for name, maximum in _FLAG_MAXIMA.items():
            object.__setattr__(self, name, integer(getattr(self, name), name, minimum=0, maximum=maximum))
        object.__setattr__(self, "wall_roughness",
                           real(self.wall_roughness, "wall_roughness", positive=True, float32=True))
        if self.wake == 0 and (self.rooftop or self.street_canyon or self.sidewall):
            raise ValueError("wake must be nonzero when rooftop, street_canyon or sidewall is enabled")

    def to_dict(self):
        return dict(schema_version=1, **asdict(self))

    @classmethod
    def from_dict(cls, payload):
        args = versioned_mapping(payload, "parameterizations")
        try:
            return cls(**args)
        except TypeError as error:
            raise ValueError(f"Invalid parameterizations fields: {error}") from error

    def _apply(self, model):
        """Write these settings into a prepared native ModelSettings."""
        for name in _FLAG_MAXIMA:
            setattr(model, f"{name}_flag", getattr(self, name))
        model.wall_roughness = self.wall_roughness

    @classmethod
    def _from_model(cls, model):
        """The settings a native ModelSettings carries."""
        return cls(**{name: getattr(model, f"{name}_flag") for name in _FLAG_MAXIMA},
                   wall_roughness=model.wall_roughness)
