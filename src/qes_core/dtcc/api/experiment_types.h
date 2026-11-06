#pragma once
// Private canyon validation settings. Never part of production qualification.
#include "canyon_types.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace dtcc_qes {
struct ExperimentOptions {
  CanyonModel canyon_model=CanyonModel::Legacy;
  bool canyon_capture=false;
  bool canyon_trace_roof=false; // Private face-level investigation, no field writes.
  // Explicit AIJ validation allowance: unchanged, one-way default QES-Turb.
  bool canyon_baseline_turbulence=false;
#ifdef DTCC_QES_CANYON_TEST_HOOKS
  bool test_canyon_failure=false;
#endif
  float omega = 1.78f;
  bool export_projection = false;
  bool diagnose_flux = false;
  std::size_t export_limit_bytes = 512ull * 1024 * 1024;
  // Zero-based physical cell indices (i,j,k), sampled without full snapshots.
  std::vector<std::array<int,3>> cells;
  std::vector<int> checkpoints;
  std::array<int,2> checkpoint_layers{0,1};
  std::vector<float> target_velocity;
  std::vector<double> target_mass;
  double boundary_flux_area = 0, boundary_flux_tolerance = 1e-4;
  // Compatibility inputs are accepted only at their defaults; no model is implemented.
  std::vector<float> canopy_factors, canopy_occupied;
  std::array<int,3> canopy_shape{0,0,0};
  std::array<double,2> canopy_origin{0,0}; // native local frame, lattice nodes
  double canopy_pitch = 20, canopy_taper = 10;
  int building_order = 0; // private: default, reverse, cycle equal-height IDs
  bool export_mixing_length = false;
  bool wake_attribution = false;
  int wake_composition = 0; // 0: legacy, 1: private SE1 support/exposure rule.
  std::size_t wake_event_limit = 100000;
};
struct ExperimentData {
  CanyonModel canyon_model=CanyonModel::Legacy;
  std::vector<std::string> canyon_fallback_reasons;
  std::vector<std::size_t> canyon_fallback_counts;
  std::vector<float> canyon_initial_w;
  std::vector<double> canyon_roof_trace; // Rows of 13 values; schema in bindings.
  std::size_t canyon_voxel_roof_changes=0;
  std::size_t canyon_core_u=0,canyon_core_v=0,canyon_core_w=0,canyon_roof_skipped=0;
  std::size_t canyon_changed_faces=0,canyon_roof_changes=0,canyon_audit_zones=0,canyon_W_changes=0;
  std::size_t canyon_qualified=0,canyon_fallback=0,canyon_writes=0;

  std::vector<std::string> stages;
  std::vector<float> stage_velocity;
  std::vector<std::int32_t> stage_flags;
  std::size_t sample_count = 0;
  int actual_threads = 1;
  std::vector<double> mass;
};
}
