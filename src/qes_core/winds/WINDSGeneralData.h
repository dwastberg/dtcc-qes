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

#include <map>
#include "dtcc/api/canyon_types.h"
#include <functional>
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

#include "Wall.h"

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

  // Private canyon state. Detached by WindRunner's solve scope on every exit.
  dtcc_qes::CanyonModel research_canyon_model=dtcc_qes::CanyonModel::Legacy;
  bool research_aligned_canyon=false;
  bool canyon_trace_roof=false;
  std::vector<double> canyon_roof_trace;
  std::size_t canyon_voxel_roof_changes=0;
  std::vector<float> canyon_incident_u,canyon_incident_v;
  std::map<std::string,std::size_t> canyon_fallback_reasons;
  std::size_t canyon_core_u=0,canyon_core_v=0,canyon_core_w=0,canyon_roof_skipped=0;
  std::size_t canyon_changed_faces=0,canyon_roof_changes=0,canyon_audit_zones=0,canyon_W_changes=0;
  std::size_t canyon_qualified=0,canyon_fallback=0,canyon_writes=0;

  void applyParametrizations(const std::function<void(const char *)> &stage = {});

  void resetICellFlag();
  void ensureMixingLengthStorage();
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

  // General QES Domain Data -- winds does not create this... provide const & in constructor of WINDS...
  qes::Domain domain;

  BuildingParameterizations parameterizations; /**< Empirical models applied per solve */

  ///@{
  /** :Values of z0 for u and v components: */
  std::vector<float> z0_domain_u, z0_domain_v;
  ///@}

  std::vector<int> ibuilding_flag; /**< :Building number flag: */
  std::vector<int> building_id; /**< :Building ID: */
  std::vector<Building *> allBuildingsV; /**< :Vector contains all of the building elements: */

  float z0{}; /**< In wallLogBC */

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
  std::vector<double> mixingLengths; /**< :document this: */

  int id{}; /**< :document this: */

  float max_velmag{}; /**< In polygonWake */

  std::unique_ptr<Wall> wall; /**< :document this: */

protected:

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
