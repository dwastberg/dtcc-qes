#pragma once

// Bridge only: bindings include the QES-free wind_config.h instead.
#include "wind_config.h"

class TURBParams;
class TURBGeneralData;

namespace dtcc_qes {
void configure_turbulence(TURBParams &, const TurbulenceSettings &);
void check_turbulence_margin(const TURBGeneralData &, const GridConfig &);
TurbulenceData turbulence_fields(const TURBGeneralData &, const GridConfig &);
}
