#pragma once

// Internal to the native runner. Bindings must never include this header.
#include "wind_config.h"
#include "winds/WINDSInputData.h"
#include "winds/PolyBuilding.h"
#include <memory>

namespace dtcc_qes {
struct QESInputs {
  SimulationParameters simulation;
  MetParams met;
  BuildingsParams buildings;
  Sensor sensor;
  TimeSeries series;
  std::vector<std::unique_ptr<PolyBuilding>> polygons;
  WINDSInputData input;

  QESInputs(const GridConfig &, const ModelSettings &, const BuildingArrays &);
  void set_condition(const WindCondition &);
  QESInputs(const QESInputs &) = delete;
  QESInputs &operator=(const QESInputs &) = delete;
};
// All conversion from the float64 boundary to QES float lives in this file.
float qes_tolerance(const SolverOptions &);
}
