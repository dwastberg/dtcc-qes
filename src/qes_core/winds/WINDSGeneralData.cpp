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

#include <utility>
#include "util/QESFeatures.h"
#include "util/UnsupportedFeature.h"
#if QES_ENABLE_IO
#include "WindProfilerHRRR.h"
#endif

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

WINDSGeneralData::WINDSGeneralData(const WINDSInputData *WID, qes::Domain domain_in, int solverType)
  : domain(std::move(domain_in))
{
  if (!WID || !WID->simParams || !WID->metParams)
    throw qes::InputError("Simulation parameters and meteorological inputs are required");

#if !QES_ENABLE_IO
  if (WID->simParams->meshTypeFlag != 0)
    throw qes::UnsupportedFeature("The in-memory core requires stair-step buildings");
  const auto stretching = WID->simParams->verticalStretching;
  if (stretching == 1) {
    const auto &layers = WID->simParams->dz_value;
    if (layers.size() != static_cast<std::size_t>(domain.nz() - 2)
        || !std::equal(layers.begin(), layers.end(), domain.dz_array.begin() + 1))
      throw qes::InputError("Declared vertical layers do not match the constructed domain");
    if (WID->simParams->logLawFlag != 0)
      throw qes::UnsupportedFeature("Wall log-law correction is not supported with explicit vertical layers");
  } else if (stretching != 0 || !domain.verticallyUniform()) {
    throw qes::InputError("Vertical grid mode does not match the constructed domain");
  }
  if (WID->simParams->DTE_heightField || WID->simParams->DTE_mesh
      || !WID->simParams->demFile.empty() || !WID->simParams->wrfFile.empty()
      || WID->simParams->wrfInputData || WID->simParams->wrfCoupling
      || WID->simParams->readCoefficientsFlag || !WID->simParams->coeffFile.empty()
      || WID->hrrrInput || !WID->metParams->sensorName.empty()
      || (WID->buildingsParams && (WID->buildingsParams->SHPData || !WID->buildingsParams->shpFile.empty()))
      || (WID->vegetationParams && (WID->vegetationParams->SHPData || !WID->vegetationParams->shpFile.empty()))) {
    throw qes::UnsupportedFeature("File-backed inputs require QES_ENABLE_IO=ON");
  }
#endif

  qes::log::info() << "-------------------------------------------------------------------" << std::endl;
  qes::log::info() << "[QES-WINDS]\t Initialization of wind model...\n";

  // converting the domain rotation to radians from degrees -- input
  // assumes degrees
  theta = (WID->simParams->domainRotation * pi / 180.0);

  // Pull Domain Size information from the WINDSInputData structure --
  // this is either read in from the XML files and/or potentially
  // calculated based on the geographic data that was loaded
  // (i.e. DEM files). It is important to get this data from the
  // main input structure.
  //
  // This is done to make reference to nx, ny and nz easier in this function
  // Vector3Int domainInfo;
  // domainInfo = *(WID->simParams->domain);
#if NOTUSED
  nx = WID->simParams->domain[0];
  ny = WID->simParams->domain[1];
  nz = WID->simParams->domain[2];
  // Modify the domain size to fit the Staggered Grid used in the solver
  nx += 1;// +1 for Staggered grid
  ny += 1;// +1 for Staggered grid
  nz += 2;// +2 for staggered grid and ghost cell

  // Vector3 gridInfo;
  // gridInfo = *(WID->simParams->grid);
  dx = WID->simParams->grid[0];// Grid resolution in x-direction
  dy = WID->simParams->grid[1];// Grid resolution in y-direction
  dz = WID->simParams->grid[2];// Grid resolution in z-direction
#endif

  // dxy = domain.minDxy();// MIN_S(dx, dy);

  // numcell_cout = domain.numCellCentered();  // (nx - 1) * (ny - 1) * (nz - 2);// Total number of cell-centered values in domain
  // numcell_cout_2d = domain.numHorizontalCellCentered();// (nx - 1) * (ny - 1);// Total number of horizontal cell-centered values in domain
  // numcell_cent = domain.numCellCentered();// (nx - 1) * (ny - 1) * (nz - 1);// Total number of cell-centered values in domain
  // numcell_face = domain.numFaceCentered();// nx * ny * nz;// Total number of face-centered values in domain

  // /////////////////////////
  // Allocate memory
  // /////////////////////////
  allocateMemory();


  //////////////////////////////////////////////////////////////////////////////////
  /////    Create sensor velocity profiles and generate initial velocity field /////
  //////////////////////////////////////////////////////////////////////////////////
  // Calling inputWindProfile function to generate initial velocity
  // field from sensors information (located in Sensor.cpp)

  // where should this really go?
  //
  // Need to now take all WRF station data and convert to
  // sensors
  if (WID->simParams->wrfInputData) {
    initializeWRFSensors(WID);
  } else {// no wrf data to deal with...
    /* FM NOTES:
       WARNING this is unfinished.
       + does support halo for QES coord (site coord == 1)
       - does not support halo for UTM coord (site coord == 2)
       - does not support halo for lon/lat coord (site coord == 3)
    */

    if (solverType == 1) {
      if (WID->hrrrInput) {
        if (WID->hrrrInput->interpolationScheme == 0) {
          windProfiler = std::make_unique<WindProfilerBarnCPU>();
        } else {
#if QES_ENABLE_IO
          windProfiler = std::make_unique<WindProfilerHRRR>();
#else
          throw qes::UnsupportedFeature("HRRR requires QES_ENABLE_IO=ON");
#endif
        }
      } else {
        windProfiler = std::make_unique<WindProfilerBarnCPU>();
      }
#ifdef HAS_CUDA
    } else {
      if (WID->hrrrInput) {
        if (WID->hrrrInput->interpolationScheme == 0) {
          windProfiler = std::make_unique<WindProfilerBarnGPU>();
        } else {
#if QES_ENABLE_IO
          windProfiler = std::make_unique<WindProfilerHRRR>();
#else
          throw qes::UnsupportedFeature("HRRR requires QES_ENABLE_IO=ON");
#endif
        }
      } else {
        windProfiler = std::make_unique<WindProfilerBarnGPU>();
      }
    }
#else
    } else {
      qes::log::info() << "No CUDA support - using CPU Barnes" << std::endl;
      windProfiler = std::make_unique<WindProfilerBarnCPU>();
    }
#endif

    //////////////////////////////////////////////////////////////////////////////////
    /////      Create an instance of HRRRInput class and processing HRRR         /////
    /////      data to create wind profiles                                      /////
    //////////////////////////////////////////////////////////////////////////////////
    if (WID->hrrrInput) {
      downscaleHRRR(WID);
    } else {
      // If the sensor file specified in the xml
      if (WID->metParams->sensorName.size() > 0) {
        for (size_t i = 0; i < WID->metParams->sensorName.size(); i++) {
          // Create new sensor object
          WID->metParams->sensors.push_back(new Sensor(WID->metParams->sensorName[i]));
        }
      }
      // If there are more than one timestep
      // if (WID->simParams->totalTimeIncrements > 0) {
      validateSensors(WID);
      // Loop to include all the timestep for the first sensor
      for (size_t i = 0; i < WID->metParams->sensors[0]->TS.size(); i++) {
        sensortime.push_back(WID->metParams->sensors[0]->TS[i]->time);
        sensortime_id.push_back(i);
      }
    }

    // Loop to include all the unique timesteps of the rest of the sensors
    for (size_t i = 0; i < WID->metParams->sensors.size(); i++) {
      for (size_t j = 0; j < WID->metParams->sensors[i]->TS.size(); j++) {
        size_t count = 0;
        for (size_t k = 0; k < sensortime.size(); k++) {
          if (WID->metParams->sensors[i]->TS[j]->time != sensortime[k]) {
            count += 1;
          }
        }
        // If the timestep is not allready included in the list
        if (count == sensortime.size()) {
          sensortime.push_back(WID->metParams->sensors[i]->TS[j]->time);
          sensortime_id.push_back(sensortime.size() - 1);
        }
        // If the timestep is not allready included in the list
        if (count == sensortime.size()) {
          sensortime.push_back(WID->metParams->sensors[i]->TS[j]->time);
          sensortime_id.push_back(sensortime.size() - 1);
        }
      }
    }

    // Sort the timesteps from low to high (earliest to latest)
    mergeSortTime(sensortime, sensortime_id);

    // adding time stamps
    for (size_t t = 0; t < sensortime_id.size(); t++) {
      timestamp.push_back(sensortime[t]);
    }

    if (WID->simParams->totalTimeIncrements == 0) {
      totalTimeIncrements = timestamp.size();
    } else if (WID->simParams->totalTimeIncrements > timestamp.size()) {
      qes::log::warning() << "[WARNING] not enough timestamp in senors" << std::endl;
      totalTimeIncrements = timestamp.size();
    } else {
      totalTimeIncrements = WID->simParams->totalTimeIncrements;
    }

    // Adding halo to sensor location (if in QEScoord site_coord_flag==1)
    for (size_t i = 0; i < WID->metParams->sensors.size(); i++) {
      if (WID->metParams->sensors[i]->site_coord_flag == 1) {
        WID->metParams->sensors[i]->site_xcoord += WID->simParams->halo_x;
        WID->metParams->sensors[i]->site_ycoord += WID->simParams->halo_y;
      }
    }
  }

  // Pete could move to input param processing...
  validateSensors(WID);
  qes::log::info() << "[QES-WINDS]\t Sensors have been loaded (total sensors = " << WID->metParams->sensors.size() << ")." << std::endl;

  // /////////////////////////
  // Calculation of z0 domain info MAY need to move to WINDSInputData
  // or somewhere else once we know the domain size
  // /////////////////////////
  z0 = 0.1;
  z0_domain_u.resize(domain.nx() * domain.ny());
  z0_domain_v.resize(domain.nx() * domain.ny());
  if (WID->metParams->z0_domain_flag == 0)// Uniform z0 for the whole domain
  {
    for (auto i = 0; i < domain.nx(); i++) {
      for (auto j = 0; j < domain.ny(); j++) {
        id = i + j * domain.nx();
        z0_domain_u[id] = WID->metParams->sensors[0]->TS[0]->site_z0;
        z0_domain_v[id] = WID->metParams->sensors[0]->TS[0]->site_z0;
        z0 = WID->metParams->sensors[0]->TS[0]->site_z0;
      }
    }
  } else {
    for (auto i = 0; i < domain.nx() / 2; i++) {
      for (auto j = 0; j < domain.ny(); j++) {
        id = i + j * domain.nx();
        z0_domain_u[id] = 0.5;
        z0_domain_v[id] = 0.5;
      }
    }
    for (auto i = domain.nx() / 2; i < domain.nx(); i++) {
      for (auto j = 0; j < domain.ny(); j++) {
        id = i + j * domain.nx();
        z0_domain_u[id] = 0.1;
        z0_domain_v[id] = 0.1;
      }
    }
  }

  // /////////////////////////
  // Definition of the grid
  // /////////////////////////
  /*if (WID->simParams->verticalStretching == 0) {// Uniform vertical grid
    defineVerticalStretching(domain.dz());
  } else if (WID->simParams->verticalStretching == 1) {// Stretched vertical grid
    defineVerticalStretching(WID->simParams->dz_value);// Read in custom dz values and set them to dz_array
  }
  defineVerticalGrid();
  defineHorizontalGrid();
*/

  // defining ground solid cells (ghost cells below the surface)
  for (int j = 0; j < domain.ny() - 1; j++) {
    for (int i = 0; i < domain.nx() - 1; i++) {
      // long icell_cent = i + j * (domain.nx() - 1);
      icellflag[domain.cell(i, j, 0)] = 2;
    }
  }

  halo_index_x = (WID->simParams->halo_x / domain.dx());
  halo_x = halo_index_x * domain.dx();
  halo_index_y = (WID->simParams->halo_y / domain.dy());
  halo_y = halo_index_y * domain.dy();

  ////////////////////////////////////////////////////////
  //////              Apply Terrain code             /////
  ///////////////////////////////////////////////////////
  // Handle remaining Terrain processing components here
  ////////////////////////////////////////////////////////


  if (WID->simParams->DTE_heightField) {
    initializeTerrain(WID);
  }
  ///////////////////////////////////////////////////////
  //////   END END END of  Apply Terrain code       /////
  ///////////////////////////////////////////////////////

  // WINDS Input Data will have read in the specific types of
  // buildings, canopies, etc... but we need to merge all of that
  // onto a single vector of Building* -- this vector is called
  //
  // allBuildingsVector
  allBuildingsV.clear();// make sure there's nothing on it

  // After Terrain is processed, handle remaining processing of SHP
  // file data

  // SHP processing is done.  Now, consolidate all "buildings" onto
  // the same list...  this includes any canopies and building types
  // that were read in via the XML file...


  // Add all the Building* that were read in from XML to this list
  // too -- could be RectBuilding, PolyBuilding, whatever is derived
  // from Building in the end...
  if (WID->buildingsParams) {

    z0 = WID->buildingsParams->wallRoughness;

    if (WID->buildingsParams->upwindCavityFlag == 1) {
      lengthf_coeff = 2.0;
    } else {
      lengthf_coeff = 1.5;
    }

    // Determines how wakes behind buildings are calculated
    if (WID->buildingsParams->wakeFlag > 1) {
      cavity_factor = 1.1;
      wake_factor = 0.1;
    } else {
      cavity_factor = 1.0;
      wake_factor = 0.0;
    }


    auto buildingsetup_start = std::chrono::high_resolution_clock::now();// Start recording execution time
    //
    if (WID->buildingsParams->SHPData) {
    initializeShapefileBuildings(WID);
  }

    if (!WID->buildingsParams->buildings.empty()) {
      qes::log::info() << "[QES-WINDS]\t Consolidating building data..." << std::endl;
    }

    float corner_height, min_height;
    for (size_t i = 0; i < WID->buildingsParams->buildings.size(); i++) {
      if (!WID->buildingsParams->buildings[i])
        throw qes::InputError("Building input cannot be null");
      allBuildingsV.push_back(WID->buildingsParams->buildings[i]);
      int j = allBuildingsV.size() - 1;
      building_id.push_back(j);

      for (size_t pIdx = 0u; pIdx < allBuildingsV[j]->polygonVertices.size(); pIdx++) {
        allBuildingsV[j]->polygonVertices[pIdx].x_poly += WID->simParams->halo_x;
        allBuildingsV[j]->polygonVertices[pIdx].y_poly += WID->simParams->halo_y;
      }

      // Setting base height for buildings if there is a DEM file
      if (WID->simParams->DTE_heightField && WID->simParams->DTE_mesh) {
        // Get base height of every corner of building from terrain height
        min_height = WID->simParams->DTE_mesh->getHeight(allBuildingsV[j]->polygonVertices[0].x_poly,
                                                         allBuildingsV[j]->polygonVertices[0].y_poly);
        if (min_height < 0) {
          min_height = 0.0;
        }
        for (size_t lIdx = 1; lIdx < allBuildingsV[j]->polygonVertices.size(); lIdx++) {
          corner_height = WID->simParams->DTE_mesh->getHeight(allBuildingsV[j]->polygonVertices[lIdx].x_poly,
                                                              allBuildingsV[j]->polygonVertices[lIdx].y_poly);

          if (corner_height < min_height && corner_height >= 0.0) {
            min_height = corner_height;
          }
        }
        allBuildingsV[j]->base_height = min_height;
      }
      allBuildingsV[j]->ID = j;
      allBuildingsV[j]->setPolyBuilding(this);
      allBuildingsV[j]->setCellFlags(WID, this, j);
      effective_height.push_back(allBuildingsV[j]->height_eff);
    }

    // We want to sort ALL buildings here...  use the allBuildingsV to
    // do this... (remember some are canopies) so we may need a
    // virtual function in the Building class to get the appropriate
    // data for the sort.
    qes::log::info() << "[QES-WINDS]\t Sorting buildings by height..." << std::flush;
    mergeSort(effective_height, building_id);


    auto buildingsetup_finish = std::chrono::high_resolution_clock::now();// Finish recording execution time

    std::chrono::duration<float> elapsed_cut = buildingsetup_finish - buildingsetup_start;
    qes::log::info() << "\t\t elapsed time: " << elapsed_cut.count() << " s\n";
  }


  // Add all the Canopy* to it (they are derived from Building)
  canopy.reset();
  if (WID->vegetationParams) {
    canopy = std::make_unique<Canopy>(WID, this);
    canopy->setCanopyElements(WID, this);
  }

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

  /////////////////////////////////////////////////////////
  /////       Read coefficients from a file            ////
  /////////////////////////////////////////////////////////

  if (WID->simParams->readCoefficientsFlag == 1) {
    readCoefficients(WID);
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

  building_volume_frac.resize(numcell_cent, 1.0);
  terrain_volume_frac.resize(numcell_cent, 1.0);
  ni.resize(numcell_cent, 0.0);
  nj.resize(numcell_cent, 0.0);
  nk.resize(numcell_cent, 0.0);
  ti.resize(numcell_cent, 0.0);
  tj.resize(numcell_cent, 0.0);
  tk.resize(numcell_cent, 0.0);
  center_id.resize(numcell_cent, 1);
  wall_distance.resize(numcell_cent, 0.0);

  icellflag.resize(numcell_cent, 1);
  icellflag_initial.resize(numcell_cent, 1);
  icellflag_footprint.resize(numcell_cout_2d, 1);

  ibuilding_flag.resize(numcell_cent, -1);

  mixingLengths.resize(numcell_cent, 0.0);

  terrain.resize(numcell_cout_2d, 0.0);
  terrain_face_id.resize(domain.nx() * domain.ny(), 1);
  terrain_id.resize(numcell_cout_2d, 1);

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



void WINDSGeneralData::applyWindProfile(const WINDSInputData *WID, int timeIndex, int solveType)
{
  validateSensors(WID);
  if (!windProfiler || timeIndex < 0 || static_cast<size_t>(timeIndex) >= sensortime.size())
    throw qes::InputError("Invalid wind-profile time index or unprepared wind profiler");

  qes::log::info() << "[QES-WINDS]\t Applying Wind Profile...\n";

  u0.clear();
  v0.clear();
  w0.clear();
  u0.resize(domain.numFaceCentered(), 0.0);
  v0.resize(domain.numFaceCentered(), 0.0);
  w0.resize(domain.numFaceCentered(), 0.0);

  auto start_InputWindProfile = std::chrono::high_resolution_clock::now();// Finish recording execution time

  int num_sites = WID->metParams->sensors.size();
  time_id.clear();
  time_id.resize(num_sites, -1);
  // loop to find which timestep of each sensor is related to the running timestep of the code
  for (auto i = 0u; i < WID->metParams->sensors.size(); ++i) {
    for (auto j = 0u; j < WID->metParams->sensors[i]->TS.size(); ++j) {
      if (sensortime[timeIndex] == WID->metParams->sensors[i]->TS[j]->time) {
        time_id[i] = j;
      }
    }
  }

  windProfiler->interpolateWindProfile(WID, this);

  // FM -> CODE REMOVED TO WITH WINDPROFILER CLASSES // TO CLEAN
#if 0
  if (WID->simParams->wrfCoupling) {

    qes::log::info() << "Using WRF Coupling..." << std::endl;

    WRFInput *wrf_ptr = WID->simParams->wrfInputData;

    for (auto i = 0; i < wrf_ptr->fm_nx; i++) {
      for (auto j = 0; j < wrf_ptr->fm_ny; j++) {
        int index = i + j * wrf_ptr->fm_nx;
        WID->metParams->sensors[index]->site_coord_flag = 1;
        WID->metParams->sensors[index]->site_xcoord = (i + halo_index_x + 0.5) * dx;
        WID->metParams->sensors[index]->site_ycoord = (j + halo_index_y + 0.5) * dy;

        WID->metParams->sensors[index]->TS[0]->site_wind_dir.resize(wrf_ptr->ht_fmw.size());
        WID->metParams->sensors[index]->TS[0]->site_z_ref.resize(wrf_ptr->ht_fmw.size());
        WID->metParams->sensors[index]->TS[0]->site_U_ref.resize(wrf_ptr->ht_fmw.size());

        WID->metParams->sensors[index]->TS[0]->site_z0 = 0.1;
        WID->metParams->sensors[index]->TS[0]->site_one_overL = 0.0;

        // hack to make time equivalencies
        WID->metParams->sensors[index]->TS[0]->time = "2022-01-01T00:00:00";

        for (auto p = 0u; p < wrf_ptr->ht_fmw.size(); p++) {
          int id = index + p * wrf_ptr->fm_nx * wrf_ptr->fm_ny;
          WID->metParams->sensors[index]->TS[0]->site_z_ref[p] = wrf_ptr->ht_fmw[p];
          WID->metParams->sensors[index]->TS[0]->site_U_ref[p] = sqrt(pow(wrf_ptr->u0_fmw[id], 2.0) + pow(wrf_ptr->v0_fmw[id], 2.0));
          WID->metParams->sensors[index]->TS[0]->site_wind_dir[p] = 180 + (180 / pi) * atan2(wrf_ptr->v0_fmw[id], wrf_ptr->u0_fmw[id]);
        }
      }
    }

    // use the time Index of 0 (forcing it) because time series are not worked out with WRF well..
    WID->metParams->sensors[0]->inputWindProfile(WID, this, 0, solveType);
  } else {
    WID->metParams->sensors[0]->inputWindProfile(WID, this, timeIndex, solveType);
  }
#endif
  // FM -> CODE REMOVED TO WITH WINDPROFILER CLASSES // TO CLEAN

  max_velmag = 0.0;
  for (auto i = 0; i < domain.nx(); i++) {
    for (auto j = 0; j < domain.ny(); j++) {
      // int icell_face = i + j * nx + (nz - 2) * nx * ny;
      long icell_face = domain.face(i, j, domain.nz() - 2);
      max_velmag = MAX_S(max_velmag, sqrt(pow(u0[icell_face], 2.0) + pow(v0[icell_face], 2.0)));
    }
  }
  max_velmag *= 1.2;

  auto end_InputWindProfile = std::chrono::high_resolution_clock::now();// Finish recording execution time

  std::chrono::duration<float> elapsed_InputWindProfile = end_InputWindProfile - start_InputWindProfile;
  qes::log::info() << "\t\t elapsed time: " << elapsed_InputWindProfile.count() << " s\n";
  return;
}

void WINDSGeneralData::applyParametrizations(const WINDSInputData *WID)
{

  auto start_param = std::chrono::high_resolution_clock::now();// Start recording execution time
  qes::log::info() << "[QES-WINDS]\t Applying parameterizations...\n";

  // ///////////////////////////////////////
  // Generic Parameterization Related Stuff
  // ///////////////////////////////////////
  if (canopy) {
    qes::log::info() << "[QES-WINDS]\t Applying vegetation parameterization...\n";
    canopy->applyCanopyVegetation(this);
  }

  if (WID->buildingsParams) {
    ///////////////////////////////////////////
    //   Upwind Cavity Parameterization     ///
    ///////////////////////////////////////////
    if (WID->buildingsParams->upwindCavityFlag > 0) {
      qes::log::info() << "[QES-WINDS]\t Applying upwind cavity parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->upwindCavity(WID, this);
      }
    }

    //////////////////////////////////////////////////
    //   Far-Wake and Cavity Parameterizations     ///
    //////////////////////////////////////////////////
    if (WID->buildingsParams->wakeFlag > 0) {
      qes::log::info() << "[QES-WINDS]\t Applying wake behind building parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->polygonWake(WID, this, building_id[i]);
      }
    }

    ///////////////////////////////////////////
    //   Street Canyon Parameterization     ///
    ///////////////////////////////////////////
    if (WID->buildingsParams->streetCanyonFlag == 1) {
      qes::log::info() << "[QES-WINDS]\t Applying street canyon parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->streetCanyon(this);
      }
    } else if (WID->buildingsParams->streetCanyonFlag == 2) {
      qes::log::info() << "[QES-WINDS]\t Applying street canyon parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->streetCanyonModified(this);
      }
    }

    ///////////////////////////////////////////
    //      Sidewall Parameterization       ///
    ///////////////////////////////////////////
    if (WID->buildingsParams->sidewallFlag > 0) {
      qes::log::info() << "[QES-WINDS]\t Applying sidewall parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->sideWall(WID, this);
      }
    }


    ///////////////////////////////////////////
    //      Rooftop Parameterization        ///
    ///////////////////////////////////////////
    if (WID->buildingsParams->rooftopFlag > 0) {
      qes::log::info() << "[QES-WINDS]\t Applying rooftop parameterization...\n";
      for (size_t i = 0; i < allBuildingsV.size(); i++) {
        allBuildingsV[building_id[i]]->rooftop(WID, this);
      }
    }
  }

  // ///////////////////////////////////////
  // Generic Parameterization Related Stuff
  // ///////////////////////////////////////
  if (canopy) {
    qes::log::info() << "[QES-WINDS]\t Applying canopy wake parameterization...\n";
    canopy->applyCanopyWake(this);
  }

  ///////////////////////////////////////////
  //         Street Intersection          ///
  ///////////////////////////////////////////
  /*if (WID->buildingsParams->streetCanyonFlag > 0 && WID->buildingsParams->streetIntersectionFlag > 0 && allBuildingsV.size() > 0)
    {
    qes::log::info() << "Applying Blended Region Parameterization...\n";
    allBuildingsV[0]->streetIntersection (WID, this);
    allBuildingsV[0]->poisson (WID, this);
    qes::log::info() << "Blended Region Parameterization done...\n";
    }*/


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

