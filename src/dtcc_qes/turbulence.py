"""Qualified QES mixing-length choices for optional turbulence output."""

from dataclasses import dataclass
from copy import deepcopy
from typing import Literal

import numpy as np

from ._validation import versioned_mapping
from ._statistics import _STRESS_RELATIVE_TOLERANCE, _velocity_magnitude

NUMERICS_VERSION = "dtcc-qes-turbulence-v3"


@dataclass(frozen=True)
class Turbulence:
    """Algebraic turbulence model; height is the provisional default.

    Both methods passed native safety/correctness checks. See the numerical
    benchmark report for measured costs and sensitivity. Pedestrian-gust
    validation against observations remains outstanding.
    """
    mixing_length: Literal["height", "wall_distance"] = "height"

    def __post_init__(self):
        if not isinstance(self.mixing_length, str) or self.mixing_length not in ("height", "wall_distance"):
            raise ValueError("mixing_length must be 'height' or 'wall_distance'")

    @property
    def qes_method(self):
        """Native methods qualified by the rotation and wall-distance repairs."""
        return 0 if self.mixing_length == "height" else 1

    def to_dict(self):
        return dict(schema_version=1, mixing_length=self.mixing_length)

    @classmethod
    def from_dict(cls, payload):
        args = versioned_mapping(payload, "turbulence")
        try:
            return cls(**args)
        except TypeError as error:
            raise ValueError(f"Invalid turbulence fields: {error}") from error


def _resolve_turbulence(value):
    if value is None or isinstance(value, Turbulence):
        return value
    raise ValueError("turbulence must be a Turbulence specification or None; boolean shorthand was removed")


def _turbulence_metadata(spec, native, domain_top, velocity, has_buildings):
    """Snapshot solve diagnostics; mutable result arrays never rewrite counts."""
    upper,friction = np.float32(native["upper_bound"]),np.float32(native["friction_velocity"])
    bound = float(upper*friction*friction)  # Match QES's float32 operation order.
    computed = native["state"] > 0
    fixes = ["orthogonal_stress_rotation", "nearest_fluid_column_direction_fallback",
             "declared_height_vector_reference", "float64_reference_mean",
             "spectral_radius_stress_bound", "recorded_limiter_activity",
             "shifted_log_ground_derivatives"]
    if spec.qes_method == 1:
        fixes += ["bounded_exposed_voxel_face_distances", "minimum_distance_preservation",
                  "physical_3H_to_3.6H_transition"]
    return dict(model="QES-Turb algebraic mixing-length model",mixing_length=spec.mixing_length,caveats=[],
        qes_method=spec.qes_method,numerics_version=NUMERICS_VERSION,audited_fixes=fixes,
        upstream_parity="Audited embedded physics; rotation, wall distances, spectral bound and ground derivatives differ from pristine QES",
        stress_components=("txx","txy","txz","tyy","tyz","tzz"),
        units=dict(stress="m^2/s^2",tke="m^2/s^2",co_eps="m^2/s^3",mixing_length="m"),
        tke_definition="QES kinetic energy before stress anisotropy scaling",
        constants=dict(von_karman=.4,c_pope=.55,sigma_over_ustar=(2.5,2.,1.3),c0=5.7,
            upper_bound=native["upper_bound"],building_wall_flag=2,terrain_wall_flag=2,
            non_local_mixing=False,background_mixing=0.,rotation_reference_height=15.),
        reference=dict(height=native["reference_height"],speed=native["reference_speed"],
            friction_velocity=native["friction_velocity"],roughness_length=native["roughness_length"],
            displacement_height=native["displacement_height"],
            sampling=dict(method="cell_centre_vector_linear", accumulation="float64", scalar_export="float32",
                support_policy="all positive-weight source cells fluid; nonfinite fluid velocities and empty support rejected",
                **native["reference_sampling"]),
            basis="3 × mean building height" if has_buildings else "100 × roughness_length"),
        cap=dict(value=bound,computed_cells=native["computed_cells"],capped_cells=native["capped_cells"],
            spectral_limited_cells=native["spectral_limited_cells"],
            energy_capped_cells=native["energy_capped_cells"],
            policy="Stress tensor scaled to spectral radius B, or TKE cap fired; zero bound in calm flow is uncapped"),
        validity=dict(policy="raw_and_mask",relative_tolerance=_STRESS_RELATIVE_TOLERANCE,
            tolerance_definition="lambda_min >= -32 * float32_epsilon * max(abs(eigenvalues)); finite zero is valid",
            invalid_stress_cells=native["invalid_stress_cells"],
            zero_speed_cells=int(np.count_nonzero(computed & (_velocity_magnitude(velocity) == 0))),
            counts_basis="original computed cells; covariance validity is independent of capping",
            rotation_direction_fallback_policy="Nearest physical fluid centre with finite nonzero horizontal wind; higher tie wins; Cartesian +x if none",
            rotation_fallback_columns=native["rotation_fallback_columns"]),
        domain_top=deepcopy(domain_top),
        speed_scaling=dict(stress_and_tke="speed squared",co_eps="speed cubed",streamwise_std="speed",
            turbulence_intensity="speed invariant",mixing_length="geometry only",
            qualification="fixed grid and zero background mixing; finite precision and solver tolerance affect comparisons"),
        limitations=["Algebraic mixing-length screening model; not validated for pedestrian gusts",
            "Height remains a provisional default; numerical acceptance does not validate pedestrian gusts",
            "Raw stress can be indefinite; derived statistics are masked without changing raw tensors",
            "Morphometric friction velocity differs from the inflow log profile and sets the cap",
            "Grid choice and automatic domain growth can change the solved wind"])
