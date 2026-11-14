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
 * @file PolyBuilding.cpp
 * @brief Designed for the general building shape (polygons).
 *
 * It's an inheritance of the building class (has all the features defined in that class).
 * In this class, first, the polygon buildings will be defined and then different
 * parameterizations related to each building will be applied.
 *
 * @sa Building
 */

#include "PolyBuilding.h"
#include "FacadeRuns.h"
#include <algorithm>
#include <limits>
#include <utility>

// These take care of the circular reference
#include "WINDSGeneralData.h"

namespace {
// A point strictly inside the footprint (outer ring minus holes) for any simple
// polygon, concave or not. Cuts the footprint with a horizontal line halfway
// between the two vertex y-values that bracket yHint, so the line passes through
// no vertex, and returns the midpoint of the widest interior span.
std::pair<double, double> scanlineInteriorPoint(const std::vector<polyVert> &v,
                                                const std::vector<std::size_t> &rings,
                                                double xHint, double yHint)
{
  std::vector<double> ys;
  ys.reserve(v.size());
  for (const auto &p : v) ys.push_back(p.y_poly);
  std::sort(ys.begin(), ys.end());
  ys.erase(std::unique(ys.begin(), ys.end()), ys.end());
  if (ys.size() < 2) return {xHint, yHint};// zero-area footprint
  const auto hi = std::clamp(std::upper_bound(ys.begin(), ys.end(), yHint),
                             ys.begin() + 1, ys.end() - 1);
  const double y = 0.5 * (*(hi - 1) + *hi);

  std::vector<double> xs;// crossings of every ring, even-odd
  for (std::size_t r = 1; r < rings.size(); ++r)
    for (std::size_t e = rings[r - 1]; e + 1 < rings[r]; ++e) {
      const double ax = v[e].x_poly, ay = v[e].y_poly;
      const double bx = v[e + 1].x_poly, by = v[e + 1].y_poly;
      if ((ay < y) != (by < y))
        xs.push_back(ax + (y - ay) / (by - ay) * (bx - ax));
    }
  std::sort(xs.begin(), xs.end());
  double bestWidth = -1.0, bestX = xHint;// [x0,x1], [x2,x3], ... are inside
  for (std::size_t k = 0; k + 1 < xs.size(); k += 2)
    if (xs[k + 1] - xs[k] > bestWidth) {
      bestWidth = xs[k + 1] - xs[k];
      bestX = 0.5 * (xs[k] + xs[k + 1]);
    }
  return {bestX, y};
}
}// namespace



PolyBuilding::PolyBuilding(const std::vector<polyVert> &iSP, float iH, float iBH, int iID)
  : Building()
{
  polygonVertices = iSP;
  H = iH;
  base_height = iBH;
  ID = iID;

  height_eff = base_height + H;
}

