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


#pragma once

#include "util/ParseInterface.h"
class ESRIShapefile;

#include "Building.h"

#include "CanopyElement.h"
#include "CanopyHomogeneous.h"
#include "CanopyIsolatedTree.h"
#include "CanopyWindbreak.h"
#include "CanopyROC.h"

#include "WINDSInputData.h"
#include "WINDSGeneralData.h"


class VegetationParams : public ParseInterface
{
private:
public:
  std::vector<Building *> canopies; /**< :document this: */

  int wakeFlag = 1; /**< :document this: */


  // SHP File parameters
  std::string shpFile; /**< :document this: */
  std::string shpTreeLayerName; /**< :document this: */
  ESRIShapefile *SHPData = nullptr; /**< :document this: */

  std::vector<std::vector<polyVert>> shpPolygons; /**< :document this: */
  std::map<std::string, std::vector<float>> shpFeatures; /**< :document this: */

  void parseValues() override;
};
