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
 * @file WINDSGeneralData.cpp
 * @brief :document this:
 */


#include "util/QESLog.h"
#include "WINDSGeneralData.h"
#include "LogProfile.h"
#include "LayerProfile.h"
#include "PolyBuilding.h"

#include <chrono>
#include <utility>
#include "util/UnsupportedFeature.h"

#define PBSTR "||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||"
#define PBWIDTH 60
#define LIMIT 99999999.0f

WINDSGeneralData::WINDSGeneralData(qes::Domain domain_in)
  : domain(std::move(domain_in))
{
  qes::log::info() << "-------------------------------------------------------------------" << std::endl;
  qes::log::info() << "[QES-WINDS]\t Initialization of wind model...\n";

  // tie(nx, ny, nz) = domain.getDomainCellNum();
  // tie(dx, dy, dz) = domain.getDomainSize();// Grid resolution in x-direction
  // dxy = domain.minDxy();// MIN_S(dx, dy);

  // numcell_cout = domain.numCellCentered();  // (nx - 1) * (ny - 1) * (nz - 2);// Total number of cell-centered values in domain
  // numcell_cout_2d = domain.numHorizontalCellCentered();// (nx - 1) * (ny - 1);// Total number of horizontal cell-centered values in domain
  // numcell_cent = domain.numCellCentered();// (nx - 1) * (ny - 1) * (nz - 1);// Total number of cell-centered values in domain
  // numcell_face = domain.numFaceCentered();// nx * ny * nz;// Total number of face-centered values in domain


  allocateMemory();
}

WINDSGeneralData::WINDSGeneralData(qes::Domain domain_in, const std::vector<BuildingFootprint> &buildings,
                                   const BuildingParameterizations &parameterizations_in, float site_z0)
  : domain(std::move(domain_in)), parameterizations(parameterizations_in)
{
  // Flat ground, stair-step buildings, no halo and one inflow sensor: the
  // former XML-driven setup reduces to the statements below, in their order.
  if (!std::isfinite(site_z0) || site_z0 <= 0)
    throw qes::InputError("Sensor roughness must be positive and stability must be finite");
  parameterizations.validateWakeDependencies();

  qes::log::info() << "-------------------------------------------------------------------" << std::endl;
  qes::log::info() << "[QES-WINDS]\t Initialization of wind model...\n";

  // /////////////////////////
  // Allocate memory
  // /////////////////////////
  allocateMemory();

  // /////////////////////////
  // Uniform z0 for the whole domain, from the inflow roughness
  // /////////////////////////
  z0 = 0.1;
  z0_domain_u.resize(domain.nx() * domain.ny());
  z0_domain_v.resize(domain.nx() * domain.ny());
  for (auto i = 0; i < domain.nx(); i++) {
    for (auto j = 0; j < domain.ny(); j++) {
      id = i + j * domain.nx();
      z0_domain_u[id] = site_z0;
      z0_domain_v[id] = site_z0;
      z0 = site_z0;
    }
  }

  // defining ground solid cells (ghost cells below the surface)
  for (int j = 0; j < domain.ny() - 1; j++) {
    for (int i = 0; i < domain.nx() - 1; i++) {
      icellflag[domain.cell(i, j, 0)] = 2;
    }
  }

  // Consolidate all buildings onto allBuildingsV; the buildings are owned here.
  allBuildingsV.clear();

  z0 = parameterizations.wallRoughness;

  if (parameterizations.upwindCavityFlag == 1) {
    lengthf_coeff = 2.0;
  } else {
    lengthf_coeff = 1.5;
  }

  // Determines how wakes behind buildings are calculated
  if (parameterizations.wakeFlag > 1) {
    cavity_factor = 1.1;
    wake_factor = 0.1;
  } else {
    cavity_factor = 1.0;
    wake_factor = 0.0;
  }

  auto buildingsetup_start = std::chrono::high_resolution_clock::now();// Start recording execution time

  if (!buildings.empty()) {
    qes::log::info() << "[QES-WINDS]\t Consolidating building data..." << std::endl;
  }

  for (size_t i = 0; i < buildings.size(); i++) {
    const auto &footprint = buildings[i];
    ownedBuildings_.push_back(std::make_unique<PolyBuilding>(footprint.vertices, footprint.height,
                                                             footprint.base_height, static_cast<int>(i)));
    allBuildingsV.push_back(ownedBuildings_.back().get());
    int j = allBuildingsV.size() - 1;
    building_id.push_back(j);
    allBuildingsV[j]->ID = j;
    allBuildingsV[j]->ringOffsets = footprint.ring_offsets;
    allBuildingsV[j]->setPolyBuilding(this);
    allBuildingsV[j]->setCellFlags(this, j);
    static_cast<PolyBuilding*>(allBuildingsV[j])->prepareParameterFaces(this);
    effective_height.push_back(allBuildingsV[j]->height_eff);
  }

  // Parameterizations run over buildings in order of height.
  qes::log::info() << "[QES-WINDS]\t Sorting buildings by height..." << std::flush;
  mergeSort(effective_height, building_id);

  auto buildingsetup_finish = std::chrono::high_resolution_clock::now();// Finish recording execution time

  std::chrono::duration<float> elapsed_cut = buildingsetup_finish - buildingsetup_start;
  qes::log::info() << "\t\t elapsed time: " << elapsed_cut.count() << " s\n";

  auto wallsetup_start = std::chrono::high_resolution_clock::now();

  qes::log::info() << "[QES-WINDS]\t Defining solid walls..." << std::flush;
  wall = std::make_unique<Wall>();
  // Boundary condition for building edges
  wall->defineWalls(this);
  wall->solverCoefficients(this);


  auto wallsetup_finish = std::chrono::high_resolution_clock::now();// Finish recording execution time
  std::chrono::duration<float> elapsed_wall = wallsetup_finish - wallsetup_start;
  qes::log::info() << "\t\t elapsed time: " << elapsed_wall.count() << " s\n";

  for (auto id = 0u; id < icellflag.size(); id++) {
    icellflag_initial[id] = icellflag[id];
  }
}