void PolyBuilding::setPolyBuilding(WINDSGeneralData *WGD)
{
  if (!WGD || polygonVertices.size() < 4 || !std::isfinite(H) || H <= 0
      || !std::isfinite(base_height))
    throw qes::InputError("A building needs a closed footprint, positive height and finite base elevation");
  for (const auto &vertex : polygonVertices) {
    if (!std::isfinite(vertex.x_poly) || !std::isfinite(vertex.y_poly))
      throw qes::InputError("Building footprint coordinates must be finite");
  }
  if (ringOffsets.empty()) ringOffsets = {0, polygonVertices.size()};
  if (ringOffsets.size()<2 || ringOffsets.front()!=0 || ringOffsets.back()!=polygonVertices.size())
    throw qes::InputError("Ring offsets must span the building vertices");
  for (std::size_t r=1; r<ringOffsets.size(); ++r) {
    if (ringOffsets[r]<=ringOffsets[r-1] || ringOffsets[r]-ringOffsets[r-1]<4)
      throw qes::InputError("Closed building rings need at least four vertices");
  }
  const auto outerEnd = ringOffsets[1];
  if (polygonVertices.front().x_poly != polygonVertices[outerEnd-1].x_poly
      || polygonVertices.front().y_poly != polygonVertices[outerEnd-1].y_poly)
    throw qes::InputError("Building footprint must be closed");


  building_cent_x = 0.0;// x-coordinate of the centroid of the building
  building_cent_y = 0.0;// y-coordinate of the centroid of the building
  height_eff = H + base_height;// Effective height of the building

  // Calculate the centroid coordinates of the building (average of all nodes coordinates)
  for (auto i = 0u; i < outerEnd - 1; i++) {
    building_cent_x += polygonVertices[i].x_poly;
    building_cent_y += polygonVertices[i].y_poly;
  }
  building_cent_x /= outerEnd - 1;
  building_cent_y /= outerEnd - 1;
  // The reference point samples the incident wind and anchors the wind-aligned
  // frame of the wake/canyon parameterizations, so it must lie in the footprint.
  // The vertex mean is kept unchanged when it does (always, for convex rings);
  // concave footprints and courtyard holes fall back to an interior point.
  if (!containsXY(building_cent_x, building_cent_y)) {
    const auto inside = scanlineInteriorPoint(polygonVertices, ringOffsets, building_cent_x, building_cent_y);
    building_cent_x = inside.first;
    building_cent_y = inside.second;
  }

  i_building_cent = std::round(building_cent_x / WGD->domain.dx()) - 1;// Index of building centroid in x-direction
  j_building_cent = std::round(building_cent_y / WGD->domain.dy()) - 1;// Index of building centroid in y-direction

  // checking if polygon is rectangular
  if (polygonVertices.size() == 5) {
    float tol = 1.0 * M_PI / 180.0;
    std::vector<float> normal_x;
    std::vector<float> normal_y;

    normal_x.resize(polygonVertices.size() - 1, 0.0);
    normal_y.resize(polygonVertices.size() - 1, 0.0);

    // Calculating outward normal to face
    for (size_t id = 0; id < polygonVertices.size() - 1; id++) {
      normal_x[id] = polygonVertices[id + 1].y_poly - polygonVertices[id].y_poly;
      normal_y[id] = polygonVertices[id].x_poly - polygonVertices[id + 1].x_poly;
      float norm = pow(normal_x[id] * normal_x[id] + normal_y[id] * normal_y[id], -0.5);
      normal_x[id] *= norm;
      normal_y[id] *= norm;
    }

    // checking internal angle
    for (size_t id = 0; id < polygonVertices.size() - 2; id++) {
      float scalProd = normal_x[id] * normal_x[id + 1] + normal_y[id] * normal_y[id + 1];
      if (std::abs(scalProd) < std::abs(cos(0.5 * M_PI - tol))) {
        rectangular_flag = true;
      } else {
        rectangular_flag = false;
        break;
      }
    }
  } else {
    rectangular_flag = false;
  }
}


/**
 *
 * This function defines bounds of the polygon building and sets the icellflag values
 * for building cells. It applies the Stair-step method to define building bounds.
 *
 */
void PolyBuilding::setCellFlags(WINDSGeneralData *WGD, int building_number)
{
  const float dx = WGD->domain.dx(), dy = WGD->domain.dy();


  // Loop to calculate maximum and minimum of x and y values of the building
  x_min = x_max = polygonVertices[0].x_poly;
  y_min = y_max = polygonVertices[0].y_poly;
  for (auto id = 1u; id < polygonVertices.size(); id++) {
    if (polygonVertices[id].x_poly > x_max) {
      x_max = polygonVertices[id].x_poly;
    }
    if (polygonVertices[id].x_poly < x_min) {
      x_min = polygonVertices[id].x_poly;
    }
    if (polygonVertices[id].y_poly > y_max) {
      y_max = polygonVertices[id].y_poly;
    }
    if (polygonVertices[id].y_poly < y_min) {
      y_min = polygonVertices[id].y_poly;
    }
  }


  i_start = (x_min / dx);// Index of building start location in x-direction
  i_end = (x_max / dx) + 1;// Index of building end location in x-direction
  j_start = (y_min / dy);// Index of building start location in y-direction
  j_end = (y_max / dy) + 1;// Index of building end location in y-direction

  // Define start index of the building in z-direction
  for (auto k = 1u; k < WGD->domain.z.size(); k++) {
    k_start = k;
    if (base_height <= WGD->domain.z_face[k + 1]) {
      break;
    }
  }

  // Define end index of the building in z-direction
  for (auto k = 0u; k < WGD->domain.z.size(); k++) {
    k_end = k + 1;
    if (height_eff < WGD->domain.z[k + 1]) {
      break;
    }
  }

  // Find out which cells are going to be inside the polygone
  // Based on Wm. Randolph Franklin, "PNPOLY - Point Inclusion in Polygon Test"
  // Check the center of each cell, if it's inside, set that cell to building
  for (auto j = j_start; j <= j_end; j++) {
    y_cent = (j + 0.5) * dy;// Center of cell y coordinate
    for (auto i = i_start; i <= i_end; i++) {
      x_cent = (i + 0.5) * dx;// Center of cell x coordinate
      if (containsXY(x_cent,y_cent)) {
        for (auto k = k_start; k < k_end; k++) {
          long icell_cent = WGD->domain.cell(i, j, k);
          if (WGD->icellflag[icell_cent] != 7) {
            WGD->icellflag[icell_cent] = 0;
          }
          if (WGD->ibuilding_flag[icell_cent] == -1) {
            WGD->ibuilding_flag[icell_cent] = building_number;
          }
        }
      }
    }
  }

}

