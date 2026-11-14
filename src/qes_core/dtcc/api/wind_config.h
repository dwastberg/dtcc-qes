#pragma once
#include "reference_sampling.h"

#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include <optional>
#include "control_types.h"
#include "profile_types.h"
#include "canyon_validation_types.h"
#include "read_only_trace_types.h"

namespace dtcc_qes {
// Private numerical contract. Coordinates are metres in a local, flat frame.
// These types deliberately contain no QES or Python objects.
struct GridConfig {
  int nx = 40, ny = 30, nz = 20;
  double cell_size = 2.0;
  std::int64_t max_cells = 2000000;
  std::vector<double> dz_layers; // Physical thicknesses; empty preserves uniform cells.
};

struct ModelSettings {
  double roughness_length = 0.1;
  double sensor_x = 11.0, sensor_y = 31.0;
  bool exposed_faces = false;
  double wall_roughness = 0.001;
  int rooftop_flag = 1, upwind_cavity_flag = 2, street_canyon_flag = 1;
  int street_intersection_flag = 0, wake_flag = 2, high_rise_flag = 0, sidewall_flag = 1;
};

struct WindCondition {
  double speed = 5.0, direction = 270.0, reference_height = 10.0;
  ProfileKind profile_kind = ProfileKind::Log;
  // Python evaluates all new profile families at physical cell centres. Owned
  // float64 boundary arrays are validated/narrowed atomically by ModelInputs.
  std::vector<double> layer_u, layer_v;
};

struct SolverOptions {
  double tolerance = 1e-5;
  int max_iterations = 500;
  std::string precision = "float32";
  // SOR relaxation for legacy and bounded solves. Zero keeps each mode's frozen
  // choice (1.78; 1.90 when adaptive); adaptive control rejects any other value.
  double relaxation = 0;
  // Legacy and bounded solves: resolve the relaxation from the domain with
  // grid_relaxation (policy_types.h). Requires relaxation == 0.
  bool grid_relaxation = false;
  // "multiplier_change" (the legacy tolerance), "velocity" (stop when the
  // remaining-velocity-error estimate is at most velocity_tolerance, a fraction
  // of the reference speed) or "fixed" (exactly max_iterations sweeps, with the
  // estimate recorded). Adaptive control accepts only "multiplier_change".
  std::string stop_rule = "multiplier_change";
  double velocity_tolerance = 1e-3;
};

// Remaining-velocity-error estimate of a "velocity" or "fixed" solve. Values
// are relative to reference_speed; non-finite entries mean "not yet available".
struct StopEstimateData {
  std::string rule, termination;
  double tolerance = 0, reference_speed = 0;
  double safety_factor = 0, contraction_limit = 0, floor_factor = 0;
  int interval = 0, checks = 0, first_counted_check = 0;
  bool history_truncated = false;
  std::vector<int> iterations;
  std::vector<double> change, contraction, estimate, floor;
};

struct BuildingArrays {
  // Flattened float64 (N, 2) vertices; each ring is closed and clockwise.
  std::vector<double> vertices;
  std::vector<std::int64_t> offsets, ids;
  std::vector<double> heights, base_heights;
  // Optional global vertex boundaries of closed rings; building offsets align.
  std::vector<std::int64_t> ring_offsets;
};

struct TurbulenceSettings {
  bool enabled = false;
  int mixing_length_method = 0; // 0: height; 1: qualified serial wall distance.
};

struct TurbulenceData {
  // Physical (z,y,x) cells, stress ordered xx,xy,xz,yy,yz,zz.
  // Uncomputed float entries are NaN. Raw computed values are never repaired.
  std::vector<float> stress, tke, co_eps, mixing_length;
  std::vector<std::uint8_t> state; // 0 uncomputed; 1 computed; 2 computed and capped.
  std::vector<std::uint8_t> stress_valid;
  ReferenceSampling reference_sampling;
  float friction_velocity = 0, reference_speed = 0, reference_height = 0;
  float roughness_length = 0, displacement_height = 0, upper_bound = 0;
  std::size_t computed_cells = 0, capped_cells = 0, invalid_stress_cells = 0;
  std::size_t spectral_limited_cells = 0, energy_capped_cells = 0;
  std::size_t rotation_fallback_columns = 0;

};

struct WakeFields {
  // Spreading wake (wake code 3), physical (z,y,x) cells like velocity.
  std::vector<float> deficit; // D, averaged from the four horizontal faces
  std::vector<float> tke;     // k_w = 0.08 max_b U_H,b^2 G_b (m^2/s^2), averaged from the two u faces
};

struct WindData {
  std::uint64_t operation_id = 0; // Binding transfer/progress correlation.
  int nx = 0, ny = 0, nz = 0;
  std::vector<float> x, y, z, z_faces, velocity;
  std::vector<std::int32_t> cell_flags;
  int iterations = 0;
  double max_lagrange_multiplier_change = 0, tolerance = 0;
  std::string precision = "float32";
  bool converged = false;
  DivergenceStats divergence;
  std::size_t building_count = 0;
  std::optional<TurbulenceData> turbulence;
  std::optional<ControlRecord> control;
  std::optional<CanyonData> experiment;
  std::optional<ReadOnlyTraceData> trace;
  std::optional<StopEstimateData> stop_estimate; // Only "velocity" and "fixed" solves.
  std::optional<double> relaxation; // The resolved factor; only grid_relaxation solves.
  ControlTimings timings; // Always measured, including legacy solves.
  std::optional<WakeFields> wake; // Wake code 3 only.
};
}
