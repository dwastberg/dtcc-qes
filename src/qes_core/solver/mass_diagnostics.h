// Conservative flux arithmetic extracted from dtcc/divergence.cpp. GPL-3.0.
#pragma once
#include "solver.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace dtcc_qes::solver {
template<class FaceValue> MassDiagnostics mass_diagnostics(const PoissonOperator &data,
    const std::vector<int> &flags, FaceValue face, MassRegion region = {}, FluxOptions options = {}) {
  const auto &d = data.domain;
  const int nx = d.nx()-1, ny = d.ny()-1, nz = d.nz()-2;
  if (region.i_last == -1) region.i_last = nx-1;
  if (region.j_last == -1) region.j_last = ny-1;
  if (region.k_last == -1) region.k_last = nz-1;
  if (region.i_first < 1 || region.i_last > nx-1 || region.i_last < region.i_first
      || region.j_first < 1 || region.j_last > ny-1 || region.j_last < region.j_first
      || region.k_first < 0 || region.k_last > nz-1 || region.k_last < region.k_first)
    throw std::invalid_argument("Mass diagnostic region is outside the assessed cells");
  const double dx = d.dx(), dy = d.dy();
  if (options.enabled && (!std::isfinite(options.reference_speed) || options.reference_speed < 0
      || (options.low_flow_fraction && (!std::isfinite(*options.low_flow_fraction) || *options.low_flow_fraction <= 0))))
    throw std::invalid_argument("Flux normalization requires finite nonnegative Uref and a positive fraction");
  MassDiagnostics stats;
  double weighted_square = 0, volume_sum = 0;
  double relative_square[2] = {0,0}, relative_volume[2] = {0,0};
  const auto contained = [&](int i,int j,int k,bool top) {
    if (i < region.i_first || i >= region.i_last || j < region.j_first || j >= region.j_last
        || k < region.k_first+1 || k >= region.k_last+1 || ((k == nz-1) != top)) return false;
    const auto flag = flags[d.cell(i,j,k)];
    return flag != 0 && flag != 2;
  };
  for (int k = region.k_first+1; k < region.k_last+1; ++k)
    for (int j = region.j_first; j < region.j_last; ++j)
      for (int i = region.i_first; i < region.i_last; ++i) {
        const auto c = d.cell(i,j,k);
        if (flags[c] == 0 || flags[c] == 2) continue;
        const double ue = face(0,i+1,j,k), uw = face(0,i,j,k);
        const double vn = face(1,i,j+1,k), vs = face(1,i,j,k);
        const double wt = face(2,i,j,k+1), wb = face(2,i,j,k);
        for (const double value : {ue, uw, vn, vs, wt, wb})
          if (!std::isfinite(value)) throw std::runtime_error("Non-finite face velocity in divergence diagnostic");
        const auto a = data.stencil(c,k);
        const double dz = d.dz_array[k], volume = dx * dy * dz;
        const double east = a.e * dx * dx, west = a.f * dx * dx;
        const double north = a.g * dy * dy, south = a.h * dy * dy;
        const double above = a.m * dz * 0.5 * (dz + d.dz_array[k + 1]);
        const double below = a.n * dz * 0.5 * (dz + d.dz_array[k - 1]);
        const double net = (east * ue - west * uw) * dy * dz
                         + (north * vn - south * vs) * dx * dz
                         + (above * wt - below * wb) * dx * dy;
        const double divergence = net / volume;
        if (!std::isfinite(divergence)) throw std::runtime_error("Non-finite conservative divergence");
        if (options.enabled) {
          const bool top = k == nz-1;
          auto &flux = top ? stats.top_band_flux : stats.interior_flux;
          // Keep the legacy net/divergence expression above intact. Rounded
          // opposite coefficients need not cancel exactly on internal faces;
          // expose both summed cell flux and actual region-boundary flux.
          const double areas[] = {east*dy*dz,west*dy*dz,north*dx*dz,south*dx*dz,above*dx*dy,below*dx*dy};
          const double q[] = {east*ue*dy*dz,-west*uw*dy*dz,north*vn*dx*dz,-south*vs*dx*dz,
                              above*wt*dx*dy,-below*wb*dx*dy};
          double throughflow = 0, area_sum = 0;
          const int di[] = {1,-1,0,0,0,0}, dj[] = {0,0,1,-1,0,0}, dk[] = {0,0,0,0,1,-1};
          for (int axis = 0; axis < 6; ++axis) {
            throughflow += 0.5*std::abs(q[axis]); area_sum += 0.5*std::abs(areas[axis]);
            if (!contained(i+di[axis],j+dj[axis],k+dk[axis],top)) flux.boundary_flux += q[axis];
          }
          flux.net_cell_flux += net; flux.absolute_cell_flux += std::abs(net); flux.throughflow += throughflow;
          if (!options.low_flow_fraction) ++flux.unassessed_cells;
          else if (!(throughflow > 0 && throughflow > *options.low_flow_fraction*options.reference_speed*area_sum))
            ++flux.low_flow_cells;
          else {
            const double relative = std::abs(net)/throughflow;
            if (!std::isfinite(relative)) throw std::runtime_error("Non-finite relative flux imbalance");
            flux.relative_max = std::max(flux.relative_max.value_or(0),relative); ++flux.resolved_cells;
            relative_square[top] += volume*relative*relative; relative_volume[top] += volume;
          }
        }
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
  if (relative_volume[0]) stats.interior_flux.relative_rms = std::sqrt(relative_square[0]/relative_volume[0]);
  if (relative_volume[1]) stats.top_band_flux.relative_rms = std::sqrt(relative_square[1]/relative_volume[1]);
  return stats;
}
}