// should not be a constructor -- reuse the other constructor...


/*void WINDSGeneralData::defineVerticalStretching(const float &dz_value)
{
  // vertical grid (can be uniform or stretched)
  dz_array.resize(nz - 1, 0.0);
  // Uniform vertical grid
  for (float &k : dz_array) {
    k = dz_value;
  }
}*/

/*void WINDSGeneralData::defineVerticalStretching(const std::vector<float> &dz_value)
{
  // vertical grid (can be uniform or stretched)
  dz_array.resize(nz - 1, 0.0);
  // Stretched vertical grid
  for (size_t k = 1; k < dz_array.size(); ++k) {
    dz_array[k] = dz_value[k - 1];// Read in custom dz values and set them to dz_array
  }
  dz_array[0] = dz_array[1];// Value for ghost cell below the surface
  dz = *std::min_element(dz_array.begin(), dz_array.end());// Set dz to minimum value of
}*/

/*void WINDSGeneralData::defineVerticalGrid()
{
  // Location of face in z-dir
  z_face.resize(nz, 0.0);
  z_face[0] = -dz_array[0];
  z_face[1] = 0.0;
  for (size_t k = 2; k < z_face.size(); ++k) {
    z_face[k] = z_face[k - 1] + dz_array[k - 1];
  }

  // Location of cell centers in z-dir
  z.resize(nz - 1, 0.0);
  z[0] = -0.5f * dz_array[0];
  for (size_t k = 1; k < z.size(); ++k) {
    z[k] = 0.5f * (z_face[k] + z_face[k + 1]);
  }
}*/

/*void WINDSGeneralData::defineHorizontalGrid()
{
  // horizontal grid (x-direction)
  x.resize(nx - 1);
  for (auto i = 0; i < nx - 1; ++i) {
    x[i] = ((float)i + 0.5f) * dx;// Location of face centers in x-dir
  }

  // horizontal grid (y-direction)
  y.resize(ny - 1);
  for (auto j = 0; j < ny - 1; ++j) {
    y[j] = ((float)j + 0.5f) * dy;// Location of face centers in y-dir
  }
}*/

