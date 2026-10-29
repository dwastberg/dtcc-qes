#pragma once

// Bridge only: bindings include the QES-free wind_config.h instead.
#include "wind_config.h"

struct TurbulenceConfig;
class TURBGeneralData;
class WINDSGeneralData;

namespace dtcc_qes {
struct ModelInputs;
void configure_turbulence(TurbulenceConfig &, const TurbulenceSettings &);
void check_turbulence_margin(const ModelInputs &, const WINDSGeneralData &, const GridConfig &);
TurbulenceData turbulence_fields(const TURBGeneralData &, const GridConfig &);
}