QEStime WINDSGeneralData::nextTimeInstance(const int &index, const float &duration)
{
  QEStime endTime = timestamp[index];
  if (totalTimeIncrements == 1) {
    endTime = timestamp[index] + duration;
  } else if (index == totalTimeIncrements - 1) {
    endTime = timestamp[index] + (float)(timestamp[index] - timestamp[index - 1]);
  } else {
    endTime = timestamp[index + 1];
  }
  return endTime;
}

void WINDSGeneralData::printTimeProgress(int index)
{
  qes::log::info() << "[QES-WINDS] Time: " << timestamp.at(index) << std::endl;
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

void WINDSGeneralData::mergeSortTime(std::vector<QEStime> &sensortime, std::vector<int> &sensortime_id)
{
  // if the size of the array is 1, it is already sorted
  if (sensortime_id.size() == 1) {
    return;
  }

  if (sensortime_id.size() > 1) {
    // make left and right sides of the data
    std::vector<QEStime> sensortime_L, sensortime_R;
    std::vector<int> sensortime_id_L, sensortime_id_R;
    sensortime_L.resize(sensortime_id.size() / 2);
    sensortime_R.resize(sensortime_id.size() - sensortime_id.size() / 2);
    sensortime_id_L.resize(sensortime_id.size() / 2);
    sensortime_id_R.resize(sensortime_id.size() - sensortime_id.size() / 2);

    // copy data from the main data set to the left and right children
    size_t lC = 0, rC = 0;
    for (size_t i = 0; i < sensortime_id.size(); i++) {
      if (i < sensortime_id.size() / 2) {
        sensortime_L[lC] = sensortime[i];
        sensortime_id_L[lC++] = sensortime_id[i];

      } else {
        sensortime_R[rC] = sensortime[i];
        sensortime_id_R[rC++] = sensortime_id[i];
      }
    }

    // recursively sort the children
    mergeSortTime(sensortime_L, sensortime_id_L);
    mergeSortTime(sensortime_R, sensortime_id_R);

    // compare the sorted children to place the data into the main array
    lC = rC = 0;
    for (size_t i = 0; i < sensortime_id.size(); i++) {
      if (rC == sensortime_R.size() || (lC != sensortime_L.size() && sensortime_L[lC] < sensortime_R[rC])) {
        sensortime[i] = sensortime_L[lC];
        sensortime_id[i] = sensortime_id_L[lC++];
      } else {
        sensortime[i] = sensortime_R[rC];
        sensortime_id[i] = sensortime_id_R[rC++];
      }
    }
  }

  return;
}


float WINDSGeneralData::canopyBisection(float ustar, float z0, float canopy_top, float canopy_atten, float vk, float psi_m)
{
  int iter;
  float uhc, d, d1, d2;
  float tol, fnew, fi;

  tol = z0 / 100;
  fnew = tol * 10;

  d1 = z0;
  d2 = canopy_top;
  d = (d1 + d2) / 2;

  uhc = (ustar / vk) * (log((canopy_top - d1) / z0) + psi_m);
  fi = ((canopy_atten * uhc * vk) / ustar) - canopy_top / (canopy_top - d1);

  if (canopy_atten > 0) {
    iter = 0;
    while (iter < 200 && abs(fnew) > tol && d < canopy_top && d > z0) {
      iter += 1;
      d = (d1 + d2) / 2;
      uhc = (ustar / vk) * (log((canopy_top - d) / z0) + psi_m);
      fnew = ((canopy_atten * uhc * vk) / ustar) - canopy_top / (canopy_top - d);
      if (fnew * fi > 0) {
        d1 = d;
      } else if (fnew * fi < 0) {
        d2 = d;
      }
    }
    if (d > canopy_top) {
      d = 10000;
    }

  } else {
    d = 0.99 * canopy_top;
  }

  return d;
}

void WINDSGeneralData::validateSensors(const WINDSInputData *WID) const
{
  if (!WID || !WID->simParams || !WID->metParams || WID->metParams->sensors.empty())
    throw qes::InputError("At least one wind sensor is required");
  for (const auto *sensor : WID->metParams->sensors) {
    if (!sensor || sensor->TS.empty())
      throw qes::InputError("Each wind sensor needs a non-empty time series");
    if (sensor->site_coord_flag == 1 && !WID->hrrrInput) {
      const float x = sensor->site_xcoord, y = sensor->site_ycoord;
      if (!std::isfinite(x) || !std::isfinite(y) || x < 0 || y < 0
          || x >= (domain.nx() - 1) * domain.dx()
          || y >= (domain.ny() - 1) * domain.dy())
        throw qes::InputError("Wind sensor must be inside the horizontal domain");
    }
#if !QES_ENABLE_IO
    if (sensor->site_coord_flag != 1)
      throw qes::UnsupportedFeature("The in-memory core requires local sensor coordinates");
#endif
    for (const auto *series : sensor->TS) {
      if (!series || series->site_z_ref.empty()
          || series->site_z_ref.size() != series->site_U_ref.size()
          || series->site_z_ref.size() != series->site_wind_dir.size())
        throw qes::InputError("Sensor heights, speeds and directions must have matching non-zero lengths");
      if (!std::isfinite(series->site_z0) || series->site_z0 <= 0
          || !std::isfinite(series->site_one_overL))
        throw qes::InputError("Sensor roughness must be positive and stability must be finite");
      for (size_t i = 0; i < series->site_z_ref.size(); ++i) {
        if (!std::isfinite(series->site_z_ref[i]) || series->site_z_ref[i] <= 0
            || !std::isfinite(series->site_U_ref[i]) || series->site_U_ref[i] < 0
            || !std::isfinite(series->site_wind_dir[i]))
          throw qes::InputError("Sensor heights must be positive; speeds non-negative; all profile values finite");
      }
    }
  }
}
