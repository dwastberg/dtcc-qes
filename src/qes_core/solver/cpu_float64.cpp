/****************************************************************************
 * Copyright (c) 2025 University of Utah
 * Copyright (c) 2025 University of Minnesota Duluth
 *
 * Copyright (c) 2025 Behnam Bozorgmehr
 * Copyright (c) 2025 Jeremy A. Gibbs
 * Copyright (c) 2025 Fabien Margairaz
 * Copyright (c) 2025 Eric R. Pardyjak
 * Copyright (c) 2025 Zachary Patterson
 * Copyright (c) 2025 Rob Stoll
 * Copyright (c) 2025 Lucas Ulmer
 * Copyright (c) 2025 Pete Willemsen
 *
 * This file is part of QES-Winds
 *
 * GPL-3.0 License
 *
 * QES-Winds is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3 of the License.
 *
 * QES-Winds is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with QES-Winds. If not, see <https://www.gnu.org/licenses/>.
 ****************************************************************************/

// Float64 arithmetic extracted from dtcc/precision_solver.cpp, itself derived
// from the QES stencil. Widening and statement boundaries are intentional.
#include "solver.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>

namespace dtcc_qes::solver {
template<class Real> template<bool Compact> void SolverState<Real>::rhs64() {
  const auto &d = domain;
  const auto &a = *fields_;
  auto &rhs = R;
  const double dx = d.dx(), dy = d.dy();
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i) {
      const auto c = d.cell(i,j,k), f = d.face(i,j,k);
      const auto coeff = operator_.stencil<Compact>(c,k);
      rhs[c] = -2.0 * ((double(coeff.e)*a.u0[f+1] - double(coeff.f)*a.u0[f])*dx
        + (double(coeff.g)*a.v0[f+d.nx()] - double(coeff.h)*a.v0[f])*dy
        + double(coeff.m)*0.5*(double(d.dz_array[k])+d.dz_array[k+1])*a.w0[f+d.nx()*d.ny()]
        - double(coeff.n)*0.5*(double(d.dz_array[k])+d.dz_array[k-1])*a.w0[f]);
    }
}
// The original float64 kernel already used one ordered loop for both builds.
template<class Real> template<bool Compact, bool Trend> Real SolverState<Real>::ordered64() {
  const auto &d = domain;
  const auto &a = *fields_;
  auto &rhs = R;
  TrendTotals totals;
  double max_error = 0;
    max_error = 0;
    int nonfinite = 0;
#ifdef _OPENMP
#pragma omp parallel if(order_ == SweepOrder::RedBlack) reduction(max : max_error) reduction(| : nonfinite)
#endif
    {
      TrendTotals local_trend;
      const int colours = order_ == SweepOrder::RedBlack ? 2 : 1;
      for (int colour = 0; colour < colours; ++colour) {
#ifdef _OPENMP
#pragma omp for
#endif
        for (int k = 1; k < d.nz()-2; ++k)
          for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
            if (colours == 2 && (i+j+k)%2 != colour) continue;
            const auto c = d.cell(i,j,k);
            const auto coeff = operator_.stencil<Compact>(c,k);
            const double neighbours = double(coeff.e)*lambda[d.cellAdd(c,1,0,0)]
              + double(coeff.f)*lambda[d.cellAdd(c,-1,0,0)]
              + double(coeff.g)*lambda[d.cellAdd(c,0,1,0)]
              + double(coeff.h)*lambda[d.cellAdd(c,0,-1,0)]
              + double(coeff.m)*lambda[d.cellAdd(c,0,0,1)]
              + double(coeff.n)*lambda[d.cellAdd(c,0,0,-1)];
            const double next = factor<Compact>(c,k,coeff)*(neighbours-rhs[c]) + (1.0-omega)*lambda[c];
            const double change = std::abs(next-lambda[c]);
            nonfinite |= !std::isfinite(change);
            max_error = std::max(max_error, change);
            if constexpr (Trend) add_residual(local_trend,c,k,coeff,lambda[c]);
            lambda[c] = next;
          }
      }
#ifdef _OPENMP
#pragma omp for
#endif
      for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i)
        lambda[d.cell(i,j,0)] = lambda[d.cell(i,j,1)];
      if constexpr (Trend) {
#pragma omp critical(dtcc_qes_trend)
        totals.merge(local_trend);
      }
    }
    if (nonfinite) throw qes::RuntimeError("Non-finite Lagrange multiplier change during solve");
  if constexpr (Trend) finish_residual(totals);
  return max_error;
}
template<> void SolverState<double>::build_rhs() {
  if (operator_.compact()) rhs64<true>(); else rhs64<false>();
}
template<> double SolverState<double>::sweep_red_black() {
  if (collect_residual_) return operator_.compact() ? ordered64<true,true>() : ordered64<false,true>();
  return operator_.compact() ? ordered64<true,false>() : ordered64<false,false>();
}
template<> double SolverState<double>::sweep_lexicographic() { return sweep_red_black(); }
template<> float SolverState<double>::corrected_face(int component,int i,int j,int k) const {
  const auto &d = domain;
  const auto &a = *fields_;
  const auto c = d.cell(i,j,k), f = d.face(i,j,k);
  const auto coeff = operator_.stencil(c,k);
  const double dx = d.dx(), dy = d.dy();
  if (component == 0) return float(double(a.u0[f]) + 0.5*double(coeff.f)*dx*(lambda[c]-lambda[c-1]));
  if (component == 1) return float(double(a.v0[f]) + 0.5*double(coeff.h)*dy*(lambda[c]-lambda[d.cellAdd(c,0,-1,0)]));
  return float(double(a.w0[f]) + 0.5*double(coeff.n)*double(d.dz_array[k])
                     *(lambda[c]-lambda[d.cellAdd(c,0,0,-1)]));
}
}
