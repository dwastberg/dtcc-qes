#pragma once
#include "monitor_types.h"
#include <stdexcept>
#include <utility>

namespace dtcc_qes {
struct SolverControl {
  std::string mode = "bounded";
  double max_solve_seconds = 0;
  int checkpoint_interval = 25;
  int residual_interval = 0; // Zero disables; otherwise collect on these sweeps.
  MonitorSpec monitor;
};
struct ControlRegion {
  std::string name;
  std::array<int,6> bounds{};
  std::size_t excluded_lateral_cells = 0, excluded_highest_cells = 0;
};
struct ControlTimings {
  double preparation_seconds = 0, mutex_wait_seconds = 0, initialization_seconds = 0;
  double workspace_seconds = 0, rhs_seconds = 0, sweeps_seconds = 0, monitoring_seconds = 0;
  double finalization_seconds = 0, postprocessing_seconds = 0, output_transfer_seconds = 0;
  double solve_seconds = 0, native_total_seconds = 0, deadline_overshoot_seconds = 0;
};
struct ControlRecord {
  std::string mode = "bounded", termination_reason, accuracy_status = "not_assessed", phase;
  SolverControl requested;
  MonitorSpec effective_monitor;
  ControlTimings timings;
  int iterations = 0, actual_threads = 1;
  bool legacy_tolerance_satisfied = false, history_truncated = false;
  std::size_t checkpoint_count = 0, monitor_bytes = 0;
  std::vector<ControlRegion> regions;
  std::vector<MonitorCheckpoint> checkpoint_history;
};
class BudgetExhausted : public std::runtime_error {
public:
  ControlRecord record;
  explicit BudgetExhausted(ControlRecord value)
    : std::runtime_error("Native solve budget exhausted before any complete sweep"), record(std::move(value)) {}
};
}
