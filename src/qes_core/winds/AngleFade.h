#pragma once

#include <algorithm>

/**
 * Weight of a building zone that is applied to a wall near one alignment with the wind.
 *
 * QES switches such a zone on inside ``tol`` of the aligned direction and off outside it, so the whole
 * zone appears between two wind directions. With a half-width h > 0 the weight is 1 up to tol - h and
 * falls by a smoothstep to 0 at tol + h; the zone's change of the velocity is multiplied by it.
 *
 * @param half_width_deg h in degrees; 0 keeps the switch
 * @param deviation angle between the wall and its aligned direction (radians, >= 0)
 * @param tol the switch angle (radians)
 * @param inside the switch's own test, returned as 1 or 0 when h is 0, so that the released
 *        comparison (inclusive or strict) is kept bit for bit
 */
inline float angleFadeWeight(float half_width_deg, float deviation, float tol, bool inside)
{
  const float h = half_width_deg * 3.14159265358979323846f / 180.0f;
  if (h <= 0.0f) return inside ? 1.0f : 0.0f;
  const float t = std::clamp((tol + h - deviation) / (2.0f * h), 0.0f, 1.0f);
  return t * t * (3.0f - 2.0f * t);
}
