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


#include "WINDSInputData.h"
#include "util/UnsupportedFeature.h"

void SimulationParameters::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

SimulationParameters::~SimulationParameters() = default;

void BuildingsParams::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

void VegetationParams::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

void MetParams::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

void HRRRInput::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

void TURBParams::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

void WINDSInputData::parseValues()
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

WINDSInputData::WINDSInputData(const std::string)
{
  throw qes::UnsupportedFeature("XML input requires QES_ENABLE_IO=ON");
}

Sensor::Sensor(const std::string)
{
  throw qes::UnsupportedFeature("Sensor files require QES_ENABLE_IO=ON");
}
