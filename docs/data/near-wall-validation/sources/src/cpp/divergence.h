#pragma once

#include "wind_config.h"

class WINDSGeneralData;

namespace dtcc_qes {
// Six-face conservative flux / volume (s^-1), using scaled open-face coefficients.
// Excludes prescribed lateral cells and the highest physical layer. The last
// solved band has an uncorrected upper w face and is reported separately.
DivergenceStats divergence_stats(const WINDSGeneralData &, bool initial = false);
}
