#include "turbulence.h"
#include "model_inputs.h"
#include "stress_validity.h"
#include "winds/TURBGeneralData.h"
#include "winds/WINDSGeneralData.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace dtcc_qes {
void configure_turbulence(TurbulenceConfig &params, const TurbulenceSettings &settings)
{
  if (settings.mixing_length_method != 0 && settings.mixing_length_method != 1)
    throw std::invalid_argument("Unsupported turbulence mixing-length method: "
      + std::to_string(settings.mixing_length_method) + "; supported methods are 0 (height) and 1 (wall distance)");
  // Method 1 passed Task 1B's bounds, height-invariant and geometry gates.
  // Keep every other model choice at the audited QES defaults.
  params.methodLocalMixing = settings.mixing_length_method;
  params.sigConst.reset();
  params.flagNonLocalMixing = false;
  params.buildingWallFlag = params.terrainWallFlag = 2;
  params.turbUpperBound = 20;
  params.backgroundMixing = 0;
}

void check_turbulence_margin(const ModelInputs &inputs, const WINDSGeneralData &wind,
                             const GridConfig &grid)
{
  const auto &faces = wind.domain.z_face;
  // Match TURBGeneralData's float32 mean in QES's sorted building order.
  // Check before constructing turbulence: its own reference-plane guards
  // otherwise throw before we can explain how to obtain a sufficient grid.
  float reference;
  if (wind.allBuildingsV.empty()) {
    reference = 100.0 * inputs.turbulence.site_z0;
  } else {
    float mean = 0;
    for (int id : wind.building_id) mean += wind.allBuildingsV[id]->H;
    mean /= float(wind.allBuildingsV.size());
    reference = 3.0 * mean;
  }
  const auto index = std::lower_bound(faces.begin(), faces.end(), reference) - faces.begin();
  if (grid.nz >= 3 && index <= grid.nz - 2 && faces.back() >= 15) return;

  std::ostringstream message;
  message << std::setprecision(std::numeric_limits<float>::max_digits10);
  message << "Turbulence domain top " << faces.back() << " m is insufficient for zRef "
          << reference << " m and the 15 m rotation reference; layer margin requires two physical layers "
          << "above the sampled layer (reference index " << index << ", maximum " << grid.nz - 2 << "). ";
  // Report an actual sufficient top for an unchanged prefix with a constant
  // tail, using QES float32 accumulation. Never suggest zRef+3*min(dz) as a
  // sufficient top for an arbitrary nonuniform grid. This check never grows it.
  auto extended = faces;
  int layers = grid.nz;
  const float thickness = static_cast<float>(grid.dz_layers.empty() ? grid.cell_size : grid.dz_layers.back());
  const auto has_margin = [&] {
    return layers >= 3 && extended[layers-2] >= reference && extended.back() >= 15;
  };
  std::string limit;
  while (!has_margin()) {
    if (layers >= 10000) { limit = "10000-layer limit"; break; }
    if (std::int64_t(grid.nx) * grid.ny * (layers+1) > grid.max_cells) {
      limit = "max_cells limit"; break;
    }
    if (std::int64_t(grid.nx+1) * (grid.ny+1) * (layers+3) > std::numeric_limits<int>::max()) {
      limit = "native index limit"; break;
    }
    const float top = extended.back() + thickness;
    if (!std::isfinite(top) || top <= extended.back()) {
      limit = "float32 coordinate progress limit"; break;
    }
    const float previous_centre = 0.5f * (extended[extended.size()-2] + extended.back());
    const float centre = 0.5f * (extended.back() + top);
    if (!std::isfinite(centre) || centre <= previous_centre) {
      limit = "float32 cell-centre progress limit"; break;
    }
    extended.push_back(top);
    ++layers;
  }
  if (limit.empty())
    message << "Appending " << layers-grid.nz << " layers of " << thickness
            << " m while preserving the existing layers gives a sufficient top of " << extended.back() << " m.";
  else
    message << "A constant-thickness tail of " << thickness << " m cannot satisfy the margin within the " << limit << ".";
  throw std::invalid_argument(message.str());
}

TurbulenceData turbulence_fields(const TURBGeneralData &turb, const GridConfig &grid)
{
  if (grid.nx != turb.domain.nx()-1 || grid.ny != turb.domain.ny()-1 || grid.nz != turb.domain.nz()-2)
    throw std::invalid_argument("Turbulence extraction grid does not match the native domain");
  const auto count = std::size_t(grid.nx) * grid.ny * grid.nz;
  const auto plane = std::size_t(grid.nx) * grid.ny;
  const float nan = std::numeric_limits<float>::quiet_NaN();
  TurbulenceData result;
  result.stress.assign(6*count, nan);
  result.tke.assign(count, nan);
  result.co_eps.assign(count, nan);
  result.mixing_length.assign(count, nan);
  result.state.assign(count, 0);
  result.stress_valid.assign(count, 0);
  result.friction_velocity = turb.getFrictionVelocity();
  result.reference_speed = turb.getReferenceSpeed();
  result.reference_height = turb.getReferenceHeight();
  result.roughness_length = turb.getRoughnessLength();
  result.displacement_height = turb.getDisplacementHeight();
  result.upper_bound = turb.getUpperBound();
  result.rotation_fallback_columns = turb.getRotationFallbackColumns();
  // Match QES's float32 operation order. Zero bound in calm wind is not a cap.
  const float bound = turb.getUpperBound() * turb.getFrictionVelocity() * turb.getFrictionVelocity();
  for (int source : turb.icellfluid) {
    // The wind mapping removes only the ground ghost layer: (k-1,j,i).
    const auto cell = std::size_t(source) - plane;
    const StressTensor stress{turb.txx[source], turb.txy[source], turb.txz[source],
                              turb.tyy[source], turb.tyz[source], turb.tzz[source]};
    std::copy(stress.begin(), stress.end(), result.stress.begin()+6*cell);
    result.tke[cell] = turb.tke[source];
    result.co_eps[cell] = turb.CoEps[source];
    result.mixing_length[cell] = turb.Lm[source];
    bool capped = false;
    if (bound > 0) {
      capped = turb.tke[source] >= bound;
      for (float component : stress) capped = capped || std::abs(component) >= bound;
    }
    result.state[cell] = capped ? 2 : 1;
    result.stress_valid[cell] = stress_validity(stress).valid;
    ++result.computed_cells;
    if (capped) ++result.capped_cells;
    if (!result.stress_valid[cell]) ++result.invalid_stress_cells;
  }
  return result;
}
}
