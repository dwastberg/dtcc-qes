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

/** @file WINDSGeneralData.h */

#pragma once

#include <vector>
#include <memory>
#include <cmath>


#define _USE_MATH_DEFINES
#define MIN_S(x, y) ((x) < (y) ? (x) : (y))
#define MAX_S(x, y) ((x) > (y) ? (x) : (y))

#include "WindModelInputs.h"

#include "qes/Domain.h"

#include "Building.h"

#include "LocalMixing.h"
#include "LocalMixingDefault.h"
#include "LocalMixingSerial.h"

#include "CutCell.h"
#include "Wall.h"


#ifdef HAS_OPTIX

// Needed to ensure that std::max and std::min are available
// since the optix.h headers eventually include windows.h on WIN32
// systems.  Windows overrides max and min and the following will
// force that off and thus allow std::max and std::min to work as
// desired.
#ifdef WIN32
#define NOMINMAX
#endif

#include "OptixRayTrace.h"
#endif


struct WINDSDeviceData
{
  float *u;
  float *v;
  float *w;
};

/**
 * @class WindsGeneralData
 * @brief :document this:
 */
class WINDSGeneralData
{
private:
  void validateInflow(const InflowCondition &) const;
  std::vector<std::unique_ptr<Building>> ownedBuildings_;

  WINDSGeneralData() : domain(1, 1, 1, 1, 1, 1) {}// do not allow empty domain to be created

public:
  explicit WINDSGeneralData(qes::Domain domain_in);
  /**
   * Prepares the wind model on flat ground. Builds one stair-step building per
   * footprint, which the model owns, and sets the solver coefficients.
   *
   * @param site_z0 inflow roughness length (m), used for the ground
   */
  WINDSGeneralData(qes::Domain domain_in, const std::vector<BuildingFootprint> &buildings,
                   const BuildingParameterizations &parameterizations, float site_z0);

  virtual ~WINDSGeneralData() = default;
  WINDSGeneralData(const WINDSGeneralData &) = delete;
  WINDSGeneralData &operator=(const WINDSGeneralData &) = delete;

  void mergeSort(std::vector<float> &effective_height,
                 std::vector<int> &building_id);

  /** Sets the initial field u0/v0/w0 to the inflow's log profile. */
  void applyWindProfile(const InflowCondition &);

  void applyParametrizations();

  void resetICellFlag();
  bool isSolid(const int &);
  bool isTerrain(const int &);
  bool isBuilding(const int &);

  ////////////////////////////////////////////////////////////////////////////
  //////// Variables and constants needed only in other functions-- Behnam
  //////// This can be moved to a new class (WINDSGeneralData)
  ////////////////////////////////////////////////////////////////////////////
  const float pi = 4.0f * atan(1.0); /**< pi constant */
  const float vk = 0.4; /**< Von Karman's constant */

  float cavity_factor = 1.0; /**< :document this: */
  float wake_factor = 0.0; /**< :document this: */
  float lengthf_coeff = 1.5; /**< :document this: */
  float theta{}; /**< :document this: */
  // int icell_face;
  // int icell_cent;

  // General QES Domain Data -- winds does not create this... provide const & in constructor of WINDS...
  qes::Domain domain;

  BuildingParameterizations parameterizations; /**< Empirical models applied per solve */
  int meshTypeFlag = 0; /**< 0 stair-step buildings; cut cells (1) are not built */

  ///@{
  /** Number of cells */
  // int nx, ny, nz;
  ///@}
  ///@{
  /** Grid resolution */
  // float dx, dy, dz;
  ///@}
  // float dxy; /**< Minimum value between dx and dy */

  float halo_x{}, halo_y{};
  int halo_index_x{}, halo_index_y{};

  // long numcell_cout{}; /**< :document this: */
  // long numcell_cout_2d; /**< :document this: */
  // long numcell_cent; /**< Total number of cell-centered values in domain */
  // long numcell_face; /**< Total number of face-centered values in domain */

  // std::vector<size_t> start; /**< :document this: */
  // std::vector<size_t> count; /**< :document this: */

  ///@{
  /** :Values of z0 for u and v components: */
  std::vector<float> z0_domain_u, z0_domain_v;
  ///@}

  std::vector<int> ibuilding_flag; /**< :Building number flag: */
  std::vector<int> building_id; /**< :Building ID: */
  std::vector<Building *> allBuildingsV; /**< :Vector contains all of the building elements: */

  float z0{}; /**< In wallLogBC */

