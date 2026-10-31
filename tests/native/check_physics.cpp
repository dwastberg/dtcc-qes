#include "solver/solver.h"
#include "model_inputs.h"
#include "divergence.h"
#include <limits>
#include "winds/WINDSGeneralData.h"
#include "fixture.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace dtcc_qes;

using namespace dtcc_qes::solver;

static void require(bool condition, const char *message)
{
  if (!condition) throw std::runtime_error(message);
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
  ModelInputs inputs(grid, model, geometry);
  inputs.set_condition({fixture::speed, fixture::direction, fixture::reference_height});
  WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.resetICellFlag();
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  const PoissonOperator op(data);
  const auto before = divergence_stats(data, op, true);
  SolverState<float> solver(op, fixture::tolerance);
  const auto diagnostics = solve_wind(solver, data, fixture::max_iterations);
  const auto after = divergence_stats(data, op);
  require(diagnostics.converged, "Physics fixture did not converge");
  require(after.cells > 1000, "Flux check did not cover the solved interior");
  require(after.interior_max < 1e-5 && after.interior_rms < 1e-6, "Interior staggered flux exceeds the validated bound (s^-1)");
  if (with_building) {
    require(before.interior_rms > 1e-3 && after.interior_rms < before.interior_rms * 1e-3, "Solver did not reduce divergent initial flux");
    require(after.top_band_max > 1e-3 && after.top_band_max < 1.6e-2,
            "Legacy prescribed-top flux band changed; review against the standalone baseline");
  } else {
    require(after.interior_max == 0 && after.top_band_max == 0, "Flat profile has nonzero flux");
  }
  // The numerical flux assertion must detect a broken staggered component.
  data.u[data.domain.face(10, 10, 2)] += 0.1f;
  require(divergence_stats(data, op).interior_max > 1e-2, "Flux check missed a perturbed face");
  if (report)
    std::cout << (with_building ? "building" : "flat") << ": initial_rms=" << before.interior_rms
              << " interior_max=" << after.interior_max << " interior_rms=" << after.interior_rms
              << " top_band_max=" << after.top_band_max << " s^-1\n";
}

static void injection(bool serial, bool vertical, float spacing, bool report)
{
  GridConfig grid;
  grid.nx = grid.ny = 24; grid.nz = 16; grid.cell_size = spacing;
  ModelSettings model;
  model.sensor_x = model.sensor_y = 2.5 * spacing;
  ModelInputs inputs(grid, model, BuildingArrays{{}, {0}, {}, {}, {}});
  inputs.set_condition({0, 270, 10});
  WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  (vertical ? data.w0 : data.u0)[data.domain.face(12, 12, 6)] = 0.1f;
  const PoissonOperator op(data);
  const auto before = divergence_stats(data, op, true);
  SolverState<float> solver(op, 2e-7f, serial ? SweepOrder::Lexicographic : default_order());
  const auto diagnostics = solve_wind(solver, data, 20000);
  const auto after = divergence_stats(data, op);
  require(before.interior_max > 0.02, "Injection did not create divergence");
  require(after.interior_max < 1e-6, "Solver failed to remove injected divergence");
  if (report)
    std::cout << "injection " << (serial ? "serial" : "factory") << " "
              << (vertical ? "w" : "u") << " dz=" << spacing
              << " before=" << before.interior_max << " after=" << after.interior_max
              << " top=" << after.top_band_max << " iterations=" << diagnostics.iterations << "\n";
}

