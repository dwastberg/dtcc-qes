#pragma once
#include <optional>
#include <string>
#include <cstddef>
namespace dtcc_qes {
// Versioned empirical numerical assessment of two pedestrian planes/receptors.
// These values do not qualify the full volume, turbulence or physical models.
inline constexpr const char *pedestrian_policy_id = "pedestrian-v1";
inline constexpr const char *pedestrian_method_id = "s5c-rb-sor-float-omega-v1-omega-1.90";
inline constexpr double policy_safety_factor = 8;
inline constexpr int policy_minimum_iterations = 150;
inline constexpr double policy_maximum_ratio = .8;
inline constexpr double policy_vector_p95 = 5e-4, policy_vector_maximum = 1e-3;
inline constexpr double policy_mass_length = 23.7;
inline constexpr double policy_mass_maximum = 1e-3, policy_mass_rms = 1e-4;
inline constexpr double policy_residual_maximum = 1e-3, policy_residual_rms = 1e-4;
struct PolicyPrediction {
  bool available = false;
  std::string reason = "warming_up";
  std::string current_tail_reason = "warming_up";
  bool fresh_tail_available = false;
  std::optional<int> anchor_iteration;
  std::optional<double> vector_p95, vector_maximum, speed_p95, speed_maximum;
  std::optional<double> required_maximum, hotspot_maximum, q_minimum, q_maximum;
};
struct PolicyEvidence {
  int iteration = 0, consecutive = 0;
  bool safeguards_passed = false, candidate = false, ready = false, accepted = false;
  PolicyPrediction prediction;
  std::optional<double> relative_residual_maximum, relative_residual_rms;
  std::optional<double> scaled_mass_maximum, scaled_mass_rms;
  std::size_t residual_cells = 0, mass_regions = 0;
};
}