bool PolyBuilding::faceExposed(const WINDSGeneralData *WGD, std::size_t edge, double x, double y, int k) const {
  if (!WGD->parameterizations.exposedFaces)
    return true;
  if (!isFace(edge) || k < 0 || k >= WGD->domain.nz() - 1)
    return false;
  const auto &a = polygonVertices[edge], &b = polygonVertices[edge + 1];
  const double ex = double(b.x_poly) - a.x_poly, ey = double(b.y_poly) - a.y_poly;
  const double length2 = ex * ex + ey * ey;
  if (!(length2 > 0))
    return false;
  const double along = std::clamp(((x - a.x_poly) * ex + (y - a.y_poly) * ey) / length2, 0., 1.);
  const double nx = -ey / std::sqrt(length2), ny = ex / std::sqrt(length2);
  const double px = std::nextafter(a.x_poly + along * ex, a.x_poly + along * ex + nx);
  const double py = std::nextafter(a.y_poly + along * ey, a.y_poly + along * ey + ny);
  const double dx = WGD->domain.dx(), dy = WGD->domain.dy();
  int i = std::floor(px / dx), j = std::floor(py / dy);
  const int sx = nx > 0 ? 1 : -1, sy = ny > 0 ? 1 : -1;
  const double inf = std::numeric_limits<double>::infinity();
  double tx = nx == 0 ? inf : (((sx > 0 ? i + 1 : i) * dx) - px) / nx;
  double ty = ny == 0 ? inf : (((sy > 0 ? j + 1 : j) * dy) - py) / ny;
  const double dtx = nx == 0 ? inf : dx / std::abs(nx), dty = ny == 0 ? inf : dy / std::abs(ny);
  for (int steps = 0; steps < WGD->domain.nx() + WGD->domain.ny(); ++steps) {
    if (i < 0 || j < 0 || i >= WGD->domain.nx() - 1 || j >= WGD->domain.ny() - 1)
      return false;
    const auto flag = WGD->icellflag_initial[WGD->domain.cell(i, j, k)];
    const bool solid = flag == 0 || flag == 2 || flag == 7;
    if (!containsXY((i + .5) * dx, (j + .5) * dy))
      return !solid;
    // Own solid ahead of the face is an opposite courtyard wall or concave
    // branch, not the source-side raster cell that the ray may skip.
    const double ahead = ((i + .5) * dx - px) * nx + ((j + .5) * dy - py) * ny;
    if (solid && ahead > 8 * std::numeric_limits<float>::epsilon() * std::max(dx, dy))
      return false;
    if (tx < ty) {
      i += sx;
      tx += dtx;
    } else if (ty < tx) {
      j += sy;
      ty += dty;
    } else {
      i += sx;
      j += sy;
      tx += dtx;
      ty += dty;
    }
  }
  return false;
}

void PolyBuilding::prepareParameterFaces(WINDSGeneralData *WGD) {
  const double tolerance = 0.5 * std::min(WGD->domain.dx(), WGD->domain.dy());
  const auto rings = facade_runs::simplify(polygonVertices, ringOffsets, tolerance);
  std::vector<polyVert> vertices;
  std::vector<std::size_t> offsets{0};
  for (auto ring : rings) {
    // A changed polygon has a canonical start as well as a deterministic set
    // of retained corners. Unchanged polygons return below without mutation.
    auto first = std::min_element(ring.begin(), ring.end(), [&](auto a, auto b) {
      return std::tie(polygonVertices[a].x_poly, polygonVertices[a].y_poly)
           < std::tie(polygonVertices[b].x_poly, polygonVertices[b].y_poly);
    });
    std::rotate(ring.begin(), first, ring.end());
    for (auto index : ring) vertices.push_back(polygonVertices[index]);
    vertices.push_back(polygonVertices[ring.front()]);
    offsets.push_back(vertices.size());
  }
  if (vertices.size() == polygonVertices.size())
    return;
  maskVertices = polygonVertices;
  maskRingOffsets = ringOffsets;
  polygonVertices = std::move(vertices);
  ringOffsets = std::move(offsets);
  setPolyBuilding(WGD);
}
