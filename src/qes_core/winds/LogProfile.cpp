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
 * @file LogProfile.cpp
 * @brief Single-sensor logarithmic inflow profile.
 *
 * Extracted from WindProfilerSensorType::sensorsProfiles (site_blayer_flag 1)
 * and singleSensorInterpolation. Expressions, operand types and includes are
 * unchanged, so the initial field stays bitwise identical.
 */

#include "util/QESLog.h"
#include <math.h>
#include <iostream>
#include <fstream>
#include <cstdlib>
#include <vector>
#include <chrono>
#include <limits>

#include "LogProfile.h"
#include "WINDSGeneralData.h"


void applyLogProfile(const InflowCondition &inflow, WINDSGeneralData *WGD)
{
  const InflowCondition *ts = &inflow;
  const float vk = 0.4;// Von Karman's constant
  float psi;// unused: psi_first
  float x_temp;
  float u_star = 0.0;
  const float asl_percent = 0.05;

  auto [nx, ny, nz] = WGD->domain.getDomainCellNum();
  auto [dx, dy, dz] = WGD->domain.getDomainSize();

  float z_terrain;

  // One sensor with one time step.
  const int num_sites = 1;
  const int idx = 0;

  std::vector<float> u_prof(num_sites * nz, 0.0);
  std::vector<float> v_prof(num_sites * nz, 0.0);
  std::vector<int> site_id(num_sites, 0);
  std::vector<float> abl_height;

  std::vector<int> site_i(num_sites, 0);
  std::vector<int> site_j(num_sites, 0);
  std::vector<float> site_theta(num_sites, 0.0);

  site_theta[idx] = (270.0 - ts->site_wind_dir) * M_PI / 180.0;
  site_i[idx] = ts->site_xcoord / dx;
  site_j[idx] = ts->site_ycoord / dy;
  site_id[idx] = site_i[idx] + site_j[idx] * nx;

  z_terrain = WGD->domain.z_face[WGD->terrain_face_id[site_id[idx]]];

  if (ts->site_one_overL > 0.0) {
    // Stable boundary layer
    abl_height.push_back(200);
  } else if (ts->site_one_overL < 0.0) {
    // Unstable boundary layer
    abl_height.push_back(1000);
  } else {
    // Neutral boundary layer
    abl_height.push_back(100);
  }

  // Logarithmic velocity profile
  for (auto k = WGD->terrain_face_id[site_id[idx]]; k < nz - 1; ++k) {
    if (k == WGD->terrain_face_id[site_id[idx]]) {
      if (ts->site_z_ref * ts->site_one_overL >= 0) {// Stable and Neutral BL
        psi = 4.7 * ts->site_z_ref * ts->site_one_overL;
      } else {// Unstable BL
        x_temp = pow((1.0 - 15.0 * ts->site_z_ref * ts->site_one_overL), 0.25);
        psi = -2.0 * log(0.5 * (1.0 + x_temp)) - log(0.5 * (1.0 + pow(x_temp, 2.0))) + 2.0 * atan(x_temp) - 0.5 * M_PI;
      }
      u_star = ts->site_U_ref * vk / (log((ts->site_z_ref + ts->site_z0) / ts->site_z0) + psi);
    }

    if ((WGD->domain.z[k] - z_terrain) * ts->site_one_overL >= 0) {// Stable and Neutral BL
      psi = 4.7 * (WGD->domain.z[k] - z_terrain) * ts->site_one_overL;
    } else {// Unstable BL
      x_temp = pow((1.0 - 15.0 * (WGD->domain.z[k] - z_terrain) * ts->site_one_overL), 0.25);
      psi = -2.0 * log(0.5 * (1.0 + x_temp)) - log(0.5 * (1.0 + pow(x_temp, 2.0))) + 2.0 * atan(x_temp) - 0.5 * M_PI;
    }
    u_prof[idx * nz + k] = (cos(site_theta[idx]) * u_star / vk) * (log(((WGD->domain.z[k] - z_terrain) + ts->site_z0) / ts->site_z0) + psi);
    v_prof[idx * nz + k] = (sin(site_theta[idx]) * u_star / vk) * (log(((WGD->domain.z[k] - z_terrain) + ts->site_z0) / ts->site_z0) + psi);
    // Free convection limit
    if (abs(u_star) >= 2 * ts->site_U_ref) {
      u_prof[idx * nz + k] = (cos(site_theta[idx]) * ts->site_U_ref);
      v_prof[idx * nz + k] = (sin(site_theta[idx]) * ts->site_U_ref);
    }
  }

  // A single sensor's profile applies over the whole domain.

  float surf_layer_height;// Surface layer height of the atmospheric boundary layer (ABL)

  for (auto k = 1; k < nz - 1; ++k) {
    // Set the modified k-index (sensor)
    int k_mod_sens = k + WGD->terrain_face_id[site_id[0]] - 1;
    for (auto j = 0; j < ny; ++j) {
      for (auto i = 0; i < nx; ++i) {

        int id = WGD->domain.face2d(i, j);// Index in horizontal surface
        int k_mod(0);
        // If height added to top of terrain is still inside QES domain
        if (k + WGD->terrain_face_id[id] - 1 < nz) {
          // Set the modified k-index (current location)
          k_mod = k + WGD->terrain_face_id[id] - 1;
        } else {
          continue;
        }
        // Lineralized index for cell faced values
        int icell_face = WGD->domain.face(i, j, k_mod);
        // If the height difference between the terrain at the curent cell and sensor location is less than ABL height
        if (abs(WGD->domain.z[WGD->terrain_face_id[id]] - WGD->domain.z[WGD->terrain_face_id[site_id[0]]]) > abl_height[0]) {
          surf_layer_height = asl_percent * abl_height[0];
        } else {
          surf_layer_height = asl_percent * (2 * abl_height[0] - (WGD->domain.z[WGD->terrain_face_id[id]] - WGD->domain.z[WGD->terrain_face_id[site_id[0]]]));
        }
        // If height (above ground) is less than or equal to ASL height
        if (WGD->domain.z[k] <= surf_layer_height) {
          WGD->u0[icell_face] = u_prof[k_mod_sens];
          WGD->v0[icell_face] = v_prof[k_mod_sens];
        }// If sum of z index and the terrain index at the sensor location is outside the domain
        else if (k + WGD->terrain_face_id[site_id[0]] - 1 > nz - 2) {
          WGD->u0[icell_face] = u_prof[nz - 2];
          WGD->v0[icell_face] = v_prof[nz - 2];
        }// If height (above ground) is greater than ASL height and modified index is inside the domain
        else if (WGD->domain.z[k] > surf_layer_height && k_mod_sens < nz) {
          WGD->u0[icell_face] = u_prof[k_mod_sens];
          WGD->v0[icell_face] = v_prof[k_mod_sens];
        }

        WGD->w0[icell_face] = 0.0;// Perpendicular wind direction
      }
    }
  }

  return;
}