void WINDSGeneralData::allocateMemory()
{
  qes::log::info() << "[QES-WINDS]\t Allocating Memory..." << std::flush;

  // long numcell_cout = domain.numCellCentered();  // (nx - 1) * (ny - 1) * (nz - 2);// Total number of cell-centered values in domain
  long numcell_cout_2d = domain.numHorizontalCellCentered();// (nx - 1) * (ny - 1);// Total number of horizontal cell-centered values in domain
  long numcell_cent = domain.numCellCentered();// (nx - 1) * (ny - 1) * (nz - 1);// Total number of cell-centered values in domain
  long numcell_face = domain.numFaceCentered();// nx * ny * nz;// Total number of face-centered values in domain

  // numcell_cout = (nx - 1) * (ny - 1) * (nz - 2);// Total number of cell-centered values in domain
  // numcell_cout_2d = (nx - 1) * (ny - 1);// Total number of horizontal cell-centered values in domain
  // numcell_cent = (nx - 1) * (ny - 1) * (nz - 1);// Total number of cell-centered values in domain
  // numcell_face = nx * ny * nz;// Total number of face-centered values in domain

  // Resize the coefficients for use with the solver
  e.resize(numcell_cent, 1.0);
  f.resize(numcell_cent, 1.0);
  g.resize(numcell_cent, 1.0);
  h.resize(numcell_cent, 1.0);
  m.resize(numcell_cent, 1.0);
  n.resize(numcell_cent, 1.0);

  icellflag.resize(numcell_cent, 1);
  icellflag_initial.resize(numcell_cent, 1);

  ibuilding_flag.resize(numcell_cent, -1);

  terrain.resize(numcell_cout_2d, 0.0);
  terrain_face_id.resize(domain.nx() * domain.ny(), 1);

  // Set the Wind Velocity data elements to be of the correct size
  // Initialize u0,v0, and w0 to 0.0
  u0.resize(numcell_face, 0.0);
  v0.resize(numcell_face, 0.0);
  w0.resize(numcell_face, 0.0);
  // Initialize u,v and w to 0.0
  u.resize(numcell_face, 0.0);
  v.resize(numcell_face, 0.0);
  w.resize(numcell_face, 0.0);

}

void WINDSGeneralData::ensureCutCellStorage()
{
  const auto count = domain.numCellCentered();
  building_volume_frac.resize(count, 1.0f);
  ni.resize(count, 0.0f); nj.resize(count, 0.0f); nk.resize(count, 0.0f);
  center_id.resize(count, 1); wall_distance.resize(count, 0.0f);
}

void WINDSGeneralData::ensureMixingLengthStorage()
{
  mixingLengths.resize(domain.numCellCentered(), 0.0);
}



void WINDSGeneralData::applyWindProfile(const InflowCondition &inflow)
{
  validateInflow(inflow);

  qes::log::info() << "[QES-WINDS]\t Applying Wind Profile...\n";

  u0.clear();
  v0.clear();
  w0.clear();
  u0.resize(domain.numFaceCentered(), 0.0);
  v0.resize(domain.numFaceCentered(), 0.0);
  w0.resize(domain.numFaceCentered(), 0.0);

  auto start_InputWindProfile = std::chrono::high_resolution_clock::now();// Finish recording execution time

  if (inflow.profile_kind == dtcc_qes::ProfileKind::Log) applyLogProfile(inflow, this);
  else applyLayerProfile(inflow, this);

  max_velmag = 0.0;
  if (inflow.profile_kind == dtcc_qes::ProfileKind::Log) {
    // Keep the legacy top-layer expressions, order and operand types.
    for (auto i = 0; i < domain.nx(); i++) {
      for (auto j = 0; j < domain.ny(); j++) {
        long icell_face = domain.face(i, j, domain.nz() - 2);
        max_velmag = MAX_S(max_velmag, sqrt(pow(u0[icell_face], 2.0) + pow(v0[icell_face], 2.0)));
      }
    }
  } else {
    for (std::size_t k = 0; k < inflow.layer_u.size(); ++k)
      max_velmag = std::max(max_velmag, static_cast<float>(std::hypot(double(inflow.layer_u[k]), double(inflow.layer_v[k]))));
  }
  max_velmag *= 1.2;

  auto end_InputWindProfile = std::chrono::high_resolution_clock::now();// Finish recording execution time

  std::chrono::duration<float> elapsed_InputWindProfile = end_InputWindProfile - start_InputWindProfile;
  qes::log::info() << "\t\t elapsed time: " << elapsed_InputWindProfile.count() << " s\n";
  return;
}

