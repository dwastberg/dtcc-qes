#pragma once
#include <cmath>

// Fold a facade normal into the grid-component frame used by the cavity.
inline float cavityFrame(float &normal)
{
  float gamma;
  if (normal > M_PI) {
    normal -= 2 * M_PI;
  }

  if (normal >= 0.75 * M_PI) {
    gamma = normal - M_PI;
  } else if (normal >= 0.25 * M_PI) {
    gamma = normal - 0.5 * M_PI;
  } else if (normal < -0.75 * M_PI) {
    gamma = normal + M_PI;
  } else if (normal < -0.25 * M_PI) {
    gamma = normal + 0.5 * M_PI;
  } else {
    gamma = normal;
  }
  return gamma;
}
