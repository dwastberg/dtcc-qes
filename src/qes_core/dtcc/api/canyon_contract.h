#pragma once
#include "wind_config.h"

namespace dtcc_qes {
// Validate supported canyon combinations before attaching state.
inline void validate_canyon_contract(const CanyonOptions& e,const ModelSettings& m,bool turbulence,
                                    int mixing_length_method=0) {
  canyon_model_name(e.canyon_model);
  if(e.canyon_model==CanyonModel::Legacy) return;
  if(m.street_canyon_flag!=1 || m.rooftop_flag!=1 || m.upwind_cavity_flag!=2 ||
     m.wake_flag!=2 || m.high_rise_flag!=0 || m.sidewall_flag!=1 || m.street_intersection_flag!=0 ||
     (turbulence && (!e.canyon_baseline_turbulence || mixing_length_method!=0)))
    throw std::invalid_argument("Research canyon models require frozen legacy parameterizations and standard turbulence");
}
}
