#pragma once

// QES-free numerical contract shared by extraction and derived statistics.
// Component order: xx, xy, xz, yy, yz, zz; values remain unmodified.
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace dtcc_qes {
using StressTensor = std::array<float, 6>;
inline constexpr double stress_validity_relative_tolerance =
  32 * double(std::numeric_limits<float>::epsilon());

struct StressValidity {
  bool valid = false;
  double minimum_eigenvalue = std::numeric_limits<double>::quiet_NaN();
  double spectral_radius = std::numeric_limits<double>::quiet_NaN();
  double tolerance = std::numeric_limits<double>::quiet_NaN();
};

inline StressValidity stress_validity(const StressTensor &stress) noexcept
{
  double scale = 0;
  for (const float value : stress) {
    if (!std::isfinite(value)) return {};
    scale = std::max(scale, std::abs(double(value)));
  }
  if (scale == 0) return {true, 0, 0, 0};

  // Normalize before a bounded symmetric Jacobi diagonalization. Only the
  // eigenvalues are needed; no per-cell allocation or eigenvectors are kept.
  double a[3][3] = {{stress[0] / scale, stress[1] / scale, stress[2] / scale},
                    {stress[1] / scale, stress[3] / scale, stress[4] / scale},
                    {stress[2] / scale, stress[4] / scale, stress[5] / scale}};
  for (int iteration = 0; iteration < 32; ++iteration) {
    int p = 0, q = 1;
    if (std::abs(a[0][2]) > std::abs(a[p][q])) { p = 0; q = 2; }
    if (std::abs(a[1][2]) > std::abs(a[p][q])) { p = 1; q = 2; }
    if (std::abs(a[p][q]) <= 8 * std::numeric_limits<double>::epsilon()) break;
    const double offset = (a[q][q] - a[p][p]) / (2 * a[p][q]);
    const double t = std::copysign(1.0 / (std::abs(offset) + std::hypot(1.0, offset)), offset);
    const double c = 1.0 / std::hypot(1.0, t), s = t * c;
    const double off_diagonal = a[p][q];
    a[p][p] -= t * off_diagonal;
    a[q][q] += t * off_diagonal;
    a[p][q] = a[q][p] = 0;
    for (int r = 0; r < 3; ++r) {
      if (r == p || r == q) continue;
      const double rp = a[r][p], rq = a[r][q];
      a[r][p] = a[p][r] = c * rp - s * rq;
      a[r][q] = a[q][r] = s * rp + c * rq;
    }
  }
  if (std::max({std::abs(a[0][1]), std::abs(a[0][2]), std::abs(a[1][2])})
        > 8 * std::numeric_limits<double>::epsilon()) return {};
  const double minimum = std::min({a[0][0], a[1][1], a[2][2]}) * scale;
  const double radius = std::max({std::abs(a[0][0]), std::abs(a[1][1]), std::abs(a[2][2])}) * scale;
  const double tolerance = stress_validity_relative_tolerance * radius;
  return {minimum >= -tolerance, minimum, radius, tolerance};
}

inline double streamwise_variance(const StressTensor &stress,
                                  const std::array<double, 3> &velocity) noexcept
{
  const double nan = std::numeric_limits<double>::quiet_NaN();
  for (const double value : velocity)
    if (!std::isfinite(value)) return nan;
  const double speed = std::hypot(velocity[0], velocity[1], velocity[2]);
  if (speed == 0 || !std::isfinite(speed)) return nan;
  const auto validity = stress_validity(stress);
  if (!validity.valid) return nan;
  const double x = velocity[0] / speed, y = velocity[1] / speed, z = velocity[2] / speed;
  const double projected = stress[0] * x * x + stress[3] * y * y + stress[5] * z * z
    + 2 * (stress[1] * x * y + stress[2] * x * z + stress[4] * y * z);
  if (projected < -validity.tolerance) return nan;
  return std::max(0.0, projected);
}
}
