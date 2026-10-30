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

// Phase extraction of the QES float32 CPU kernels. Expressions and statement
// boundaries below deliberately retain the original arithmetic.
#include "solver.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>
#include <math.h>

namespace dtcc_qes::solver {
template<class Real> template<bool Compact> void SolverState<Real>::rhs32() {
  const auto *WGD = &*fields_;
  long icell_cent, icell_face;
#pragma omp parallel if(order_ == SweepOrder::RedBlack) private(icell_cent, icell_face) default(none) shared(WGD, R)
  {
#pragma omp for
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 0; j < domain.ny() - 1; ++j) {
        for (int i = 0; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          const auto a = operator_.stencil<Compact>(icell_cent,k);
          // icell_face = i + j * WGD->nx + k * WGD->nx * WGD->ny;
          icell_face = domain.face(i, j, k);
          // Calculate divergence of initial velocity field
        // m/n already include 1/(dz * centre separation). Cancel only the
        // centre separation here, retaining 1/dz for the vertical divergence.
        R[icell_cent] = (-2.0f * pow(alpha1, 2.0))
                          * (((a.e * WGD->u0[domain.faceAdd(icell_face, 1, 0, 0)]
                               - a.f * WGD->u0[icell_face])
                              * domain.dx())
                             + ((a.g * WGD->v0[domain.faceAdd(icell_face, 0, 1, 0)]
                                 - a.h * WGD->v0[icell_face])
                                * domain.dy())
                             + ((a.m * 0.5 * (domain.dz_array[k] + domain.dz_array[k + 1])
                                   * WGD->w0[domain.faceAdd(icell_face, 0, 0, 1)]
                                 - a.n * 0.5f * (domain.dz_array[k] + domain.dz_array[k - 1])
                                     * WGD->w0[icell_face])));
        }
      }
    }
  }
}
template<class Real> template<bool Compact, bool Trend> Real SolverState<Real>::lex32() {
  const auto *WGD = &*fields_;
  long icell_cent;
  float error, max_error = 0;
  TrendTotals totals;
    int nonfinite = 0;

    //
    // main SOR formulation loop
    //
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 1; j < domain.ny() - 2; ++j) {
        for (int i = 1; i < domain.nx() - 2; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          const auto a = operator_.stencil<Compact>(icell_cent,k);
          const float previous = lambda[icell_cent];
          const float next = factor<Compact>(icell_cent,k,a)
                                 * (a.e * lambda[domain.cellAdd(icell_cent, 1, 0, 0)]
                                    + a.f * lambda[domain.cellAdd(icell_cent, -1, 0, 0)]
                                    + a.g * lambda[domain.cellAdd(icell_cent, 0, 1, 0)]
                                    + a.h * lambda[domain.cellAdd(icell_cent, 0, -1, 0)]
                                    + a.m * lambda[domain.cellAdd(icell_cent, 0, 0, 1)]
                                    + a.n * lambda[domain.cellAdd(icell_cent, 0, 0, -1)] - R[icell_cent])
                               + (1.0f - omega) * lambda[icell_cent];// SOR formulation
          if constexpr (Trend) add_residual(totals,icell_cent,k,a,previous);
          lambda[icell_cent] = next;
          error = fabs(next - previous);
          if (!std::isfinite(error)) nonfinite = 1;
          if (error > max_error) max_error = error;
        }
      }
    }

    // Mirror boundary condition (lambda (@k=0) = lambda (@k=1))
    for (int j = 0; j < domain.ny() - 1; ++j) {
      for (int i = 0; i < domain.nx() - 1; ++i) {
        // icell_cent = i + j * (WGD->nx - 1);// Lineralized index for cell centered values
        icell_cent = domain.cell(i, j, 0);
        lambda[icell_cent] = lambda[domain.cellAdd(icell_cent, 0, 0, 1)];
      }
    }


    if (nonfinite)
      throw qes::RuntimeError("Non-finite Lagrange multiplier change during solve");
  if constexpr (Trend) finish_residual(totals);
  return max_error;
}
template<class Real> template<bool Compact, bool Trend> Real SolverState<Real>::rb32() {
  const auto *WGD = &*fields_;
  long icell_cent, icell_face;
  float error, max_error = 0;
  TrendTotals totals;
    max_error = 0.0f;
    int nonfinite = 0;

// Each cell is updated once; its pre-update value is its sweep-start value.
#pragma omp parallel private(icell_cent, icell_face, error) default(none) shared(WGD, lambda, R, totals) reduction(max : max_error) reduction(| : nonfinite)
    {
      TrendTotals local_trend;
      // main SOR formulation loop

      // Red nodes pass
#pragma omp for
      for (int k = 1; k < domain.nz() - 2; ++k) {
        for (int j = 1; j < domain.ny() - 2; ++j) {
          for (int i = 1; i < domain.nx() - 2; ++i) {

            if (((i + j + k) % 2) == 0) {
              // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
              icell_cent = domain.cell(i, j, k);
          const auto a = operator_.stencil<Compact>(icell_cent,k);
              const float previous = lambda[icell_cent];
              const float next = factor<Compact>(icell_cent,k,a)
                                     * (a.e * lambda[domain.cellAdd(icell_cent, 1, 0, 0)]
                                        + a.f * lambda[domain.cellAdd(icell_cent, -1, 0, 0)]
                                        + a.g * lambda[domain.cellAdd(icell_cent, 0, 1, 0)]
                                        + a.h * lambda[domain.cellAdd(icell_cent, 0, -1, 0)]
                                        + a.m * lambda[domain.cellAdd(icell_cent, 0, 0, 1)]
                                        + a.n * lambda[domain.cellAdd(icell_cent, 0, 0, -1)] - R[icell_cent])
                                   + (1.0f - omega) * lambda[icell_cent];// SOR formulation
              if constexpr (Trend) add_residual(local_trend,icell_cent,k,a,previous);
              lambda[icell_cent] = next;
              error = fabs(next - previous);
              if (!std::isfinite(error)) nonfinite = 1;
              if (error > max_error) max_error = error;
            }
          }
        }
      }
      // end of omp for (with implicit barrier)

      // Black nodes pass
#pragma omp for
      for (int k = 1; k < domain.nz() - 2; ++k) {
        for (int j = 1; j < domain.ny() - 2; ++j) {
          for (int i = 1; i < domain.nx() - 2; ++i) {
            if (((i + j + k) % 2) == 1) {
              // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
              icell_cent = domain.cell(i, j, k);
          const auto a = operator_.stencil<Compact>(icell_cent,k);
              const float previous = lambda[icell_cent];
              const float next = factor<Compact>(icell_cent,k,a)
                                     * (a.e * lambda[domain.cellAdd(icell_cent, 1, 0, 0)]
                                        + a.f * lambda[domain.cellAdd(icell_cent, -1, 0, 0)]
                                        + a.g * lambda[domain.cellAdd(icell_cent, 0, 1, 0)]
                                        + a.h * lambda[domain.cellAdd(icell_cent, 0, -1, 0)]
                                        + a.m * lambda[domain.cellAdd(icell_cent, 0, 0, 1)]
                                        + a.n * lambda[domain.cellAdd(icell_cent, 0, 0, -1)] - R[icell_cent])
                                   + (1.0f - omega) * lambda[icell_cent];// SOR formulation
              if constexpr (Trend) add_residual(local_trend,icell_cent,k,a,previous);
              lambda[icell_cent] = next;
              error = fabs(next - previous);
              if (!std::isfinite(error)) nonfinite = 1;
              if (error > max_error) max_error = error;
            }
          }
        }
      }
      // end of omp for (with implicit barrier)

      // Mirror boundary condition (lambda (@k=0) = lambda (@k=1))
#pragma omp for
      for (int j = 0; j < domain.ny() - 1; ++j) {
        for (int i = 0; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1);// Lineralized index for cell centered values
          icell_cent = domain.cell(i, j, 0);
          lambda[icell_cent] = lambda[domain.cellAdd(icell_cent, 0, 0, 1)];
        }
      }
      // end of omp for (with implicit barrier)

      if constexpr (Trend) {
#pragma omp critical(dtcc_qes_trend)
        totals.merge(local_trend);
      }
    }
    // end of omp parallel workshare
    // Exceptions must leave the parallel region on the calling thread.
    if (nonfinite)
      throw qes::RuntimeError("Non-finite Lagrange multiplier change during solve");
  if constexpr (Trend) finish_residual(totals);
  return max_error;
}
template<> void SolverState<float>::build_rhs() {
  if (operator_.compact()) rhs32<true>(); else rhs32<false>();
}
template<> float SolverState<float>::sweep_lexicographic() {
  if (collect_residual_) return operator_.compact() ? lex32<true,true>() : lex32<false,true>();
  return operator_.compact() ? lex32<true,false>() : lex32<false,false>();
}
template<> float SolverState<float>::sweep_red_black() {
  if (collect_residual_) return operator_.compact() ? rb32<true,true>() : rb32<false,true>();
  return operator_.compact() ? rb32<true,false>() : rb32<false,false>();
}
template<> float SolverState<float>::corrected_face(int component,int i,int j,int k) const {
  const auto *WGD = &*fields_;
  const auto icell_cent = domain.cell(i,j,k), icell_face = domain.face(i,j,k);
  const auto a = operator_.stencil(icell_cent,k);
  if (component == 0) return WGD->u0[icell_face]
                             + (1.0f / (2.0f * (float)pow(alpha1, 2.0))) * a.f * domain.dx()
                                 * (lambda[icell_cent] - lambda[icell_cent - 1]);
  if (component == 1) return WGD->v0[icell_face]
                             + (1.0f / (2.0f * (float)pow(alpha1, 2.0))) * a.h * domain.dy()
                                 * (lambda[icell_cent] - lambda[domain.cellAdd(icell_cent, 0, -1, 0)]);
  return WGD->w0[icell_face]
                             + (1.0f / (2.0f * (float)pow(alpha2, 2.0))) * a.n * domain.dz_array[k]
                                 * (lambda[icell_cent] - lambda[domain.cellAdd(icell_cent, 0, 0, -1)]);
}
}
