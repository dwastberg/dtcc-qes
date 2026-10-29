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


/**
 * @file Wall.cpp
 * @brief :brief here:
 *
 * :long desc here if necessary:
 */

#include "util/QESLog.h"
#include "Wall.h"

#include "WINDSGeneralData.h"


void Wall::defineWalls(WINDSGeneralData *WGD)
{
  auto [nx, ny, nz] = WGD->domain.getDomainCellNum();

  for (auto k = 1; k < nz - 1; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        if (WGD->e[icell_cent] < 0.05) {
          WGD->e[icell_cent] = 0.0;
        }
        if (WGD->f[icell_cent] < 0.05) {
          WGD->f[icell_cent] = 0.0;
        }
        if (WGD->g[icell_cent] < 0.05) {
          WGD->g[icell_cent] = 0.0;
        }
        if (WGD->h[icell_cent] < 0.05) {
          WGD->h[icell_cent] = 0.0;
        }
        if (WGD->m[icell_cent] < 0.05) {
          WGD->m[icell_cent] = 0.0;
        }
        if (WGD->n[icell_cent] < 0.05) {
          WGD->n[icell_cent] = 0.0;
        }

        if (WGD->e[icell_cent] > 1.0) {
          WGD->e[icell_cent] = 1.0;
        }
        if (WGD->f[icell_cent] > 1.0) {
          WGD->f[icell_cent] = 1.0;
        }
        if (WGD->g[icell_cent] > 1.0) {
          WGD->g[icell_cent] = 1.0;
        }
        if (WGD->h[icell_cent] > 1.0) {
          WGD->h[icell_cent] = 1.0;
        }
        if (WGD->m[icell_cent] > 1.0) {
          WGD->m[icell_cent] = 1.0;
        }
        if (WGD->n[icell_cent] > 1.0) {
          WGD->n[icell_cent] = 1.0;
        }
      }
    }
  }

  for (auto k = 1; k < nz - 1; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        if ((WGD->icellflag[icell_cent] == 7 || WGD->icellflag[icell_cent] == 0) && WGD->building_volume_frac[icell_cent] <= 0.1) {
          WGD->icellflag[icell_cent] = 0;
          WGD->e[icell_cent] = 1.0;
          WGD->f[icell_cent] = 1.0;
          WGD->g[icell_cent] = 1.0;
          WGD->h[icell_cent] = 1.0;
          WGD->m[icell_cent] = 1.0;
          WGD->n[icell_cent] = 1.0;
        }
      }
    }
  }

  for (auto k = 1; k < nz - 1; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        if (WGD->e[icell_cent] == 0.0 && WGD->f[icell_cent] == 0.0 && WGD->g[icell_cent] == 0.0
            && WGD->h[icell_cent] == 0.0 && WGD->m[icell_cent] == 0.0 && WGD->n[icell_cent] == 0.0 && WGD->icellflag[icell_cent] == 7) {
          WGD->icellflag[icell_cent] = 0;
          WGD->e[icell_cent] = 1.0;
          WGD->f[icell_cent] = 1.0;
          WGD->g[icell_cent] = 1.0;
          WGD->h[icell_cent] = 1.0;
          WGD->m[icell_cent] = 1.0;
          WGD->n[icell_cent] = 1.0;
        }
      }
    }
  }

  for (auto k = 1; k < nz - 2; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        if (WGD->icellflag[icell_cent] != 0 && WGD->icellflag[icell_cent] != 2) {

          // Wall below
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 2) {
            WGD->n[icell_cent] = 0.0;
          }
          // Wall above
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 2) {
            WGD->m[icell_cent] = 0.0;
          }
          // Wall in back
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 2) {
            if (i > 0) {
              WGD->f[icell_cent] = 0.0;
            }
          }
          // Wall in front
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 2) {
            WGD->e[icell_cent] = 0.0;
          }
          // Wall on right
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 2) {
            if (j > 0) {
              WGD->h[icell_cent] = 0.0;
            }
          }
          // Wall on left
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 2) {
            WGD->g[icell_cent] = 0.0;
          }
        }

        if (WGD->icellflag[icell_cent] == 7) {
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 8) {
            WGD->m[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] = WGD->n[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 8) {
            WGD->n[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] = WGD->m[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 8) {
            if (i > 0) {
              WGD->f[icell_cent] = WGD->e[WGD->domain.cellAdd(icell_cent, -1, 0, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 8) {
            WGD->e[icell_cent] = WGD->f[WGD->domain.cellAdd(icell_cent, +1, 0, 0)];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 8) {
            if (j > 0) {
              WGD->h[icell_cent] = WGD->g[WGD->domain.cellAdd(icell_cent, 0, -1, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 8) {
            WGD->g[icell_cent] = WGD->h[WGD->domain.cellAdd(icell_cent, 0, +1, 0)];
          }
        }

        if (WGD->icellflag[icell_cent] == 8) {
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 8) {
            WGD->m[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] = WGD->n[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 8) {
            WGD->n[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] = WGD->m[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 8) {
            if (i > 0) {
              WGD->f[icell_cent] = WGD->e[WGD->domain.cellAdd(icell_cent, -1, 0, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 8) {
            WGD->e[icell_cent] = WGD->f[WGD->domain.cellAdd(icell_cent, +1, 0, 0)];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 8) {
            if (j > 0) {
              WGD->h[icell_cent] = WGD->g[WGD->domain.cellAdd(icell_cent, 0, -1, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 8) {
            WGD->g[icell_cent] = WGD->h[WGD->domain.cellAdd(icell_cent, 0, +1, 0)];
          }
        }

        if (WGD->icellflag[icell_cent] == 1) {
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 8) {
            WGD->m[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] = WGD->n[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 8) {
            WGD->n[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] = WGD->m[icell_cent];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 8) {
            if (i > 0) {
              WGD->f[icell_cent] = WGD->e[WGD->domain.cellAdd(icell_cent, -1, 0, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 8) {
            WGD->e[icell_cent] = WGD->f[WGD->domain.cellAdd(icell_cent, +1, 0, 0)];
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 8) {
            if (j > 0) {
              WGD->h[icell_cent] = WGD->g[WGD->domain.cellAdd(icell_cent, 0, -1, 0)];
            }
          }

          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 7 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 8) {
            WGD->g[icell_cent] = WGD->h[WGD->domain.cellAdd(icell_cent, 0, +1, 0)];
          }
        }
      }
    }
  }

  for (auto k = 1; k < nz - 1; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        if (WGD->e[icell_cent] == 0.0 && WGD->f[icell_cent] == 0.0 && WGD->g[icell_cent] == 0.0
            && WGD->h[icell_cent] == 0.0 && WGD->m[icell_cent] == 0.0 && WGD->n[icell_cent] == 0.0
            && (WGD->icellflag[icell_cent] == 7 || WGD->icellflag[icell_cent] == 0)) {
          WGD->icellflag[icell_cent] = 0;
          WGD->e[icell_cent] = 1.0;
          WGD->f[icell_cent] = 1.0;
          WGD->g[icell_cent] = 1.0;
          WGD->h[icell_cent] = 1.0;
          WGD->m[icell_cent] = 1.0;
          WGD->n[icell_cent] = 1.0;
        }

        if (WGD->e[icell_cent] == 0.0 && WGD->f[icell_cent] == 0.0 && WGD->g[icell_cent] == 0.0
            && WGD->h[icell_cent] == 0.0 && WGD->m[icell_cent] == 0.0 && WGD->n[icell_cent] == 0.0
            && (WGD->icellflag[icell_cent] == 8 || WGD->icellflag[icell_cent] == 2)) {
          WGD->icellflag[icell_cent] = 2;
          WGD->e[icell_cent] = 1.0;
          WGD->f[icell_cent] = 1.0;
          WGD->g[icell_cent] = 1.0;
          WGD->h[icell_cent] = 1.0;
          WGD->m[icell_cent] = 1.0;
          WGD->n[icell_cent] = 1.0;
        }
      }
    }
  }

  for (auto k = 1; k < nz - 2; k++) {
    for (auto i = 0; i < nx - 1; i++) {
      for (auto j = 0; j < ny - 1; j++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        long icell_face = WGD->domain.face(i, j, k);
        if (WGD->icellflag[icell_cent] != 0 && WGD->icellflag[icell_cent] != 2) {

          // Wall below
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, -1)] == 2) {
            WGD->n[icell_cent] = 0.0;
          }
          // Wall above
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, 0, +1)] == 2) {
            WGD->m[icell_cent] = 0.0;
          }
          // Wall in back
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, -1, 0, 0)] == 2) {
            if (i > 0) {
              WGD->f[icell_cent] = 0.0;
            }
          }
          // Wall in front
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, +1, 0, 0)] == 2) {
            WGD->e[icell_cent] = 0.0;
          }
          // Wall on right
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, -1, 0)] == 2) {
            if (j > 0) {
              WGD->h[icell_cent] = 0.0;
            }
          }
          // Wall on left
          if (WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 0 || WGD->icellflag[WGD->domain.cellAdd(icell_cent, 0, +1, 0)] == 2) {
            WGD->g[icell_cent] = 0.0;
          }
        }

      }
    }
  }
}