// Independent finite-volume oracle: it uses physical face velocities and known
// unobstructed areas, never the coefficient recovery used by divergence_stats.
static void diagnostic_checks()
{
  GridConfig grid;
  grid.nx = 7; grid.ny = 6; grid.nz = 5;
  grid.dz_layers = {0.5, 0.75, 1.0, 1.5, 2.0};
  ModelSettings model;
  model.sensor_x = model.sensor_y = 1;
  ModelInputs inputs(grid, model, BuildingArrays{{}, {0}, {}, {}, {}});
  const auto domain = make_domain(inputs);
  WINDSGeneralData data(domain, inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  const auto &d = data.domain;
  for (int k = 0; k < d.nz(); ++k)
    for (int j = 0; j < d.ny(); ++j)
      for (int i = 0; i < d.nx(); ++i) {
        data.u0[d.face(i, j, k)] = 0.125f * i;
        data.v0[d.face(i, j, k)] = 0.25f * j;
        data.w0[d.face(i, j, k)] = d.z_face[k] * d.z_face[k];
      }
  double maximum = 0, weighted_square = 0, volume_sum = 0, top = 0;
  for (int k = 1; k < grid.nz; ++k) {
    const double expected = 0.125 / d.dx() + 0.25 / d.dy() + 2 * d.z[k];
    if (k == grid.nz - 1) { top = expected; continue; }
    maximum = std::max(maximum, expected);
    const double volume = d.dx() * d.dy() * d.dz_array[k];
    weighted_square += volume * expected * expected;
    volume_sum += volume;
  }
  const PoissonOperator op(data);
  const auto stats = divergence_stats(data, op, true);
  require(std::abs(stats.interior_max - maximum) < 2e-6, "Divergence maximum differs from independent oracle");
  require(std::abs(stats.interior_rms - std::sqrt(weighted_square / volume_sum)) < 2e-6,
          "Divergence RMS does not use actual cell volumes");
  require(std::abs(stats.top_band_max - top) < 2e-6, "Top band differs from independent oracle");
  require(stats.cells == 60 && stats.top_band_cells == 20, "Incorrect diagnostic region counts");

  // Neither top-layer values nor its unscaled coefficients may be accessed.
  data.u0[d.face(2, 2, grid.nz)] = std::numeric_limits<float>::quiet_NaN();
  require(divergence_stats(data, op, true).interior_max == stats.interior_max, "Unassessed top layer contaminated diagnostic");
  data.u0[d.face(2, 2, 2)] = std::numeric_limits<float>::quiet_NaN();
  bool rejected = false;
  try { divergence_stats(data, op, true); } catch (const std::runtime_error &) { rejected = true; }
  require(rejected, "Diagnostic accepted a nonfinite assessed face");

  GridConfig small;
  small.nx = small.ny = 3; small.nz = 2;
  ModelInputs small_inputs(small, model, BuildingArrays{{}, {0}, {}, {}, {}});
  WINDSGeneralData small_data(make_domain(small_inputs), small_inputs.buildings, small_inputs.parameterizations, small_inputs.inflow.site_z0);
  small_data.applyWindProfile(small_inputs.inflow);
  small_data.applyParametrizations();
  const PoissonOperator small_op(small_data);
  const auto empty = divergence_stats(small_data, small_op, true);
  require(empty.cells == 0 && empty.top_band_cells == 1, "Small grid diagnostic bands are incorrect");
  std::fill(small_data.icellflag.begin(), small_data.icellflag.end(), 2);
  const auto solid = divergence_stats(small_data, small_op, true);
  require(solid.cells == 0 && solid.top_band_cells == 0, "Solid cells entered diagnostic");
}

static void box(BuildingArrays &geometry, int id, double x0, double x1)
{
  for (auto vertex : {std::pair{x0, 20.0}, std::pair{x0, 60.0},
                     std::pair{x1, 60.0}, std::pair{x1, 20.0}, std::pair{x0, 20.0}})
    geometry.vertices.insert(geometry.vertices.end(), {vertex.first, vertex.second});
  geometry.offsets.push_back(geometry.vertices.size() / 2);
  geometry.ids.push_back(id); geometry.heights.push_back(15); geometry.base_heights.push_back(0);
}

static std::vector<float> canyon(bool serial, bool report)
{
  GridConfig grid;
  grid.nx = 60; grid.ny = 40; grid.nz = 25;
  ModelSettings model;
  model.sensor_x = model.sensor_y = 5;
  BuildingArrays geometry{{}, {0}, {}, {}, {}};
  box(geometry, 0, 30, 40); box(geometry, 1, 52, 62);
  ModelInputs inputs(grid, model, geometry);
  inputs.set_condition({5, 270, 10});
  WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  const PoissonOperator op(data);
  const auto before = divergence_stats(data, op, true);
  require(before.interior_max > 0.1, "Canyon did not exercise divergent parameterizations");
  SolverState<float> solver(op, std::numeric_limits<float>::epsilon(), serial ? SweepOrder::Lexicographic : default_order());
  std::vector<float> previous, plane;
  for (const int budget : {1000, 2000, 4000}) {
    // Always restart from the same initial field and reset lambda. Verify that
    // the requested work is performed, even if the production stopping rule
    // would normally return early. No public stopping-rule change is made.
      const auto diagnostics = solve_wind(solver, data, budget);
    require(diagnostics.iterations == budget, "Canyon study stopped before the requested checkpoint");
    const auto stats = divergence_stats(data, op);
    require(stats.interior_max * 15 / 5 < 1e-3 && stats.interior_rms * 15 / 5 < 1e-4,
            "Canyon exceeds common conservative divergence bounds");
    plane.clear();
    const auto &d = data.domain;
    double street_speed = 0;
    std::size_t street_count = 0;
    for (int j = 1; j < grid.ny - 1; ++j)
      for (int i = 1; i < grid.nx - 1; ++i) {
        if (data.icellflag[d.cell(i, j, 1)] == 0) continue;
        const auto f = d.face(i, j, 1);
        const float u = 0.5f * (data.u[f] + data.u[d.faceAdd(f, 1, 0, 0)]);
        const float v = 0.5f * (data.v[f] + data.v[d.faceAdd(f, 0, 1, 0)]);
        const float w = 0.5f * (data.w[f] + data.w[d.faceAdd(f, 0, 0, 1)]);
        plane.insert(plane.end(), {u, v, w});
        if (d.x[i] > 40 && d.x[i] < 52 && d.y[j] > 20 && d.y[j] < 60) {
          street_speed += std::hypot(u, v); ++street_count;
        }
      }
    double maximum_change = 0, p95_change = 0;
    if (!previous.empty()) {
      std::vector<double> changes;
      for (std::size_t p = 0; p < plane.size(); p += 3)
        changes.push_back(std::sqrt(std::pow(plane[p] - previous[p], 2)
                         + std::pow(plane[p + 1] - previous[p + 1], 2)
                         + std::pow(plane[p + 2] - previous[p + 2], 2)) / 5);
      std::sort(changes.begin(), changes.end());
      maximum_change = changes.back(); p95_change = changes[std::size_t(0.95 * (changes.size() - 1))];
      require(maximum_change <= 1e-3 && p95_change <= 5e-4, "Canyon pedestrian velocity has not stabilized");
    }
    previous = plane;
    if (report)
      std::cout << "canyon " << (serial ? "serial" : "factory") << " budget=" << budget
                << " max=" << stats.interior_max << " rms=" << stats.interior_rms
                << " top=" << stats.top_band_max << " iterations=" << diagnostics.iterations
                << " lambda_change=" << diagnostics.max_lagrange_multiplier_change
                << " converged=" << diagnostics.converged << " street_horizontal_speed_at_1m="
                << street_speed / street_count << " max_velocity_change=" << maximum_change
                << " p95_velocity_change=" << p95_change << "\n";
  }
  return plane;
}

int main(int argc, char **)
{
  check(false, argc > 1);
  check(true, argc > 1);
  diagnostic_checks();
  for (float spacing : {1.0f, 2.0f, 4.0f})
    for (bool vertical : {false, true}) {
      injection(true, vertical, spacing, argc > 1);
#ifdef _OPENMP
      injection(false, vertical, spacing, argc > 1);
#endif
    }
  const auto serial = canyon(true, argc > 1);
#ifdef _OPENMP
  const auto parallel = canyon(false, argc > 1);
  require(serial.size() == parallel.size(), "Canyon backend sample counts differ");
  for (std::size_t i = 0; i < serial.size(); ++i)
    require(std::abs(serial[i] - parallel[i]) <= 2e-4 + 1e-5 * std::abs(serial[i]),
            "Canyon backends disagree at matched residual and velocity stability");
#endif
}
