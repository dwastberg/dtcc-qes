#include "solver_control.h"
#include "api/build_info.h"
#include "util/QESException.h"
#include <chrono>
#include <cmath>
#include <limits>

namespace dtcc_qes {
SolverController::SolverController(const SolverControl &spec,MonotonicClock clock)
  : clock_(std::move(clock)) {
  if ((spec.mode != "bounded" && spec.mode != "adaptive") || !std::isfinite(spec.max_solve_seconds) || spec.max_solve_seconds <= 0
      || spec.checkpoint_interval < 1 || spec.residual_interval < 0)
    throw qes::InputError("Solver controls require bounded/adaptive mode, a positive finite time budget and valid intervals");
  if((spec.mode=="adaptive" && (spec.policy!=pedestrian_policy_id || spec.checkpoint_interval!=25 || spec.monitor.history_limit<5))
      || (spec.mode=="bounded" && !spec.policy.empty()))
    throw qes::InputError("Adaptive mode requires policy pedestrian-v1, cadence 25 and history >=5; bounded mode has no policy");
  if (!clock_) clock_ = [] {return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();};
  started_ = last_time_ = now();
  record.requested = spec;record.effective_monitor = spec.monitor;
  record.mode=spec.mode;record.policy=spec.policy;
  if(spec.mode=="adaptive")record.policy_revision=solver_policy_revision();
  record.method=spec.mode=="adaptive"?pedestrian_method_id:legacy_method_id;
  if(spec.mode=="adaptive") {
    record.accuracy_status="unaccepted";record.assessment_scope="pedestrian_roi_and_required_receptors";
    record.assessment_reason="pending_assessment";
  }
}
void SolverController::configure_adaptive(const std::vector<std::string> &reasons) {
  if(record.mode!="adaptive")return;
  record.exclusions=reasons;
  if(!reasons.empty()) {
    record.accuracy_status="not_assessed";record.assessment_reason=reasons.front();
    record.method=legacy_method_id;return;
  }
  auto &s=record.effective_monitor;
  const auto bytes=sizeof(PolicyEvidence)+384;
  if(s.history_limit>(std::numeric_limits<std::size_t>::max()-1024)/bytes)
    throw qes::InputError("Policy history memory estimate overflow");
  policy_bytes_=s.history_limit*bytes+1024;
  if(policy_bytes_>=s.memory_limit_bytes)throw qes::InputError("Policy history exceeds monitor memory limit");
  record.assessment_history.reserve(s.history_limit);
  s.short_window=1;s.long_window=4;s.global_mass=true;adaptive_=true;
}
[[noreturn]] void SolverController::numerical_failure(const std::string &message) {
  record.accepted=false;record.accuracy_status="unaccepted";record.termination_reason="numerical_failure";
  record.assessment_reason=message;record.phase="failed";
  try {save_history();} catch(const std::exception &) {}
  throw NumericalFailure(record,message);
}
double SolverController::now() const {
  const double value = clock_();
  if (!std::isfinite(value)) throw qes::RuntimeError("Non-finite monotonic clock");
  return value;
}
bool SolverController::check(const char *phase,int completed) {
  const double time = now();
  if (time < last_time_) throw qes::RuntimeError("Solver clock moved backwards");
  last_time_ = time;
  record.timings.solve_seconds = time-started_;
  if (record.timings.solve_seconds < record.requested.max_solve_seconds) return true;
  record.phase = phase;record.termination_reason = "time_limit";record.iterations = completed;
  if(record.mode=="adaptive" && record.accuracy_status!="not_assessed") {
    record.accepted=false;record.accuracy_status="unaccepted";record.assessment_reason="deadline_before_acceptance";
  }
  record.timings.deadline_overshoot_seconds = std::max(0.0,record.timings.solve_seconds-record.requested.max_solve_seconds);
  if (!completed) {save_history();record.timings.native_total_seconds = record.timings.solve_seconds;throw BudgetExhausted(record);}
  return false;
}
void SolverController::save_history() {
  if (!monitor_) return;
  record.checkpoint_history.clear();
  for (std::size_t i=0;i<monitor_->history_size();++i) record.checkpoint_history.push_back(monitor_->history_at(i));
  record.history_truncated = record.checkpoint_count > record.checkpoint_history.size();
}
void SolverController::finish_output() {record.timings.native_total_seconds = now()-started_;}
}
