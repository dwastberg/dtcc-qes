#pragma once
#include "api/control_types.h"
#include "monitor.h"
#include "pedestrian_policy.h"
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
  void configure_adaptive(const std::vector<std::string> &unsupported_reasons);
  bool adaptive_enabled() const {return adaptive_;}
  [[noreturn]] void numerical_failure(const std::string &);
  template<class Real> void run(solver::SolverState<Real> &state, std::atomic<int> *completed_checkpoint = nullptr) {
    if (!check("before_monitor_compile")) return;
    auto started = now();
    auto monitor_spec=record.effective_monitor;
    if(adaptive_)monitor_spec.memory_limit_bytes-=policy_bytes_;
    monitor_ = std::make_unique<Monitor>(state,monitor_spec);
    record.monitor_bytes = monitor_->allocated_bytes()+policy_bytes_;
    for (const auto &r : monitor_->regions())
      record.regions.push_back({r.name,{r.bounds.i_first,r.bounds.i_last,r.bounds.j_first,r.bounds.j_last,
        r.bounds.k_first,r.bounds.k_last},r.excluded_lateral_cells,r.excluded_highest_cells});
    record.timings.monitoring_seconds += now()-started;
    check("after_monitor_compile");
    capture(state,completed_checkpoint);
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
      if(adaptive_ && invalid_initial_support_) {
        capture(state,completed_checkpoint);if(!check("after_invalid_support_checkpoint",record.iterations))break;
        record.termination_reason="invalid_support";record.assessment_reason="invalid_required_or_empty_support";
        break;
      }
      if (record.iterations%record.requested.checkpoint_interval == 0 || state.termination() != solver::Termination::None) {
        if (!check("before_checkpoint",record.iterations)) break;
        capture(state,completed_checkpoint);
        if (!check("after_checkpoint",record.iterations)) break;
        if(adaptive_ && record.assessment && record.assessment->ready) {
          if(!check("before_finalization",record.iterations))break;
          record.accepted=true;record.accuracy_status="accepted";record.termination_reason="accepted";
          record.assessment_reason="qualified_pedestrian_outputs";record.phase="accepted";
          record.assessment->accepted=true;record.assessment_history.back().accepted=true;
          break;
        }
        if(adaptive_ && policy_.stagnated()) {
          record.termination_reason="stagnation";record.assessment_reason="unavailable_tail_at_precision_plateau";break;
        }
      }
    }
    if (record.termination_reason.empty()) {
      record.termination_reason = !adaptive_ && state.diagnostics().converged ? "legacy_tolerance" : "iteration_limit";
      record.phase = "completed";
      check("before_finalization",record.iterations);
    }
    if(adaptive_ && !record.accepted && record.assessment_reason=="pending_assessment")
      record.assessment_reason=record.termination_reason=="iteration_limit"?"insufficient_qualifying_evidence":record.termination_reason;
    save_history();
  }
private:
  MonotonicClock clock_;
  double started_ = 0, last_time_ = 0;
  std::unique_ptr<Monitor> monitor_;
  bool adaptive_ = false, invalid_initial_support_ = false;
  std::size_t policy_bytes_ = 0;
  PedestrianDecision policy_;
  void save_history();
  template<class Real> void capture(const solver::SolverState<Real> &state, std::atomic<int> *completed_checkpoint) {
    const double started = now();
    const auto &checkpoint=monitor_->capture(state,started-started_);
    if(adaptive_) {
      if(checkpoint.initial) {
        invalid_initial_support_=!checkpoint.required_receptors_valid
          || std::any_of(checkpoint.heights.begin(),checkpoint.heights.end(),[](const auto &h){return h.valid<16;});
      } else assess(state,checkpoint);
    }
    record.timings.monitoring_seconds += now()-started;
    ++record.checkpoint_count;
    if (completed_checkpoint) completed_checkpoint->store(checkpoint.iteration,std::memory_order_relaxed);
  }
  template<class Real> void assess(const solver::SolverState<Real> &state,const MonitorCheckpoint &checkpoint) {
    const auto residual=state.equation_residual();
    const double rmax=residual.relative_maximum.value_or(-1),rrms=residual.relative_volume_weighted_rms.value_or(-1);
    bool passed=residual.fluid_cells>0 && residual.rhs_maximum>0 && residual.rhs_volume_weighted_rms>0
      && rmax>=0 && rmax<=policy_residual_maximum && rrms>=0 && rrms<=policy_residual_rms;
    double mass_max=0,mass_rms=0;
    const double scale=policy_mass_length/record.effective_monitor.reference_speed;
    for(std::size_t n=0;n<checkpoint.mass.size();++n) {
      const auto &mass=checkpoint.mass[n].divergence;
      mass_max=std::max(mass_max,mass.interior_max*scale);mass_rms=std::max(mass_rms,mass.interior_rms*scale);
      const auto r=state.equation_residual(monitor_->regions()[n].bounds);
      passed &= mass.cells>0 && std::isfinite(mass.interior_max) && std::isfinite(mass.interior_rms)
        && mass.interior_max*scale<=policy_mass_maximum && mass.interior_rms*scale<=policy_mass_rms
        && r.fluid_cells>0 && r.maximum/residual.rhs_maximum<=policy_residual_maximum
        && r.volume_weighted_rms/residual.rhs_volume_weighted_rms<=policy_residual_rms;
    }
    auto evidence=policy_.evaluate(checkpoint,rmax,rrms,residual.fluid_cells,passed,mass_max,mass_rms);
    record.assessment=evidence;++record.assessment_count;
    if(record.assessment_history.size()==record.effective_monitor.history_limit)record.assessment_history.erase(record.assessment_history.begin());
    record.assessment_history.push_back(std::move(evidence));
  }
};
}
