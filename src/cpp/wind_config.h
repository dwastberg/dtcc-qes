#pragma once

#include <cstdint>
#include <cstddef>
#include <vector>

namespace dtcc_qes {
// Private numerical contract. Coordinates are metres in a local, flat frame.
// These types deliberately contain no QES or Python objects.
struct GridConfig {
  int nx = 40, ny = 30, nz = 20;
  double cell_size = 2.0;
  std::int64_t max_cells = 2000000;
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
};

struct SolverOptions {
  double tolerance = 1e-5;
  int max_iterations = 500;
};

struct BuildingArrays {
  // Flattened float64 (N, 2) vertices; each ring is closed and clockwise.
  std::vector<double> vertices;
  std::vector<std::int64_t> offsets, ids;
  std::vector<double> heights, base_heights;
};

struct WindData {
  int nx = 0, ny = 0, nz = 0;
  std::vector<float> x, y, z, velocity;
  std::vector<std::int32_t> cell_flags;
  int iterations = 0;
  float max_lagrange_multiplier_change = 0, tolerance = 0;
  bool converged = false;
  std::size_t building_count = 0;
};
}
