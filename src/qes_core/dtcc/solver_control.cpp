#include "solver_control.h"
#include "util/QESException.h"
#include <chrono>
#include <cmath>

namespace dtcc_qes {
SolverController::SolverController(const SolverControl &spec,MonotonicClock clock)
  : clock_(std::move(clock)) {
  if (spec.mode != "bounded" || !std::isfinite(spec.max_solve_seconds) || spec.max_solve_seconds <= 0
      || spec.checkpoint_interval < 1 || spec.residual_interval < 0)
    throw qes::InputError("Solver controls require bounded mode, a positive finite time budget and valid intervals");
  if (!clock_) clock_ = [] {return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();};
  started_ = last_time_ = now();
  record.requested = spec;record.effective_monitor = spec.monitor;
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
