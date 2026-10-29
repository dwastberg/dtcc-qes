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

/** @file LocalMixingSerial.h */

#pragma once

#include "LocalMixing.h"

class WINDSInputData;
class WINDSGeneralData;

/**
 * Serial distance to exposed stair-step grid faces, limited by the vertical
 * terrain distance, with a physical-height transition back to that seed.
 * This uses the voxelized geometry, not the original polygon surfaces.
 * Setup cost grows with exposed faces and their candidate fluid cells;
 * larger-domain performance must be measured before choosing it as a default.
 */
class LocalMixingSerial : public LocalMixing
{
public:
  void defineMixingLength(const WINDSInputData *, WINDSGeneralData *) override;
};
