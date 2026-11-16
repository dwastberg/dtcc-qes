"""Settings for the QES-Winds empirical building parameterizations."""

from dataclasses import asdict, dataclass

from ._validation import integer, real, versioned_mapping

# Highest supported code per model; the native bridge enforces the same ranges
# (model_inputs.cpp). Field names map to the native ``<name>_flag`` settings.
_FLAG_MAXIMA = dict(rooftop=2, upwind_cavity=3, street_canyon=1, wake=3, high_rise=1, sidewall=1, tall_buildings=1)


@dataclass(frozen=True)
class Parameterizations:
    """Empirical building models that shape the initial QES-Winds field.

    Codes follow QES: ``rooftop`` 0 none, 1 log profile, 2 vortex;
    ``upwind_cavity`` 0 none, 1 Röckle, 2 MVP, 3 HMVP; ``street_canyon`` 0 none,
    1 Röckle with Fackrell; ``wake`` 0 none, 1 Röckle, 2 modified Röckle,
    3 modified Röckle cavity with a spreading far wake and wake turbulence
    (experimental; see below); ``high_rise`` and ``sidewall`` 0 off, 1 on. ``wall_roughness`` is the wall
    roughness length in metres. Rooftop, street-canyon and sidewall models use
    the wake geometry, so they require ``wake > 0``.

    The defaults are the QES-Winds defaults used by every run before this
    setting existed, and the only values ``pedestrian-v1`` qualifies: any other
    value makes an adaptive run ``unqualified_model_settings``. QES's street
    intersection model is not implemented, so it is not offered.

    ``wake=3`` keeps the code-2 cavity but replaces its far wake: each
    building's shadow, widened by its separation bubble, spreads across the
    wind and in height (width 0.2 x behind the building), shelters the
    buildings behind it, and adds a wake turbulence 0.08 U_H² G. The result
    then carries ``result.wake`` (deficit and turbulence) and
    ``result.scalar_speed()``. It sets no far-wake cell flag (5).

    ``angle_fade`` (degrees, experimental) replaces the on/off test of the sidewall
    zone and the upwind cavity. QES applies both to a wall only within 10 degrees
    of its aligned direction, so a whole zone appears between two wind
    directions. With a half-width h the zone has full strength up to 10 - h
    degrees and fades to nothing at 10 + h. ``0`` keeps the switch; ``2.5`` is
    the validated value (``validation/ACCURACY_RESULTS.md``). Cell flags keep the
    switch.

    ``tall_buildings=1`` (experimental, needs ``wake=3``) adds two things that
    belong together. Far-wake deficits combine by the root sum of squares
    instead of the largest, so that weak wakes that overlap add up in a dense
    fabric. And a building much taller than its neighbours gets a zone of
    faster air near the ground beside it and reversed flow in front of it,
    from published speed ratios; part of that rise is carried as turbulence
    in ``result.wake.tke``. It is a model of the scalar speed
    (``result.scalar_speed()``): the direction of the mean flow near a tall
    building is not reliable. Heights must be full-scale metres. See
    ``docs/tall-buildings.md``.
    """

    rooftop: int = 1
    upwind_cavity: int = 2
    street_canyon: int = 1
    wake: int = 2
    high_rise: int = 0
    sidewall: int = 1
    wall_roughness: float = 0.001
    angle_fade: float = 0.0
    tall_buildings: int = 0

    def __post_init__(self):
        for name, maximum in _FLAG_MAXIMA.items():
            object.__setattr__(self, name, integer(getattr(self, name), name, minimum=0, maximum=maximum))
        object.__setattr__(self, "wall_roughness",
                           real(self.wall_roughness, "wall_roughness", positive=True, float32=True))
        fade = real(self.angle_fade, "angle_fade", nonnegative=True)
        if fade > 10.0:
            raise ValueError("angle_fade must be at most 10 degrees")
        object.__setattr__(self, "angle_fade", fade)
        if self.tall_buildings and self.wake != 3:
            raise ValueError("tall_buildings requires wake=3")
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
        model.angle_fade = self.angle_fade

    @classmethod
    def _from_model(cls, model):
        """The settings a native ModelSettings carries."""
        return cls(**{name: getattr(model, f"{name}_flag") for name in _FLAG_MAXIMA},
                   wall_roughness=model.wall_roughness, angle_fade=model.angle_fade)