void Wall::setVelocityZero(WINDSGeneralData *WGD)
{
  auto [nx, ny, nz] = WGD->domain.getDomainCellNum();
  for (auto k = 0; k < nz - 1; k++) {
    for (auto j = 1; j < ny - 1; j++) {
      for (auto i = 1; i < nx - 1; i++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        long icell_face = WGD->domain.face(i, j, k);
        if (WGD->icellflag[icell_cent] == 0 || WGD->icellflag[icell_cent] == 2) {
          WGD->u0[icell_face] = 0.0;// Set velocity inside the building to zero
          WGD->u0[icell_face + 1] = 0.0;
          WGD->v0[icell_face] = 0.0;// Set velocity inside the building to zero
          WGD->v0[icell_face + nx] = 0.0;
          WGD->w0[icell_face] = 0.0;// Set velocity inside the building to zero
          WGD->w0[icell_face + nx * ny] = 0.0;
        }
      }
    }
  }
}


void Wall::solverCoefficients(WINDSGeneralData *WGD)
{
  // New boundary condition implementation
  // This needs to be done only once
  auto [nx, ny, nz] = WGD->domain.getDomainCellNum();
  auto [dx, dy, dz] = WGD->domain.getDomainSize();
  for (auto k = 1; k < nz - 2; k++) {
    for (auto j = 0; j < ny - 1; j++) {
      for (auto i = 0; i < nx - 1; i++) {
        long icell_cent = WGD->domain.cell(i, j, k);
        WGD->e[icell_cent] = WGD->e[icell_cent] / (dx * dx);
        WGD->f[icell_cent] = WGD->f[icell_cent] / (dx * dx);
        WGD->g[icell_cent] = WGD->g[icell_cent] / (dy * dy);
        WGD->h[icell_cent] = WGD->h[icell_cent] / (dy * dy);
        WGD->m[icell_cent] = WGD->m[icell_cent] / (WGD->domain.dz_array[k] * 0.5f * (WGD->domain.dz_array[k] + WGD->domain.dz_array[k + 1]));
        WGD->n[icell_cent] = WGD->n[icell_cent] / (WGD->domain.dz_array[k] * 0.5f * (WGD->domain.dz_array[k] + WGD->domain.dz_array[k - 1]));
      }
    }
  }
}
