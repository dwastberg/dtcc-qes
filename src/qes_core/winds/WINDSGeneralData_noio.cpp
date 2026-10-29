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


#include "WINDSGeneralData.h"
#include "util/UnsupportedFeature.h"

void WINDSGeneralData::initializeWRFSensors(const WINDSInputData *WID)
{
  throw qes::UnsupportedFeature("initializeWRFSensors requires QES_ENABLE_IO=ON");
}

void WINDSGeneralData::initializeTerrain(const WINDSInputData *WID)
{
  throw qes::UnsupportedFeature("initializeTerrain requires QES_ENABLE_IO=ON");
}

void WINDSGeneralData::initializeShapefileBuildings(const WINDSInputData *WID)
{
  throw qes::UnsupportedFeature("initializeShapefileBuildings requires QES_ENABLE_IO=ON");
}

void WINDSGeneralData::readCoefficients(const WINDSInputData *WID)
{
  throw qes::UnsupportedFeature("readCoefficients requires QES_ENABLE_IO=ON");
}

WINDSGeneralData::WINDSGeneralData(const std::string &inputFile)
  : domain(inputFile)
{
  throw qes::UnsupportedFeature("NetCDF input requires QES_ENABLE_IO=ON");
}

void WINDSGeneralData::loadNetCDFData(int stepin)
{
  throw qes::UnsupportedFeature("NetCDF input requires QES_ENABLE_IO=ON");
}

void WINDSGeneralData::downscaleHRRR(const WINDSInputData *WID)
{
  throw qes::UnsupportedFeature("NetCDF input requires QES_ENABLE_IO=ON");
}
