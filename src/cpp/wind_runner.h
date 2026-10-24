#pragma once

#include "log_sink.h"
#include "wind_config.h"
#include <memory>

namespace dtcc_qes {
class WindRunner {
public:
  WindRunner();
  ~WindRunner();
  WindRunner(const WindRunner &) = delete;
  WindRunner &operator=(const WindRunner &) = delete;

  // Failed preparation preserves the last successfully prepared geometry.
  void prepare(const GridConfig &, const ModelSettings &, const BuildingArrays &, Messages &);
  WindData solve(const WindCondition &, const SolverOptions &, Messages &);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
