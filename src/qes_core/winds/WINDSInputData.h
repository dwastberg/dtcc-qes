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
 ***************************************************************************/

/** @file WINDSInputData.h */

#pragma once

/*
 * A collection of data read from an XML. This contains
 * all root level information extracted from the xml.
 */

#include "util/ParseInterface.h"


#include "SimulationParameters.h"
#include "FileOptions.h"
#include "MetParams.h"
#include "BuildingsParams.h"
#include "VegetationParams.h"

class Fires;

#include "TURBParams.h"
#include "HRRRInput.h"

/**
 * @class WINDSInputData
 * @brief Collection of data read from an XML.
 *
 * Contains all root level information extracted from the xml
 *
 * @sa ParseInterface
 */
class WINDSInputData : public ParseInterface
{
public:
  SimulationParameters *simParams = nullptr; /**< :document this: */
  FileOptions *fileOptions = nullptr; /**< :document this: */
  MetParams *metParams = nullptr; /**< :document this: */
  TURBParams *turbParams = nullptr; /**< :document this: */
  BuildingsParams *buildingsParams = nullptr; /**< :document this: */
  VegetationParams *vegetationParams = nullptr; /**< :document this: */

  HRRRInput *hrrrInput = nullptr; /**< :HRRR input class instance: */

  Fires *fires = nullptr; /**< :document this: */

  // In-memory fields and their nested pointer vectors are non-owning views.
  // The caller owns each input (including buildings, sensors and time series)
  // and must keep them alive until WINDSGeneralData has been destroyed.
  ~WINDSInputData() override = default;

  WINDSInputData()
  {
    fileOptions = 0;
    metParams = 0;
    turbParams = 0;
    buildingsParams = 0;
    vegetationParams = 0;
    hrrrInput = 0;
    fires = 0;
  }

  explicit WINDSInputData(const std::string fileName);

  /**
   * :document this:
   */
  void parseValues() override;
};
