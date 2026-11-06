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

/** @file PolyBuilding.h */

#pragma once

#include "util/QESLog.h"

#define _USE_MATH_DEFINES
#include <cmath>
#include <math.h>
#include <algorithm>

#include "Building.h"

using namespace std;

using std::endl;
using std::vector;

#define MIN_S(x, y) ((x) < (y) ? (x) : (y))

/**
 * @class PolyBuliding
 * @brief Designed for the general building shape (polygons).
 *
 * It's an inheritance of the building class (has all the features defined in that class).
 * In this class, first, the polygon buildings will be defined and then different
 * parameterizations related to each building will be applied. For now,
 *
 * @sa Building
 */
class PolyBuilding : public Building
{
private:
protected:
  ///@{
  /** Position value of the building */
  float x_min{}, x_max{}, y_min{}, y_max{};
  ///@}
  ///@{
  /** Center of a cell. */
  float x_cent{}, y_cent{};
  ///@}
  float polygon_area{}; /**< Polygon area */


  bool rectangular_flag = false; /**< Is the building rectangular */

  int rooftop_flag = 0; /**< rooftop flag */

  ///@{
  /** :document this */
  std::vector<float> xi, yi;
  ///@}

  ///@{
  /** :document this: */
  std::vector<float> xf1, yf1, xf2, yf2;
  ///@}

  ///@{
  /** :document this: */
  float x1{}, x2{}, y1{}, y2{};
  ///@}

  std::vector<float> upwind_rel_dir; /**< :document this: */

public:
  void prepareParameterFaces(WINDSGeneralData *WGD);
  bool faceExposed(const WINDSGeneralData *WGD, std::size_t edge, double x, double y, int k) const;

  void resetConditionState() override
  {
    // polygonWake only assigns this for eligible wind-facing edges. Restore
    // the fresh-building decision before every condition, including retries.
    rooftop_flag = 0;
  }

  PolyBuilding()
    : Building()
  {
    // What should go here ???  Good to consider this case so we
    // don't have problems down the line.
  }

  virtual ~PolyBuilding()
  {
  }

  /**
   * Creates a polygon type building.
   *
   * Calculates and initializes all the features specific to this type of the building.
   * This function reads in nodes of the polygon along with height and base height of the building.
   *
   * @param iSP :document this:
   * @param iH :document this:
   * @param iH :document this:
   * @param iID :document this:
   */
  PolyBuilding(const std::vector<polyVert> &iSP, float iH, float iBH, int iID);


  /**
   * :document this:
   *
   * @param WGD :document this:
   */
  void setPolyBuilding(WINDSGeneralData *WGD) override;


  /**
   * Defines bounds of the polygon building and sets the icellflag values
   * for building cells. It applies the Stair-step method to define building bounds.
   *
   * @param WGD :document this:
   * @param building_number :document this:
   */
  void setCellFlags(WINDSGeneralData *WGD, int building_number) override;

  /**
   * Applies the upwind cavity in front of the building to buildings defined as polygons.
   *
   * Reads in building features like nodes, building height and base height and uses
   * features of the building defined in the class constructor and setCellsFlag function. It defines
   * cells in the upwind area and applies the approperiate parameterization to them.
   * More information: "Improvements to a fast-response WINDSan wind model, M. Nelson et al. (2008)"
   *
   * @param WGD :document this:
   */
  void upwindCavity(WINDSGeneralData *WGD) override;

  /**
   * Applies wake behind the building parameterization to buildings defined as polygons.
   *
   * The parameterization has two parts: near wake and far wake. This function reads in building features
   * like nodes, building height and base height and uses features of the building defined in the class
   * constructor ans setCellsFlag function. It defines cells in each wake area and applies the approperiate
   * parameterization to them.
   *
   * @param WGD :document this:
   * @param building_id :document this:
   */
  void polygonWake(WINDSGeneralData *WGD, int building_id) override;


  /**
   * Applies the street canyon parameterization to the qualified space between buildings defined as polygons.
   *
   * Reads in building features like nodes, building height and base height and uses
   * features of the building defined in the class constructor and setCellsFlag function. It defines
   * cells qualified in the space between buildings and applies the approperiate parameterization to them.
   * More information: "Improvements to a fast-response WINDSan wind model, M. Nelson et al. (2008)"
   *
   * @param WGD :document this:
   */
  void streetCanyon(WINDSGeneralData *WGD) override;

  /**
   * Applies the street canyon parameterization to the qualified space between buildings defined as polygons.
   *
   * Reads in building features like nodes, building height and base height and uses
   * features of the building defined in the class constructor and setCellsFlag function. It defines
   * cells qualified in the space between buildings and applies the approperiate parameterization to them.
   * More information: "Improvements to a fast-response WINDSan wind model, M. Nelson et al. (2008)"
   * New model base on "Evaluation of the QUIC-URB fast response urban wind model for a cubical building
   * array and wide building street canyon" Singh et al. (2008)
   *
   * @param WGD :document this:
   */
  void streetCanyonModified(WINDSGeneralData *WGD) override;

  /**
   * Applies the sidewall parameterization to the qualified space on the side of buildings defined as polygons.
   *
   * Reads in building features like nodes, building height and base height and uses
   * features of the building defined in the class constructor and setPolyBuilding and setCellsFlag functions. It defines
   * cells qualified on the side of buildings and applies the approperiate parameterization to them.
   * More information: "Comprehensive Evaluation of Fast-Response, Reynolds-Averaged Navier–Stokes, and Large-Eddy Simulation
   * Methods Against High-Spatial-Resolution Wind-Tunnel Data in Step-Down Street Canyons, A. N. Hayati et al. (2017)"
   *
   * @param WGD :document this:
   */
  void sideWall(WINDSGeneralData *WGD) override;


  /**
   * Applies the rooftop parameterization to the qualified space on top of buildings defined as polygons.
   *
   * Reads in building features like nodes, building height and base height and uses
   * features of the building defined in the class constructor and setPolyBuilding and setCellsFlag functions. It defines
   * cells qualified on top of buildings and applies the approperiate parameterization to them.
   * More information:
   *
   * @param WGD :document this:
   */
  void rooftop(WINDSGeneralData *WGD) override;






  /**
   * Applies the non local mixing length model.
   * More information: William et al. 2004
   *
   * @param WGD
   * @param TGD
   * @param bWIDling_id
   */
  void NonLocalMixing(WINDSGeneralData *WGD, TURBGeneralData *TGD, int bWIDling_id) override;
};
