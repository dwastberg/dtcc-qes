#pragma once
// Native boundary for coordinate-only policy queries; no QES/field storage.
#include "wind_config.h"

namespace dtcc_qes {
struct PolicyEligibility {
  std::vector<std::string> exclusions;
  std::vector<std::string> pending_runtime_checks;
};
std::vector<std::string> pedestrian_input_exclusions(ProfileKind, const SolverOptions &,
                                                  bool turbulence, std::optional<int> threads = {});
PolicyEligibility pedestrian_preflight(const GridConfig &,const ModelSettings &,const BuildingArrays &,
                                      const TurbulenceSettings &,const WindCondition &,const SolverOptions &,
                                      const MonitorSpec &,std::optional<int> threads = {});
}
