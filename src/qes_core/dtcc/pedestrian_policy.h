#pragma once
#include "api/policy_types.h"
#include "api/monitor_types.h"
#include "model_inputs.h"
#include <algorithm>
#include <cmath>

namespace dtcc_qes {
bool policy_build_supported();
std::string pedestrian_scope(const GridConfig &,const ModelSettings &,const ModelInputs &,
                             const SolverOptions &,const MonitorSpec &,int threads);
PolicyPrediction predict_pedestrian(const MonitorCheckpoint &);
bool prediction_meets_target(const PolicyPrediction &);

// Small bounded state only; no velocity/history volume or per-point arrays.
class PedestrianDecision {
public:
  PolicyEvidence evaluate(const MonitorCheckpoint &,double residual_max,double residual_rms,
                          std::size_t cells,bool safeguards,double mass_max,double mass_rms);
  bool stagnated() const {return stagnation_ >= 4;}
private:
  int consecutive_ = 0, stagnation_ = 0;
  double previous_residual_ = -1;
  int previous_iteration_ = -1;
  struct Anchor {int iteration;double vector,speed,qmin,qmax;};
  std::optional<Anchor> anchor_;
};
}
