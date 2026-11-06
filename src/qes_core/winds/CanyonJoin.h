#pragma once
#include <stdexcept>
#include "canyon_kernel.h"
namespace joint_canyon {
// qes-canyon-join-v1: vector components share this scalar Hermite operator.
// A includes the retained gamma*cross-speed*4r(1-r) component amplitude.
inline double joined(double x,double y,double width,double along,double amplitude,double incident) {
  const double b=.5*width,d=.2*x,a=b-d,s=b-2*d;
  if(!(width>0) || !std::isfinite(x+y+width+along+amplitude+incident))
    throw std::invalid_argument("Nonfinite or degenerate canyon join input");
  if(std::abs(y)>=b) return incident;
  if(!(d>0) || std::abs(y)<=s) return along+amplitude*core(x,y,width);
  if(!(s>0)) throw std::invalid_argument("Collapsed canyon join support");
  const double f=std::pow(d/a,.25),q0=along+amplitude*f;
  const double t=(std::abs(y)-s)/(2*d),t2=t*t,t3=t2*t;
  // L*m0=-amplitude*f/2; no division by a vanishing mixing width.
  return (2*t3-3*t2+1)*q0-(t3-2*t2+t)*amplitude*f*.5+(-2*t3+3*t2)*incident;
}
}
