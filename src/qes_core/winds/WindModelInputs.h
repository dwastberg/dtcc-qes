#pragma once

/** @file WindModelInputs.h
 * @brief Plain in-memory inputs of the wind and turbulence models.
 *
 * These replace the former XML parameter classes (SimulationParameters,
 * MetParams, Sensor, TimeSeries, BuildingsParams and TURBParams). Field names
 * follow those parameters so the model code reads as before.
 */

#include "util/PolygonVertex.h"
#include "util/Vector3Float.h"
#include <optional>
#include <vector>

/** One extruded polygon building: a closed, clockwise ring in the local frame. */
struct BuildingFootprint
{
  std::vector<polyVert> vertices;
  float height = 0; /**< metres above the base */
  float base_height = 0; /**< metres above the ground */
};

/** Empirical building parameterizations (formerly BuildingsParams). */
struct BuildingParameterizations
{
  float wallRoughness = 0.001; /**< wall roughness length (m) */
  int rooftopFlag = 1; /**< 0 none, 1 log profile, 2 vortex */
  int upwindCavityFlag = 2; /**< 0 none, 1 Rockle, 2 MVP, 3 HMVP */
  int streetCanyonFlag = 1; /**< 0 none, 1 Roeckle with Fackrel, 2 modified */
  int wakeFlag = 2; /**< 0 none, 1 Rockle, 2 modified Rockle */
  int highRiseFlag = 0; /**< 0 off, 1 on */
  int sidewallFlag = 1; /**< 0 off, 1 on */
};

/** Logarithmic inflow profile from one sensor (formerly Sensor and TimeSeries). */
struct InflowCondition
{
  float site_xcoord = 0, site_ycoord = 0; /**< sensor position in the local frame (m) */
  float site_U_ref = 0; /**< speed at the reference height (m/s) */
  float site_z_ref = 10; /**< reference height (m) */
  float site_wind_dir = 270; /**< direction the wind comes from (degrees clockwise from north) */
  float site_z0 = 0.1; /**< roughness length (m) */
  float site_one_overL = 0; /**< inverse Obukhov length (1/m); zero is neutral */
};

/** QES-Turb settings (formerly TURBParams and the grid's stretching flag). */
struct TurbulenceConfig
{
  int methodLocalMixing = 0; /**< 0 height, 1 serial wall distance, 3 OptiX */
  int mlSamplesPerAirCell = 0; /**< OptiX samples per air cell */
  std::optional<Vector3Float> sigConst; /**< sigma/u* constants; QES defaults when empty */
  bool flagNonLocalMixing = false;
  int buildingWallFlag = 2, terrainWallFlag = 2; /**< 1 log law, 2 finite differences */
  float turbUpperBound = 20.0; /**< cap on stresses and TKE in units of u*^2 */
  float backgroundMixing = 0.0;
  int verticalStretching = 0; /**< 1 selects the nonuniform vertical derivatives */
  float site_z0 = 0.1; /**< reference roughness when there are no buildings (m) */
};
