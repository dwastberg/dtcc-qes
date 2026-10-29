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

/** @file LocalMixingSerial.cpp */

#include "LocalMixingSerial.h"
#include "WINDSInputData.h"
#include "WINDSGeneralData.h"
#include "util/QESLog.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

void LocalMixingSerial::defineMixingLength(const WINDSInputData *WID, WINDSGeneralData *WGD)
{
  const auto &d = WGD->domain;
  const int cx = static_cast<int>(d.x.size());
  const int cy = static_cast<int>(d.y.size());
  const int cz = static_cast<int>(d.z.size());
  const auto cell = [=](int i, int j, int k) { return i + cx * (j + cy * k); };
  const auto solid = [&](int i, int j, int k) {
    const int flag = WGD->icellflag[cell(i,j,k)];
    return flag == 0 || flag == 2;
  };
  const double ground = *std::min_element(WGD->terrain.begin(), WGD->terrain.end());

  // Seed the same physical cells as the height method, including horizontal
  // boundary cells. Ghost and uncomputed top cells are left untouched.
  double highest = ground;
  for (int k = 1; k < cz - 1; ++k)
    for (int j = 0; j < cy; ++j)
      for (int i = 0; i < cx; ++i) {
        if (!solid(i,j,k))
          WGD->mixingLengths[cell(i,j,k)] = std::max(0.0,
            static_cast<double>(d.z[k]) - WGD->terrain[i + cx * j]);
      }
  // Include the last physical solid layer when finding the influence height.
  // The ground ghost layer has top z=0 and is not an above-ground object.
  for (int k = 1; k < cz; ++k)
    for (int j = 0; j < cy; ++j)
      for (int i = 0; i < cx; ++i)
        if (solid(i,j,k)) highest = std::max(highest, static_cast<double>(d.z_face[k+1]));

  const double height = highest - ground;
  if (height > 0) {
    const double transition_start = ground + 3.0 * height;
    const double transition_end = ground + 3.6 * height;
    const double transition_width = transition_end - transition_start;
    // The interval is in metres, independent of layer count or spacing. A flat
    // empty domain bypasses this block, so it cannot create a zero denominator.
    // Above transition_end, the seed is the final answer. Below it, a distance
    // greater than radius cannot improve any computed cell's height seed.
    double radius = 0;
    for (int k = 1; k < cz - 1 && d.z[k] < transition_end; ++k)
      radius = std::max(radius, static_cast<double>(d.z[k]) - ground);

    // QES uses uniform horizontal cells, with centre coordinates in x/y and
    // explicit (possibly nonuniform) vertical faces. Keep face coordinates in
    // double precision instead of rounding each distance update to float.
    const auto faces = [](const std::vector<float> &centres, double spacing) {
      std::vector<double> result(centres.size() + 1);
      result.front() = centres.front() - 0.5 * spacing;
      for (std::size_t n = 1; n < centres.size(); ++n)
        result[n] = 0.5 * (static_cast<double>(centres[n-1]) + centres[n]);
      result.back() = centres.back() + 0.5 * spacing;
      return result;
    };
    const auto [dx,dy,dz] = d.getDomainSize();
    const auto xf = faces(d.x, dx), yf = faces(d.y, dy);
    using Point = std::array<double,3>;
    const auto gap = [](double coordinate, double lower, double upper) {
      return std::max({lower - coordinate, 0.0, coordinate - upper});
    };
    // All ranges are half open and restricted to turbulence's computed cells:
    // 1..cx-2, 1..cy-2, 1..cz-2. Source-neighbour bounds below are independent.
    const auto range = [](const std::vector<float> &axis, double lower, double upper) {
      const auto first = axis.begin() + 1, last = axis.end() - 1;
      return std::array<int,2>{
        static_cast<int>(std::lower_bound(first,last,lower) - axis.begin()),
        static_cast<int>(std::upper_bound(first,last,upper) - axis.begin())};
    };
    const auto apply_face = [&](const Point &lower, const Point &upper) {
      // A horizontal face at/below the lowest terrain cannot shorten the
      // vertical terrain seed. This also avoids propagating every flat-ground
      // face across the domain.
      if (lower[2] == upper[2] && upper[2] <= ground) return;
      const auto kr = range(d.z, lower[2] - radius,
                            std::min(upper[2] + radius, transition_end));
      for (int k = kr[0]; k < kr[1]; ++k) {
        if (d.z[k] >= transition_end) continue;
        const double gz = gap(d.z[k], lower[2], upper[2]);
        // Every local height seed is <= z - minimum terrain. Prune only when
        // a face cannot beat that bound; no index-based influence cones remain.
        const double reach2 = std::pow(static_cast<double>(d.z[k]) - ground, 2) - gz * gz;
        if (reach2 <= 0) continue;
        const double reach = std::sqrt(reach2);
        const auto jr = range(d.y, lower[1] - reach, upper[1] + reach);
        for (int j = jr[0]; j < jr[1]; ++j) {
          const double gy = gap(d.y[j], lower[1], upper[1]);
          const double xreach2 = reach2 - gy * gy;
          if (xreach2 <= 0) continue;
          const double xreach = std::sqrt(xreach2);
          const auto ir = range(d.x, lower[0] - xreach, upper[0] + xreach);
          for (int i = ir[0]; i < ir[1]; ++i) {
            if (solid(i,j,k)) continue;
            const double gx = gap(d.x[i], lower[0], upper[0]);
            const double distance2 = gx * gx + gy * gy + gz * gz;
            double &length = WGD->mixingLengths[cell(i,j,k)];
            if (distance2 < length * length) length = std::sqrt(distance2);
          }
        }
      }
    };

    // Each exposed solid/fluid interface is an axis-aligned rectangle. Use the
    // same distance update for all six orientations, including undersides.
    // Neighbours must exist in the actual cell arrays; domain edges are not
    // solid walls. Ground-ghost cells can supply their upward interface only.
    for (int k = 0; k < cz; ++k)
      for (int j = 0; j < cy; ++j)
        for (int i = 0; i < cx; ++i) {
          if (!solid(i,j,k)) continue;
          Point lower{xf[i], yf[j], d.z_face[k]};
          Point upper{xf[i+1], yf[j+1], d.z_face[k+1]};
          for (int axis = 0; axis < 3; ++axis)
            for (int sign : {-1, 1}) {
              std::array<int,3> neighbour{i,j,k};
              neighbour[axis] += sign;
              if (neighbour[0] < 0 || neighbour[0] >= cx
                  || neighbour[1] < 0 || neighbour[1] >= cy
                  || neighbour[2] < 1 || neighbour[2] >= cz
                  || solid(neighbour[0],neighbour[1],neighbour[2])) continue;
              auto face_lower = lower, face_upper = upper;
              face_lower[axis] = face_upper[axis] = sign < 0 ? lower[axis] : upper[axis];
              apply_face(face_lower, face_upper);
            }
        }

    // Blend the minimum distance with each cell's terrain-relative height,
    // using its physical z coordinate. This is a model transition, not an
    // exact nearest-wall distance in the transition band or far field.
    if (transition_width > 0)
      for (int k = 1; k < cz - 1; ++k) {
        if (d.z[k] <= transition_start || d.z[k] >= transition_end) continue;
        const double weight = (d.z[k] - transition_start) / transition_width;
        for (int j = 1; j < cy - 1; ++j)
          for (int i = 1; i < cx - 1; ++i) {
            if (solid(i,j,k)) continue;
            const double seed = std::max(0.0,
              static_cast<double>(d.z[k]) - WGD->terrain[i + cx * j]);
            double &length = WGD->mixingLengths[cell(i,j,k)];
            length = std::min(seed, length + weight * (seed - length));
          }
      }
    qes::log::info() << "[MixLength] \t serial grid-face distances; transition "
                     << transition_start << " to " << transition_end << " m" << std::endl;
  }

  if (WID->turbParams->save2file) saveMixingLength(WID, WGD);
}
