#pragma once
#include "api/control_types.h"
#include "monitor.h"
#include <algorithm>
#include <functional>
#include <memory>

namespace dtcc_qes {
// Native-only test clock. Python callbacks are never accepted or invoked.
using MonotonicClock = std::function<double()>;
class SolverController {
public:
  explicit SolverController(const SolverControl &,MonotonicClock = {});
  ControlRecord record;
  double now() const;
  double elapsed() const {return now()-started_;}
  bool check(const char *phase,int completed = 0);
  void finish_output();
  template<class Real> void run(solver::SolverState<Real> &state) {
    if (!check("before_monitor_compile")) return;
    auto started = now();
    monitor_ = std::make_unique<Monitor>(state,record.effective_monitor);
    record.monitor_bytes = monitor_->allocated_bytes();
    for (const auto &r : monitor_->regions())
      record.regions.push_back({r.name,{r.bounds.i_first,r.bounds.i_last,r.bounds.j_first,r.bounds.j_last,
        r.bounds.k_first,r.bounds.k_last},r.excluded_lateral_cells,r.excluded_highest_cells});
    record.timings.monitoring_seconds += now()-started;
    check("after_monitor_compile");
    capture(state);
    check("after_initial_checkpoint");
    while (state.termination() == solver::Termination::None) {
      const int before = state.diagnostics().iterations;
      if (!check("before_sweep",before)) break;
      started = now();
      const int interval = record.requested.residual_interval;
      state.advance(1,interval > 0 && (before+1)%interval == 0);
      record.timings.sweeps_seconds += now()-started;
      const auto diagnostics = state.diagnostics();
      record.iterations = diagnostics.iterations;
      record.legacy_tolerance_satisfied = diagnostics.converged;
      if (!check("after_sweep",record.iterations)) break;
      if (record.iterations%record.requested.checkpoint_interval == 0 || state.termination() != solver::Termination::None) {
        if (!check("before_checkpoint",record.iterations)) break;
        capture(state);
        if (!check("after_checkpoint",record.iterations)) break;
      }
    }
    if (record.termination_reason.empty()) {
      record.termination_reason = state.diagnostics().converged ? "legacy_tolerance" : "iteration_limit";
      record.phase = "completed";
      check("before_finalization",record.iterations);
    }
    save_history();
  }
private:
  MonotonicClock clock_;
  double started_ = 0, last_time_ = 0;
  std::unique_ptr<Monitor> monitor_;
  void save_history();
  template<class Real> void capture(const solver::SolverState<Real> &state) {
    const double started = now();
    monitor_->capture(state,started-started_);
    record.timings.monitoring_seconds += now()-started;
    ++record.checkpoint_count;
  }
};
}