void WINDSGeneralData::applyParametrizations()
{
  parameterizations.validateWakeDependencies();
  for (auto *building : allBuildingsV) building->resetConditionState();

  auto start_param = std::chrono::high_resolution_clock::now();// Start recording execution time
  qes::log::info() << "[QES-WINDS]\t Applying parameterizations...\n";

  ///////////////////////////////////////////
  //   Upwind Cavity Parameterization     ///
  ///////////////////////////////////////////
  if (parameterizations.upwindCavityFlag > 0) {
    qes::log::info() << "[QES-WINDS]\t Applying upwind cavity parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->upwindCavity(this);
    }
  }

  //////////////////////////////////////////////////
  //   Far-Wake and Cavity Parameterizations     ///
  //////////////////////////////////////////////////
  if (parameterizations.wakeFlag > 0) {
    qes::log::info() << "[QES-WINDS]\t Applying wake behind building parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->polygonWake(this, building_id[i]);
    }
  }

  ///////////////////////////////////////////
  //   Street Canyon Parameterization     ///
  ///////////////////////////////////////////
  if (parameterizations.streetCanyonFlag == 1) {
    qes::log::info() << "[QES-WINDS]\t Applying street canyon parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->streetCanyon(this);
    }
  } else if (parameterizations.streetCanyonFlag == 2) {
    qes::log::info() << "[QES-WINDS]\t Applying street canyon parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->streetCanyonModified(this);
    }
  }

  ///////////////////////////////////////////
  //      Sidewall Parameterization       ///
  ///////////////////////////////////////////
  if (parameterizations.sidewallFlag > 0) {
    qes::log::info() << "[QES-WINDS]\t Applying sidewall parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->sideWall(this);
    }
  }


  ///////////////////////////////////////////
  //      Rooftop Parameterization        ///
  ///////////////////////////////////////////
  if (parameterizations.rooftopFlag > 0) {
    qes::log::info() << "[QES-WINDS]\t Applying rooftop parameterization...\n";
    for (size_t i = 0; i < allBuildingsV.size(); i++) {
      allBuildingsV[building_id[i]]->rooftop(this);
    }
  }

  wall->setVelocityZero(this);

  auto finish_param = std::chrono::high_resolution_clock::now();// Finish recording execution time

  std::chrono::duration<float> elapsed_param = finish_param - start_param;
  qes::log::info() << "\t\t elapsed time: " << elapsed_param.count() << " s\n";
}

void WINDSGeneralData::resetICellFlag()
{
  for (size_t id = 0; id < icellflag.size(); id++) {
    icellflag[id] = icellflag_initial[id];
  }
  return;
}

void WINDSGeneralData::mergeSort(std::vector<float> &effective_height, std::vector<int> &building_id)
{
  // if the size of the array is 1, it is already sorted
  if (building_id.size() == 1) {
    return;
  }

  if (building_id.size() > 1) {
    // make left and right sides of the data
    std::vector<float> effective_height_L, effective_height_R;
    std::vector<int> building_id_L, building_id_R;
    effective_height_L.resize(building_id.size() / 2);
    effective_height_R.resize(building_id.size() - building_id.size() / 2);
    building_id_L.resize(building_id.size() / 2);
    building_id_R.resize(building_id.size() - building_id.size() / 2);

    // copy data from the main data set to the left and right children
    size_t lC = 0, rC = 0;
    for (size_t i = 0; i < building_id.size(); i++) {
      if (i < building_id.size() / 2) {
        effective_height_L[lC] = effective_height[i];
        building_id_L[lC++] = building_id[i];

      } else {
        effective_height_R[rC] = effective_height[i];
        building_id_R[rC++] = building_id[i];
      }
    }
    // recursively sort the children
    mergeSort(effective_height_L, building_id_L);
    mergeSort(effective_height_R, building_id_R);

    // compare the sorted children to place the data into the main array
    lC = rC = 0;
    for (size_t i = 0; i < building_id.size(); i++) {
      if (rC == effective_height_R.size() || (lC != effective_height_L.size() && effective_height_L[lC] < effective_height_R[rC])) {
        effective_height[i] = effective_height_L[lC];
        building_id[i] = building_id_L[lC++];
      } else {
        effective_height[i] = effective_height_R[rC];
        building_id[i] = building_id_R[rC++];
      }
    }
  }

  return;
}

void WINDSGeneralData::validateInflow(const InflowCondition &inflow) const
{
  if (inflow.profile_kind != dtcc_qes::ProfileKind::Log
      && inflow.profile_kind != dtcc_qes::ProfileKind::LayerTable)
    throw qes::InputError("Unsupported profile kind");
  const float x = inflow.site_xcoord, y = inflow.site_ycoord;
  if (!std::isfinite(x) || !std::isfinite(y) || x < 0 || y < 0
      || x >= (domain.nx() - 1) * domain.dx()
      || y >= (domain.ny() - 1) * domain.dy())
    throw qes::InputError("Wind sensor must be inside the horizontal domain");
  if (!std::isfinite(inflow.site_z0) || inflow.site_z0 <= 0
      || !std::isfinite(inflow.site_one_overL))
    throw qes::InputError("Sensor roughness must be positive and stability must be finite");
  if (!std::isfinite(inflow.site_z_ref) || inflow.site_z_ref <= 0
      || !std::isfinite(inflow.site_U_ref) || inflow.site_U_ref < 0
      || !std::isfinite(inflow.site_wind_dir))
    throw qes::InputError("Sensor heights must be positive; speeds non-negative; all profile values finite");
}
