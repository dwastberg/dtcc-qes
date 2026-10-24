#include "qes_inputs.h"
#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#include "fixture.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace dtcc_qes;

static void require(bool condition, const char *message)
{
  if (!condition) throw std::runtime_error(message);
}

struct FluxStats {
  double max = 0, rms = 0, top_band_max = 0;
  std::size_t count = 0;
};

// Conservative six-face flux, not a derivative of cell-centred averages.
// Wall::solverCoefficients scales the open-face fractions by spacing squared;
// recover those fractions and divide net volumetric flux by cell volume.
static FluxStats flux(const WINDSGeneralData &data, bool initial)
{
  const auto &d = data.domain;
  const auto &u = initial ? data.u0 : data.u;
  const auto &v = initial ? data.v0 : data.v;
  const auto &w = initial ? data.w0 : data.w;
  FluxStats stats;
  double sum_squared = 0;
  // Outer x/y cells have prescribed boundary conditions. The last solved z
  // band has an uncorrected upper w face in QES 2.3.1: report it separately.
  for (int k = 1; k < fixture::nz; ++k)
    for (int j = 1; j < fixture::ny - 1; ++j)
      for (int i = 1; i < fixture::nx - 1; ++i) {
        const auto c = d.cell(i, j, k), f = d.face(i, j, k);
        if (data.icellflag[c] == 0 || data.icellflag[c] == 2) continue;
        const double dx = d.dx(), dy = d.dy(), dz = d.dz_array[k];
        const double east = data.e[c] * dx * dx, west = data.f[c] * dx * dx;
        const double north = data.g[c] * dy * dy, south = data.h[c] * dy * dy;
        const double above = data.m[c] * dz * 0.5 * (dz + d.dz_array[k + 1]);
        const double below = data.n[c] * dz * 0.5 * (dz + d.dz_array[k - 1]);
        const double net = (east * u[d.faceAdd(f, 1, 0, 0)] - west * u[f]) * dy * dz
                         + (north * v[d.faceAdd(f, 0, 1, 0)] - south * v[f]) * dx * dz
                         + (above * w[d.faceAdd(f, 0, 0, 1)] - below * w[f]) * dx * dy;
        const double divergence = net / (dx * dy * dz);
        require(std::isfinite(divergence), "Non-finite staggered flux");
        if (k == fixture::nz - 1) {
          stats.top_band_max = std::max(stats.top_band_max, std::abs(divergence));
        } else {
          stats.max = std::max(stats.max, std::abs(divergence));
          sum_squared += divergence * divergence;
          ++stats.count;
        }
      }
  stats.rms = std::sqrt(sum_squared / stats.count);
  return stats;
}

static void check(bool with_building, bool report)
{
  GridConfig grid;
  grid.nx = fixture::nx; grid.ny = fixture::ny; grid.nz = fixture::nz;
  grid.cell_size = fixture::cell_size;
  ModelSettings model;
  model.sensor_x = fixture::sensor_x; model.sensor_y = fixture::sensor_y;
  model.roughness_length = fixture::roughness;
  BuildingArrays geometry{{}, {0}, {}, {}, {}};
  if (with_building) {
    for (const auto &vertex : fixture::vertices)
      geometry.vertices.insert(geometry.vertices.end(), {vertex[0], vertex[1]});
    geometry.offsets.push_back(geometry.vertices.size() / 2);
    geometry.ids = {0}; geometry.heights = {fixture::height}; geometry.base_heights = {fixture::base_height};
  }
  QESInputs inputs(grid, model, geometry);
  inputs.set_condition({fixture::speed, fixture::direction, fixture::reference_height});
  WINDSGeneralData data(&inputs.input, qes::Domain(inputs.simulation.domain, inputs.simulation.grid), CPU_Type);
  data.resetICellFlag();
  data.applyWindProfile(&inputs.input, 0, CPU_Type);
  data.applyParametrizations(&inputs.input);
  const auto before = flux(data, true);
  std::unique_ptr<Solver> solver(SolverFactory::create(CPU_Type, data.domain, fixture::tolerance));
  solver->resetLambda();
  const auto diagnostics = solver->solve(&data, fixture::max_iterations);
  const auto after = flux(data, false);
  require(diagnostics.converged, "Physics fixture did not converge");
  require(after.count > 1000, "Flux check did not cover the solved interior");
  require(after.max < 1e-5 && after.rms < 1e-6, "Interior staggered flux exceeds the validated bound (s^-1)");
  if (with_building) {
    require(before.rms > 1e-3 && after.rms < before.rms * 1e-3, "Solver did not reduce divergent initial flux");
    require(after.top_band_max > 1e-3 && after.top_band_max < 1.6e-2,
            "Legacy prescribed-top flux band changed; review against the standalone baseline");
  } else {
    require(after.max == 0 && after.top_band_max == 0, "Flat profile has nonzero flux");
  }
  // The numerical flux assertion must detect a broken staggered component.
  data.u[data.domain.face(10, 10, 2)] += 0.1f;
  require(flux(data, false).max > 1e-2, "Flux check missed a perturbed face");
  if (report)
    std::cout << (with_building ? "building" : "flat") << ": initial_rms=" << before.rms
              << " interior_max=" << after.max << " interior_rms=" << after.rms
              << " top_band_max=" << after.top_band_max << " s^-1\n";
}

int main(int argc, char **)
{
  check(false, argc > 1);
  check(true, argc > 1);
}
