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

/** @file Solver_CPU_RB.cpp */


#include "util/QESLog.h"
#include "Solver_CPU_RB.h"

/** :document this:
 * Start by writing a one sentence description here
 *
 * Complete by continuting to write implementation details here.
 * (remove :document this: tag when done)
 */
SolveDiagnostics Solver_CPU_RB::solve(WINDSGeneralData *WGD, const int &itermax)
{
  validateSolve(WGD, itermax);

  auto startOfSolveMethod = std::chrono::high_resolution_clock::now();// Start recording execution time

  /***************************************************************
   *********   Divergence of the initial velocity field   ********
   ***************************************************************/
  long icell_face;// cell-face index
  long icell_cent;// cell-centered index

  // R.resize(WGD->numcell_cent, 0.0);
  // lambda.resize(WGD->numcell_cent, 0.0);
  // lambda_old.resize(WGD->numcell_cent, 0.0);

  auto startSolveSection = std::chrono::high_resolution_clock::now();
#pragma omp parallel private(icell_cent, icell_face) default(none) shared(WGD, R)
  {
#pragma omp for
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 0; j < domain.ny() - 1; ++j) {
        for (int i = 0; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          // icell_face = i + j * WGD->nx + k * WGD->nx * WGD->ny;
          icell_face = domain.face(i, j, k);
          // Calculate divergence of initial velocity field
        // m/n already include 1/(dz * centre separation). Cancel only the
        // centre separation here, retaining 1/dz for the vertical divergence.
        R[icell_cent] = (-2.0f * pow(alpha1, 2.0))
                          * (((WGD->e[icell_cent] * WGD->u0[domain.faceAdd(icell_face, 1, 0, 0)]
                               - WGD->f[icell_cent] * WGD->u0[icell_face])
                              * domain.dx())
                             + ((WGD->g[icell_cent] * WGD->v0[domain.faceAdd(icell_face, 0, 1, 0)]
                                 - WGD->h[icell_cent] * WGD->v0[icell_face])
                                * domain.dy())
                             + ((WGD->m[icell_cent] * 0.5 * (domain.dz_array[k] + domain.dz_array[k + 1])
                                   * WGD->w0[domain.faceAdd(icell_face, 0, 0, 1)]
                                 - WGD->n[icell_cent] * 0.5f * (domain.dz_array[k] + domain.dz_array[k - 1])
                                     * WGD->w0[icell_face])));
        }
      }
    }
  }
  // INSERT CANOPY CODE

  /***************************************************************
   **********************   SOR Solver   *************************
   ***************************************************************/

  int iter = 0;
  float error;
  float max_error = 1.0;
  // int i_max, j_max, k_max;

  qes::log::info() << "[Solver]\t Running Red/Black CPU Solver ..." << std::endl;

  // Measure convergence at least once, even when the tolerance exceeds 1.
  while (iter < itermax && (iter == 0 || max_error > tol)) {
    max_error = 0.0f;
    int nonfinite = 0;

// Save previous iteration values for error calculation
#pragma omp parallel private(icell_cent, icell_face, error) default(none) shared(WGD, lambda, lambda_old, R) reduction(max : max_error) reduction(| : nonfinite)
    {
#pragma omp for
      for (auto k = 0u; k < lambda.size(); ++k) {
        lambda_old[k] = lambda[k];
      }
      // end of omp for (with implicit barrier)


      // main SOR formulation loop

      // Red nodes pass
#pragma omp for
      for (int k = 1; k < domain.nz() - 2; ++k) {
        for (int j = 1; j < domain.ny() - 2; ++j) {
          for (int i = 1; i < domain.nx() - 2; ++i) {

            if (((i + j + k) % 2) == 0) {
              // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
              icell_cent = domain.cell(i, j, k);
              lambda[icell_cent] = (omega / (WGD->e[icell_cent] + WGD->f[icell_cent] + WGD->g[icell_cent] + WGD->h[icell_cent] + WGD->m[icell_cent] + WGD->n[icell_cent]))
                                     * (WGD->e[icell_cent] * lambda[domain.cellAdd(icell_cent, 1, 0, 0)]
                                        + WGD->f[icell_cent] * lambda[domain.cellAdd(icell_cent, -1, 0, 0)]
                                        + WGD->g[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 1, 0)]
                                        + WGD->h[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, -1, 0)]
                                        + WGD->m[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 0, 1)]
                                        + WGD->n[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 0, -1)] - R[icell_cent])
                                   + (1.0f - omega) * lambda[icell_cent];// SOR formulation
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
              lambda[icell_cent] = (omega / (WGD->e[icell_cent] + WGD->f[icell_cent] + WGD->g[icell_cent] + WGD->h[icell_cent] + WGD->m[icell_cent] + WGD->n[icell_cent]))
                                     * (WGD->e[icell_cent] * lambda[domain.cellAdd(icell_cent, 1, 0, 0)]
                                        + WGD->f[icell_cent] * lambda[domain.cellAdd(icell_cent, -1, 0, 0)]
                                        + WGD->g[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 1, 0)]
                                        + WGD->h[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, -1, 0)]
                                        + WGD->m[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 0, 1)]
                                        + WGD->n[icell_cent] * lambda[domain.cellAdd(icell_cent, 0, 0, -1)] - R[icell_cent])
                                   + (1.0f - omega) * lambda[icell_cent];// SOR formulation
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

      // Error calculation
