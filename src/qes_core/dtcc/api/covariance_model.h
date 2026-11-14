#pragma once
#include "stress_validity.h"

namespace dtcc_qes {
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
