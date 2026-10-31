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

/** @file Building.h */

#pragma once
#include <algorithm>

#include "util/PolygonVertex.h"
#include "CutVertex.h"

using namespace std;

// forward declaration of WINDSGeneralData, which will be used by the
// derived classes and thus included there in the C++ files
class WINDSGeneralData;
class TURBGeneralData;

/**
 * @class Building
 * @brief An abstract representation of a building.
 *
 * Holds the basic information and funcitons that every building should have.
 *
 * @sa Canopy
 * @sa PolyBuilding
 * @sa RectangularBuilding
 * @sa WINDSGeneralData
 * @sa TURBGeneralData
 */
class Building
{
protected:
public:
  int ID{}; /**< :document this: */
  float building_rotation{}; /**< :document this: */
  float canopy_rotation{}; /**< :document this: */
  float x_start{}; /**< :document this: */
  float y_start{}; /**< :document this: */
  float L{}; /**< Length of the building */
  float W{}; /**< Width of the building */

  ///@{
  /** index of start and end of building in stair-step method */
  int i_start{}, i_end{}, j_start{}, j_end{}, k_end{}, k_start{};
  ///@}

  ///@{
  /** index of start and end of building in cut-cell method */
  int i_cut_start{}, i_cut_end{}, j_cut_start{}, j_cut_end{}, k_cut_end{};
  ///@}

  float H{}; /**< Height of the building */
  float base_height{}; /**< Base height of the building */

  float upwind_dir{}; /**< Wind direction of initial velocity at the height of building at the centroid */
  float height_eff{}; /**< Effective height of the building */
  float building_cent_x{}; /**< x coordinate of buildings' centroid */
  float building_cent_y{}; /**< y coordinate of buildings' centorid */
  int i_building_cent{}; /**< :document this: */
  int j_building_cent{}; /**< :document this: */


  double u0_h{}; /**< u velocity at the height of building at the centroid */
  double v0_h{}; /**< v velocity at the height of building at the centroid */

  float width_eff{}; /**< Effective width of the building */
  float length_eff{}; /**< Effective length of the building */
  float small_dimension{}; /**< Smaller of the height (H) and the effective cross-wind width (Weff) */
  float long_dimension{}; /**< Larger of the height (H) and the effective cross-wind width (Weff) */

  float L_over_H{}; /**< Length over height of the building */
  float H_over_L{}; /**< Height over length of the building */
  float W_over_H{}; /**< Width over height of the building */
  float Lr{}; /**< Length of far wake zone */

  std::vector<polyVert> polygonVertices; /**< :document this: */

  std::vector<std::size_t> ringOffsets;
  std::vector<polyVert> maskVertices;
  std::vector<std::size_t> maskRingOffsets;

  bool isFace(std::size_t edge) const {
    return edge + 1 < polygonVertices.size() && !std::binary_search(ringOffsets.begin(), ringOffsets.end(), edge + 1);
  }
  std::size_t previousFace(std::size_t edge) const {
    if (ringOffsets.empty())
      return (edge + polygonVertices.size() - 2) % (polygonVertices.size() - 1);
    const auto end = std::upper_bound(ringOffsets.begin(), ringOffsets.end(), edge);
    return edge == *(end - 1) ? *end - 2 : edge - 1;
  }
  std::size_t nextFace(std::size_t edge) const {
    if (ringOffsets.empty())
      return (edge + 1) % (polygonVertices.size() - 1);
    const auto end = std::upper_bound(ringOffsets.begin(), ringOffsets.end(), edge);
    return edge + 2 == *end ? *(end - 1) : edge + 1;
  }
  bool containsXY(double x, double y) const {
    const auto &vertices = maskVertices.empty() ? polygonVertices : maskVertices;
    const auto &offsets = maskVertices.empty() ? ringOffsets : maskRingOffsets;
    const float px = x, py = y;
    bool inside = false;
    for (std::size_t edge = 0; edge + 1 < vertices.size(); ++edge) {
      if (std::binary_search(offsets.begin(), offsets.end(), edge + 1))
        continue;
      const auto &a = vertices[edge], &b = vertices[edge + 1];
      if ((a.y_poly <= py && b.y_poly > py) || (a.y_poly > py && b.y_poly <= py)) {
        const float fraction = (py - a.y_poly) / (b.y_poly - a.y_poly);
        if (px < a.x_poly + fraction * (b.x_poly - a.x_poly))
          inside = !inside;
      }
    }
    return inside;
  }

  Building() {}

  virtual ~Building() {}

  // It would be nice if someone explained the function of each method below at the most abstract level.
  // using doxygen syntax

  /** Clear decisions that are specific to the next wind condition. */
  virtual void resetConditionState() {}

  virtual void setPolyBuilding(WINDSGeneralData *WGD)
  {
  }

  // Need to finalize the parameters here...
  virtual void setCellFlags(WINDSGeneralData *WGD, int building_number)
  {
  }

  virtual void upwindCavity(WINDSGeneralData *WGD)
  {
  }

  virtual void polygonWake(WINDSGeneralData *WGD, int building_id)
  {
  }

  virtual void canopyVegetation(WINDSGeneralData *WGD, int building_id)
  {
  }

  virtual void canopyWake(WINDSGeneralData *wgd, int building_id)
  {
  }

  virtual void canopyTurbulenceWake(WINDSGeneralData *wgd, TURBGeneralData *TGD, int buildind_id)
  {
  }

  virtual void canopyStress(WINDSGeneralData *wgd, TURBGeneralData *TGD, int buildind_id)
  {
  }

  virtual void streetCanyon(WINDSGeneralData *WGD)
  {
  }

  virtual void streetCanyonModified(WINDSGeneralData *WGD)
  {
  }

  virtual void sideWall(WINDSGeneralData *WGD)
  {
  }

  virtual void rooftop(WINDSGeneralData *WGD)
  {
  }

  virtual void NonLocalMixing(WINDSGeneralData *WGD, TURBGeneralData *TGD, int buidling_id)
  {
  }
};
