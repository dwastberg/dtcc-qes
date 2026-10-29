#pragma once

// Internal to the native runner. Bindings must never include this header.
#include "wind_config.h"
#include "winds/WindModelInputs.h"
#include "qes/Domain.h"
#include <vector>

namespace dtcc_qes {
// Validated float32 inputs of the wind and turbulence models. All conversion
// from the float64 boundary to QES float lives in model_inputs.cpp.
struct ModelInputs {
  int nx = 0, ny = 0, nz = 0;
  float spacing = 0;
  std::vector<float> layers; // Explicit layer thicknesses; empty for uniform cells.
  std::vector<BuildingFootprint> buildings;
  BuildingParameterizations parameterizations;
  InflowCondition inflow;
  TurbulenceConfig turbulence;
  bool turbulence_enabled = false;

  ModelInputs(const GridConfig &, const ModelSettings &, const BuildingArrays &,
              const TurbulenceSettings & = {});
  void set_condition(const WindCondition &);
};
float qes_tolerance(const SolverOptions &);
double solver_tolerance(const SolverOptions &);
std::vector<float> vertical_faces(const GridConfig &);
qes::Domain make_domain(const ModelInputs &);
}
