#pragma once
#include "diagnostic_types.h"
#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace dtcc_qes {
// S3 native value types. Python/controller exposure is a separate S4 step.
enum class MonitorFrame { Local, World };
struct MonitorLocation { double x = 0, y = 0, height_agl = 0; };
struct MonitorRectangle { double x_first = 0, x_last = 0, y_first = 0, y_last = 0; };
struct MonitorReceptor {
  std::string id;
  MonitorLocation location;
  bool required = true;
};
struct MonitorCellRegion {
  std::string name;
  int i_first = 1, i_last = -1, j_first = 1, j_last = -1, k_first = 0, k_last = -1;
};
struct MonitorSpec {
  MonitorRectangle region; // Explicit half-open rectangle of native x/y centres.
  std::vector<double> heights{1.5,1.75}; // Metres AGL, never rounded to float32.
  std::vector<MonitorReceptor> receptors;
  MonitorFrame frame = MonitorFrame::Local; // Applies to x/y; heights remain AGL.
  std::array<double,3> origin{0,0,0};
  std::string crs;
  double reference_speed = 5;
  std::size_t short_window = 1, long_window = 2, history_limit = 64;
  std::size_t memory_limit_bytes = 64*1024*1024;
  bool global_mass = false;
  std::vector<MonitorCellRegion> mass_regions; // Additional physical index boxes.
  // Absent means relative mass imbalance is unassessed. Any supplied value is
  // experimental; S3 has no calibrated acceptance threshold or acceptance state.
  std::optional<double> low_flow_fraction;
};
struct MonitorSample {
  std::array<double,3> velocity{};
  bool valid = false;
};
struct MonitorPeak {
  bool valid = false;
  std::size_t point = 0;
  MonitorLocation location;
  double speed = 0;
  std::optional<double> speed_factor;
};
struct MonitorNorm { std::optional<double> p95, maximum; };
struct MonitorRatios {
  std::optional<double> vector_p95, vector_max, speed_p95, speed_max;
};
struct MonitorHotspot {
  bool present = false;
  std::size_t point = 0;
  MonitorLocation location;
  MonitorSample before, current;
  std::optional<double> vector_change, speed_change;
};
struct MonitorWindow {
  bool available = false;
  int from_iteration = 0, to_iteration = 0;
  std::size_t common_valid = 0, validity_changes = 0;
  MonitorNorm vector_change, speed_change; // m/s; equal-weight linear p95.
  MonitorNorm vector_over_uref, speed_factor_change; // Unavailable for Uref=0.
  MonitorRatios ratios; // Only stable support and equal sweep intervals.
  std::array<MonitorHotspot,2> hotspots; // Current and preceding window peaks.
};
struct MonitorHeightRecord {
  double height_agl = 0;
  std::size_t points = 0, valid = 0;
  MonitorPeak peak;
  MonitorWindow short_change, long_change;
};
struct MonitorReceptorRecord {
  std::size_t receptor = 0;
  bool required = true;
  MonitorLocation location;
  MonitorSample sample;
  std::optional<double> speed, speed_factor;
  MonitorWindow short_change, long_change;
};
struct MonitorFlux {
  double net_cell_flux = 0, boundary_flux = 0, absolute_cell_flux = 0, throughflow = 0;
  std::size_t low_flow_cells = 0, resolved_cells = 0, unassessed_cells = 0;
  std::optional<double> relative_max, relative_rms;
};
struct MonitorMassRecord {
  std::size_t region = 0;
  DivergenceStats divergence;
  MonitorFlux interior, top_band;
};
struct MonitorResidualTrend {
  int iteration = 0;
  double maximum = 0, volume_weighted_rms = 0;
  std::size_t fluid_cells = 0;
  // Algebraic/native RHS units on a partly updated sweep; no s^-1 conversion.
};
struct MonitorCheckpoint {
  int iteration = 0;
  bool initial = false, required_receptors_valid = true;
  double elapsed_seconds = 0;
  std::vector<MonitorHeightRecord> heights;
  std::vector<MonitorReceptorRecord> receptors;
  std::vector<MonitorMassRecord> mass;
  std::optional<MonitorResidualTrend> residual_trend;
};
}
