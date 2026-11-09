#pragma once

// Cell-centred vector sampling at a declared physical height. No extrapolation.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace dtcc_qes {
struct ReferenceSampling {
  int lower = -1, upper = -1;
  double lower_height = 0, upper_height = 0, upper_weight = 0;
  std::size_t valid_columns = 0, excluded_columns = 0;
  double mean_speed = 0;
};

template<class Sample>
ReferenceSampling sample_reference(const std::vector<float> &centres, double height,
                                   std::size_t columns, Sample sample, int begin = 0)
{
  if (begin < 0 || std::size_t(begin) >= centres.size() || !std::isfinite(height)
      || height < centres[begin] || height > centres.back())
    throw std::invalid_argument("Turbulence reference height has no bracketing physical cell centres; refine the first layer or extend the domain");
  ReferenceSampling out;
  const auto at = std::lower_bound(centres.begin()+begin, centres.end(), height);
  out.upper = int(at-centres.begin());
  out.lower = *at == height ? out.upper : out.upper-1;
  out.lower_height = centres[out.lower];
  out.upper_height = centres[out.upper];
  out.upper_weight = out.lower == out.upper ? 0
    : (height-out.lower_height)/(out.upper_height-out.lower_height);
  double total = 0;
  for (std::size_t column = 0; column < columns; ++column) {
    const auto a = sample(out.lower, column);
    // Exact-centre requests have one positive-weight source only.
    const auto b = out.lower == out.upper ? a : sample(out.upper, column);
    if (!a.first || !b.first) { ++out.excluded_columns; continue; }
    std::array<double,3> velocity;
    for (int c = 0; c < 3; ++c) {
      if (!std::isfinite(a.second[c]) || !std::isfinite(b.second[c]))
        throw std::invalid_argument("Turbulence reference has nonfinite fluid velocity support");
      velocity[c] = (1-out.upper_weight)*a.second[c]+out.upper_weight*b.second[c];
    }
    const double speed = std::sqrt(velocity[0]*velocity[0]+velocity[1]*velocity[1]+velocity[2]*velocity[2]);
    if (!std::isfinite(speed))
      throw std::invalid_argument("Turbulence reference speed is nonfinite");
    total += speed;
    ++out.valid_columns;
  }
  if (!out.valid_columns)
    throw std::invalid_argument("Turbulence reference has no complete fluid columns at the declared height");
  out.mean_speed = total/double(out.valid_columns);
  return out;
}
}
