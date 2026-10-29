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

/** @file SimulationParameters.h */

#pragma once

#include <string>
#include "util/ParseInterface.h"
#include "util/ParseVector.h"
#include "util/Vector3Float.h"
#include "util/Vector3Int.h"
#include "util/Mesh.h"
class DTEHeightField;
class WRFInput;

#include "util/TimerTool.h"

/**
 * @class SimulationParameters
 * @brief Contains variables that define information
 * necessary for running the simulation.
 *
 * @sa ParseInterface
 */
class SimulationParameters : public ParseInterface
{
private:
public:
  Vector3Int domain; /**< :Number of cells in each direction: */
  Vector3Float grid; /**< :Cell sizes in each direction: */
  int verticalStretching = 0; /**< :Defines grid type in z-direction (0-unifrom (default), 1-custom): */
  std::vector<float> dz_value; /**< :Array holding values of dz if the verticalStretching is 1: */
  unsigned int totalTimeIncrements = 1; /**< :Total number of time steps: */
  int logLawFlag = 0; /**< :Log Law flag to apply the log law (0-off (default), 1-on): */
  int maxIterations = 500; /**< :Maximum number of iterations (default = 500): */
  double tolerance = 1e-5; /**< :Convergence criteria, error threshold (default = 1e-9): */
  int meshTypeFlag = 0; /**< :Type of meshing scheme (0-Stair step (original QES) (default), 1-Cut-cell method: */
  float domainRotation = 0; /**< :Rotation angle of domain relative to true north: */
  int originFlag = 0; /**< :Origin flag (0- DEM coordinates (default), 1- UTM coordinates): */
  float UTMx; /**< :x component (m) of origin in UTM DEM coordinates (if originFlag = 1): */
  float UTMy; /**< :y component (m) of origin in UTM DEM coordinates (if originFlag = 1): */
  int UTMZone; /**< :UTM zone that domain located: */
  std::string UTMZoneLetter;
  float DEMDistancex = 0.0; /**< :x component (m) of origin in DEM coordinates (if originFlag = 0): */
  float DEMDistancey = 0.0; /**< :y component (m) of origin in DEM coordinates (if originFlag = 0): */
  float halo_x = 0.0; /**< :Halo region added to x-direction of domain (at the beginning and the end of domain) (meters): */
  float halo_y = 0.0; /**< :Halo region added to y-direction of domain (at the beginning and the end of domain) (meters): */
  float heightFactor = 1.0; /**< :Height factor multiplied by the building height read in from the shapefile (default = 1.0): */

  int readCoefficientsFlag = 0; /**< :Reading solver coefficients flag (0-calculate coefficients (default), 1-read coefficients from the file): */
  std::string coeffFile; /**< :Address to coefficients file location: */

  // DTE - digital elevation model details
  std::string demFile; /**< DEM file name */
  DTEHeightField *DTE_heightField = nullptr; /**< :document this: */
  Mesh *DTE_mesh = nullptr; /**< :document this: */

  // //////////////////////////////////////////
  // WRF File Parameters
  // //////////////////////////////////////////
  //
  // Two use-cases are now supported:
  //
  // (1) Only a WRF file is supplied.
  // If only a WRF data output file is supplied in the XML, the
  // elevation, terrain model is acquired from the WRF Fire Mesh.
  // Metparmas related to stations/sensors are pulled from the wind
  // profile supplied by WRF.
  // * Issues:
  // - We are not yet checking if no fire mesh is specified.  If no
  // fire mesh is available, the terrain height could come from the
  // atmos mesh.
  //
  // (2) Both a DEM and a WRF file are supplied.  With both a DEM
  // and WRF file, the DEM will be used for creating the terrain and
  // the WRF file will only be used to extract stations/sensors
  // pulled from the wind profile in the WRF atmospheric mesh. Thus,
  // no terrain will be queried from the WRF file.
  //

  std::string wrfFile; /**< :document this: */
  WRFInput *wrfInputData = nullptr; /**< :document this: */
  int wrfSensorSample = 1; /**< :document this: */
  bool wrfCoupling = false;

  enum DomainInputType {
    WRFOnly,
    WRFDEM,
    DEMOnly,
    UNKNOWN
  };
  DomainInputType m_domIType = UNKNOWN;

  SimulationParameters()
  {
    UTMx = 0.0;
    UTMy = 0.0;
    UTMZone = 0;
    UTMZoneLetter = "";
  }

  ~SimulationParameters();


  /**
   * :document this:
   */
  void parseValues() override;
};
