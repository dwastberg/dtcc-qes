#pragma once

#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include <optional>
#include "control_types.h"
#include "profile_types.h"

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
};

struct BuildingArrays {
  // Flattened float64 (N, 2) vertices; each ring is closed and clockwise.
  std::vector<double> vertices;
  std::vector<std::int64_t> offsets, ids;
  std::vector<double> heights, base_heights;
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
  float friction_velocity = 0, reference_speed = 0, reference_height = 0;
  float roughness_length = 0, displacement_height = 0, upper_bound = 0;
  std::size_t computed_cells = 0, capped_cells = 0, invalid_stress_cells = 0;
  std::size_t rotation_fallback_columns = 0;
};

struct WindData {
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
};
}
