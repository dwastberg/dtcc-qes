#pragma once
#include "canyon_kernel.h"

namespace joint_canyon {
// A grid can represent a roof above OR below its physical height. Preserve
// both bands; substituting either height alone can weaken the other contract.
inline bool protected_roof(double x,double physical_distance,double legacy_distance) {
  return vertical(x,physical_distance) || vertical(x,legacy_distance);
}
}
