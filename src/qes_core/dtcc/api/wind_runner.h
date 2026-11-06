#pragma once

#include "log_sink.h"
#include "wind_config.h"
#include <memory>
#include <functional>
#include <atomic>
#include <mutex>
#include "runner_progress.h"
#include "resource_usage.h"

namespace dtcc_qes {
class WindRunner {
public:
  WindRunner();
  ~WindRunner();
  WindRunner(const WindRunner &) = delete;
  WindRunner &operator=(const WindRunner &) = delete;

  // Failed preparation preserves the last successfully prepared geometry.
  void prepare(const GridConfig &, const ModelSettings &, const BuildingArrays &, Messages &);
  void prepare(const GridConfig &, const ModelSettings &, const BuildingArrays &,
               const TurbulenceSettings &, Messages &);
  WindData solve(const WindCondition &, const SolverOptions &, Messages &, const SolverControl * = nullptr,
                 const std::function<double()> &native_test_clock = {});

  RunnerProgress progress() const;
  void output_transfer(std::uint64_t operation_id, bool finished, bool failed = false);

private:
  class ProgressScope;
  mutable std::mutex progress_mutex_;
  std::mutex operation_mutex_;
  RunnerProgress progress_;
  std::atomic<int> completed_sweeps_{0}, completed_checkpoint_{0};
  void start_progress(const char *operation);
  void progress_phase(const char *phase, bool finished = false);
  void stage_progress(const char *stage);
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