  // std::vector<float> dz_array; /**< :Array contain dz values: */
  ///@{
  /** :Location of center of cell in x,y and z directions: */
  // std::vector<float> x, y, z;
  ///@}
  // std::vector<float> z_face; /**< :Location of the bottom face of the cell in z-direction: */


  ///@{
  /** Coefficient for SOR solver */
  std::vector<float> e, f, g, h, m, n;
  ///@}

  // The following are mostly used for output
  std::vector<int> icellflag;
  /**< Cell index flag (0 = Building, 1 = Fluid, 2 = Terrain, 3 = Upwind cavity
                        4 = Cavity, 5 = Farwake, 6 = Street canyon, 7 = Building cut-cells,
                        8 = Terrain cut-cells, 9 = Sidewall, 10 = Rooftop,
                        11 = Canopy vegetation, 12 = Fire) */
  std::vector<int> icellflag_initial;

  std::vector<float> building_volume_frac; /**< Cut-cell building volume fraction */

  ///@{
  /** Normal components of the cut surface for the solid elements (Building or Terrain) */
  std::vector<float> ni, nj, nk;
  ///@}
  std::vector<float> wall_distance; /**< :Distance of the cell center from the cut face: */
  std::vector<int> center_id; /**< :Defines whether a cell center is inside a solid (0) or air (1): */
  std::vector<float> terrain; /**< :document this: */
  std::vector<int> terrain_face_id; /**< Sensor function (inputWindProfile) */

  std::vector<float> base_height; /**< Base height of buildings */
  std::vector<float> effective_height; /**< Effective height of buildings */

  // Initial wind conditions
  ///@{
  /** Declaration of initial wind components (u0,v0,w0) */
  std::vector<float> u0, v0, w0;
  // maintain a separate QESWindData for u0,v0,w0
  ///@}

  ///@{
  /** Declaration of final velocity field components (u,v,w) */
  std::vector<float> u, v, w;

  /// it really needs to use SimDataAccess.windData for the u, v, w....
  ///@}

  // local Mixing class and data
  LocalMixing *localMixing{}; /**< :document this: */
  std::vector<double> mixingLengths; /**< :document this: */

  int id{}; /**< :document this: */

  // [FM Feb.28.2020] there 2 variables are not used anywhere
  // std::vector<float> site_canopy_H;
  // std::vector<float> site_atten_coeff;

  float convergence{}; /**< :document this: */

  // Canopy functions
  // std::vector<float> canopy_atten;   /**< Canopy attenuation coefficient */
  // std::vector<float> canopy_top;	   /**< Canopy height */
  // std::vector<int> canopy_top_index; /**< Canopy top index */
  // std::vector<float> canopy_z0;	   /**< Canopy surface roughness */
  // std::vector<float> canopy_ustar;   /**< Velocity gradient at the top of canopy */
  // std::vector<float> canopy_d;	   /**< Canopy displacement length */


  float max_velmag{}; /**< In polygonWake */

  Cell *cells{}; /**< :document this: */
  // bool DTEHFExists = false;
  CutCell *cut_cell = nullptr; /**< :document this: */
  std::unique_ptr<Wall> wall; /**< :document this: */

  // NetCDFInput* NCDFInput;     /**< :document this: */
  ///@{
  /** :document this: */
  // int ncnx, ncny, ncnz, ncnt;
  ///@}

  ///@{
  /** Building cut-cell (rectangular building) */
  std::vector<std::vector<std::vector<float>>> x_cut;
  std::vector<std::vector<std::vector<float>>> y_cut;
  std::vector<std::vector<std::vector<float>>> z_cut;
  std::vector<std::vector<int>> num_points;
  std::vector<std::vector<float>> coeff;
  ///@}

  WINDSDeviceData d_data{};
  void allocateDevice();
  void freeDevice();
  void copyDataToDevice();
  void copyDataFromDevice();

protected:
  // void defineHorizontalGrid();
  // void defineVerticalGrid();
  // void defineVerticalStretching(const float &);
  // void defineVerticalStretching(const std::vector<float> &);

  void allocateMemory();
};

inline bool WINDSGeneralData::isBuilding(const int &cellID)
{
  return (icellflag[cellID] == 0);
}

inline bool WINDSGeneralData::isTerrain(const int &cellID)
{
  return (icellflag[cellID] == 2);
}

inline bool WINDSGeneralData::isSolid(const int &cellID)
{
  return (icellflag[cellID] == 0 || icellflag[cellID] == 2);
}