#pragma omp for
      for (int k = 1; k < domain.nz() - 1; ++k) {
        for (int j = 0; j < domain.ny() - 1; ++j) {
          for (int i = 0; i < domain.nx() - 1; ++i) {
            // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);// Lineralized index for cell centered values
            icell_cent = domain.cell(i, j, k);
            error = fabs(lambda[icell_cent] - lambda_old[icell_cent]);
            if (!std::isfinite(error)) nonfinite = 1;
            if (error > max_error) {
              max_error = error;
            }
          }
        }
      }
      // end of omp for (with implicit barrier)
    }
    // end of omp parallel workshare
    // Exceptions must leave the parallel region on the calling thread.
    if (nonfinite)
      throw qes::RuntimeError("Non-finite Lagrange multiplier change during solve");
    iter += 1;
  }

  // qes::log::info() << "Solved!\n";

  // qes::log::info() << "Number of iterations:" << iter << "\n";// Print the number of iterations
  // qes::log::info() << "Error:" << max_error << "\n";
  // qes::log::info() << "tol:" << tol << "\n";


  const auto solid = [&](int i, int j, int k) {
    if (i < 0 || i >= domain.nx() - 1 || j < 0 || j >= domain.ny() - 1
        || k < 1 || k >= domain.nz() - 1) return false;
    const auto flag = WGD->icellflag[domain.cell(i, j, k)];
    return flag == 0 || flag == 2;
  };
#pragma omp parallel private(icell_cent, icell_face) default(none) shared(WGD, lambda, solid)
  {
    // Update the velocity field using Euler-Lagrange equations
#pragma omp for
    for (auto k = 0u; k < WGD->u.size(); ++k) {
      WGD->u[k] = WGD->u0[k];
    }
    // end of omp for (with implicit barrier)
#pragma omp for
    for (auto k = 0u; k < WGD->v.size(); ++k) {
      WGD->v[k] = WGD->v0[k];
    }
    // end of omp for (with implicit barrier)
#pragma omp for
    for (auto k = 0u; k < WGD->w.size(); ++k) {
      WGD->w[k] = WGD->w0[k];
    }
    // end of omp for (with implicit barrier)

    // Update the velocity field using Euler equations
#pragma omp for
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 1; j < domain.ny() - 1; ++j) {
        for (int i = 1; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          // icell_face = i + j * WGD->nx + k * WGD->nx * WGD->ny;
          icell_face = domain.face(i, j, k);
          WGD->u[icell_face] = WGD->u0[icell_face]
                               + (1.0f / (2.0f * (float)pow(alpha1, 2.0))) * WGD->f[icell_cent] * domain.dx()
                                   * (lambda[icell_cent] - lambda[icell_cent - 1]);
        }
      }
    }
    // end of omp for (with implicit barrier)

#pragma omp for
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 1; j < domain.ny() - 1; ++j) {
        for (int i = 1; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          // icell_face = i + j * WGD->nx + k * WGD->nx * WGD->ny;
          icell_face = domain.face(i, j, k);
          WGD->v[icell_face] = WGD->v0[icell_face]
                               + (1.0f / (2.0f * (float)pow(alpha1, 2.0))) * WGD->h[icell_cent] * domain.dy()
                                   * (lambda[icell_cent] - lambda[domain.cellAdd(icell_cent, 0, -1, 0)]);
        }
      }
    }
    // end of omp for (with implicit barrier)

#pragma omp for
    for (int k = 1; k < domain.nz() - 2; ++k) {
      for (int j = 1; j < domain.ny() - 1; ++j) {
        for (int i = 1; i < domain.nx() - 1; ++i) {
          // icell_cent = i + j * (WGD->nx - 1) + k * (WGD->nx - 1) * (WGD->ny - 1);
          icell_cent = domain.cell(i, j, k);
          // icell_face = i + j * WGD->nx + k * WGD->nx * WGD->ny;
          icell_face = domain.face(i, j, k);
          WGD->w[icell_face] = WGD->w0[icell_face]
                               + (1.0f / (2.0f * (float)pow(alpha2, 2.0))) * WGD->n[icell_cent] * domain.dz_array[k]
                                   * (lambda[icell_cent] - lambda[domain.cellAdd(icell_cent, 0, 0, -1)]);
        }
      }
    }
    // end of omp for (with implicit barrier)

#pragma omp for
    // Each face belongs to one iteration. Visiting solid cells and writing
    // both faces would race on the w face shared by adjacent k slabs.
    for (int k = 1; k < domain.nz(); ++k) {
      for (int j = 0; j < domain.ny(); ++j) {
        for (int i = 0; i < domain.nx(); ++i) {
          icell_face = domain.face(i, j, k);
          if (solid(i, j, k) || solid(i - 1, j, k))
            WGD->u[icell_face] = 0;
          if (solid(i, j, k) || solid(i, j - 1, k))
            WGD->v[icell_face] = 0;
          if (solid(i, j, k) || solid(i, j, k - 1))
            WGD->w[icell_face] = 0;
        }
      }
    }
    // end of omp for (with implicit barrier)
  }
  auto finish = std::chrono::high_resolution_clock::now();// Finish recording execution time
  std::chrono::duration<float> elapsedTotal = finish - startOfSolveMethod;
  std::chrono::duration<float> elapsedSolve = finish - startSolveSection;
  qes::log::info() << "\t\t elapsed time: " << elapsedTotal.count() << " s\n";// Print out elapsed execution time
  // qes::log::info() << "Elapsed solve time: " << elapsedSolve.count() << " s\n";// Print out elapsed execution time
  return {iter, max_error, tol, std::isfinite(max_error) && max_error <= tol};
}
