#pragma once
// Offline research replay only; never included by the runtime.
#include "stress_validity.h"

namespace dtcc_qes {


inline float uncapped_energy(float viscosity,float length,float c_pope=.55f) noexcept {
  if(length==0 && viscosity==0)return 0;
  // Preserve the native float division and double pow before float storage.
  return float(std::pow(viscosity/(c_pope*length),2.0));
}

inline double production_scale(float capped,float uncapped) noexcept {
  if(!std::isfinite(capped) || !std::isfinite(uncapped) || capped<0 || uncapped<0)
    return std::numeric_limits<double>::quiet_NaN();
  return uncapped>0?std::min(1.,double(capped)/uncapped):1.;
}

inline StressTensor consistent_constitutive(const StressTensor &strain,float viscosity,
                                            float uncapped,float capped) noexcept {
  const double r=production_scale(capped,uncapped);
  StressTensor out;
  for(int n=0;n<6;++n) {
    // Float product and intermediate storage reproduce the frozen ablation.
    const float raw=float((n==0 || n==3 || n==5 ? (2./3.)*uncapped : 0.)-2.*(viscosity*strain[n]));
    out[n]=float(double(raw)*r);
  }
  return out;
}

inline double spectral_limit(StressTensor &stress,float bound) noexcept {
  if(!std::isfinite(bound) || bound<0)return std::numeric_limits<double>::quiet_NaN();
  for(float value:stress)if(!std::isfinite(value))return std::numeric_limits<double>::quiet_NaN();
  // An absolute row-sum bound proves that alpha=1, avoiding an eigensolve
  // for the common inactive case without changing the spectral formulation.
  const double upper=std::max({std::abs(double(stress[0]))+std::abs(double(stress[1]))+std::abs(double(stress[2])),
    std::abs(double(stress[1]))+std::abs(double(stress[3]))+std::abs(double(stress[4])),
    std::abs(double(stress[2]))+std::abs(double(stress[4]))+std::abs(double(stress[5]))});
  if(upper<=bound)return 1.;
  const double radius=stress_validity(stress).spectral_radius;
  if(!std::isfinite(radius))return std::numeric_limits<double>::quiet_NaN();
  const double alpha=radius>0?std::min(1.,double(bound)/radius):1.;
  for(float &value:stress)value=float(double(value)*alpha);
  return alpha;
}
}
