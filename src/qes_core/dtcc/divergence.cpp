#include "divergence.h"
#include "winds/WINDSGeneralData.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace dtcc_qes {
DivergenceStats divergence_stats(const WINDSGeneralData &data, bool initial)
{
  const auto &d = data.domain;
  const auto &u = initial ? data.u0 : data.u;
  const auto &v = initial ? data.v0 : data.v;
  const auto &w = initial ? data.w0 : data.w;
  const int nx = d.nx() - 1, ny = d.ny() - 1, nz = d.nz() - 2;
  const double dx = d.dx(), dy = d.dy();
  DivergenceStats stats;
  double weighted_square = 0, volume_sum = 0;
  // k == nz has unscaled coefficients and no dz_array[k + 1]. Never visit it.
  for (int k = 1; k < nz; ++k)
    for (int j = 1; j < ny - 1; ++j)
      for (int i = 1; i < nx - 1; ++i) {
        const auto c = d.cell(i, j, k), f = d.face(i, j, k);
        if (data.icellflag[c] == 0 || data.icellflag[c] == 2) continue;
        const double ue = u[d.faceAdd(f, 1, 0, 0)], uw = u[f];
        const double vn = v[d.faceAdd(f, 0, 1, 0)], vs = v[f];
        const double wt = w[d.faceAdd(f, 0, 0, 1)], wb = w[f];
        for (const double value : {ue, uw, vn, vs, wt, wb})
          if (!std::isfinite(value)) throw std::runtime_error("Non-finite face velocity in divergence diagnostic");
        const double dz = d.dz_array[k], volume = dx * dy * dz;
        const double east = data.e[c] * dx * dx, west = data.f[c] * dx * dx;
        const double north = data.g[c] * dy * dy, south = data.h[c] * dy * dy;
        const double above = data.m[c] * dz * 0.5 * (dz + d.dz_array[k + 1]);
        const double below = data.n[c] * dz * 0.5 * (dz + d.dz_array[k - 1]);
        const double net = (east * ue - west * uw) * dy * dz
                         + (north * vn - south * vs) * dx * dz
                         + (above * wt - below * wb) * dx * dy;
        const double divergence = net / volume;
        if (!std::isfinite(divergence)) throw std::runtime_error("Non-finite conservative divergence");
        if (k == nz - 1) {
          stats.top_band_max = std::max(stats.top_band_max, std::abs(divergence));
          ++stats.top_band_cells;
        } else {
          stats.interior_max = std::max(stats.interior_max, std::abs(divergence));
          weighted_square += volume * divergence * divergence;
          volume_sum += volume;
          ++stats.cells;
        }
      }
  if (stats.cells) stats.interior_rms = std::sqrt(weighted_square / volume_sum);
  return stats;
}
}
