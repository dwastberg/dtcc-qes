#pragma once

#include "log_sink.h"
#include "wind_config.h"
#include <memory>
#include <functional>

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

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
