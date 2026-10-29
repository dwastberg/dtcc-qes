#include "precision_solver.h"
#include "model_inputs.h"
#include "divergence.h"
#include "wind_runner.h"
#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#ifdef _OPENMP
#include <omp.h>
#endif
#include <cmath>
#include <limits>
#include <stdexcept>

using namespace dtcc_qes;
static void require(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
template<class Operation> static void rejects(Operation operation) {
  try { operation(); } catch (const std::exception &) { return; }
  throw std::runtime_error("Expected precision validation failure");
}

static void injection(double spacing, bool stretched, int axis)
{
  GridConfig grid;
  grid.nx = grid.ny = 24; grid.nz = 32; grid.cell_size = spacing;
  if (stretched) {
    grid.dz_layers = std::vector<double>(8, .5);
    grid.dz_layers.insert(grid.dz_layers.end(), 8, .75);
    grid.dz_layers.insert(grid.dz_layers.end(), 8, 1.25);
    grid.dz_layers.insert(grid.dz_layers.end(), 8, 2);
  }
  ModelSettings model; model.sensor_x = model.sensor_y = 2.5*spacing;
  ModelInputs input(grid, model, BuildingArrays{{}, {0}, {}, {}, {}});
  input.set_condition({0, 270, 10});
  WINDSGeneralData data(make_domain(input), input.buildings, input.parameterizations, input.inflow.site_z0);
  data.applyWindProfile(input.inflow);
  data.applyParametrizations();
  auto &initial = axis == 0 ? data.u0 : axis == 1 ? data.v0 : data.w0;
  initial[data.domain.face(12,12,6)] = .1f;
  PrecisionSolver solver(data.domain, 1e-12);
  require(solver.workspace_bytes() == 2*sizeof(double)*data.domain.numCellCentered(), "Unexpected precision workspace");
  const auto diagnostics = solver.solve(&data, 20000);
  require(diagnostics.converged && diagnostics.max_lagrange_multiplier_change <= 1e-12,
          "Precision injection did not converge");
  require(divergence_stats(data).interior_max < 3e-8, "Precision injection retains divergent flux");
  const auto u = data.u, v = data.v, w = data.w;
  const auto repeated = solver.solve(&data, 20000);
  require(data.u == u && data.v == v && data.w == w && repeated.iterations == diagnostics.iterations,
          "Repeated precision solve did not start from zero");
#ifdef _OPENMP
  omp_set_num_threads(4);
  const auto parallel = solver.solve(&data, 20000);
  require(data.u == u && data.v == v && data.w == w && parallel.iterations == diagnostics.iterations,
          "Precision output depends on OpenMP team size");
  omp_set_num_threads(2);
#endif
  const auto &d = data.domain;
  for (int k = 1; k < d.nz()-1; ++k) {
    require(data.u[d.face(0,2,k)] == data.u0[d.face(0,2,k)], "Prescribed lateral face changed");
    require(data.w[d.face(2,2,grid.nz)] == data.w0[d.face(2,2,grid.nz)], "Uncorrected top changed");
  }
  require(solver.solve(&data, 7, true).iterations == 7, "Study fixed-sweep control ignored budget");
  rejects([&] { solver.solve(nullptr, 1); });
  rejects([&] { solver.solve(&data, 0); });
  initial[0] = std::numeric_limits<float>::quiet_NaN();
  rejects([&] { solver.solve(&data, 1); });
  initial[0] = 0;
  data.e[0] = std::numeric_limits<float>::infinity();
  rejects([&] { solver.solve(&data, 1); });
  data.e[0] = 1;
  data.e.pop_back();
  rejects([&] { solver.solve(&data, 1); });
}

static void runner_modes()
{
  GridConfig grid; grid.nx = grid.ny = 16; grid.nz = 20;
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  BuildingArrays buildings{{12,12, 12,18, 18,18, 18,12, 12,12}, {0,5}, {0}, {8}, {0}};
  Messages messages;
  WindRunner runner;
  runner.prepare(grid, model, buildings, messages);
  SolverOptions options; options.max_iterations = 2000;
  const auto legacy = runner.solve({}, options, messages);
  options.precision = "float64"; options.tolerance = 1e-10;
  const auto precise = runner.solve({}, options, messages);
  require(precise.precision == "float64" && precise.tolerance == 1e-10 && precise.converged,
          "Runner lost precision diagnostics");
  require(precise.divergence.interior_max < 1e-6, "Runner precision residual too large");
  const auto repeated = runner.solve({}, options, messages);
  require(repeated.velocity == precise.velocity && repeated.iterations == precise.iterations,
          "Cached precision solve retained multipliers");
  options.tolerance = 1e-8;
  require(runner.solve({}, options, messages).tolerance == 1e-8, "Precision tolerance cache stale");
  options.precision = "float32"; options.tolerance = 1e-5;
  const auto restored = runner.solve({}, options, messages);
  require(restored.velocity == legacy.velocity && restored.iterations == legacy.iterations,
          "Switching precision changed default float32 output");
  options.precision = "float128";
  rejects([&] { runner.solve({}, options, messages); });
  options.precision = "float64";
  for (double tolerance : {0.0, 1e-20, std::numeric_limits<double>::infinity(),
                           std::numeric_limits<double>::quiet_NaN()}) {
    options.tolerance = tolerance;
    rejects([&] { runner.solve({}, options, messages); });
  }
  options.tolerance = 1e-10;
  require(runner.solve({}, options, messages).velocity == precise.velocity, "Failed validation damaged runner");
  for (std::size_t c = 0; c < precise.cell_flags.size(); ++c)
    if (precise.cell_flags[c] == 0 || precise.cell_flags[c] == 2)
      require(precise.velocity[3*c] == 0 && precise.velocity[3*c+1] == 0 && precise.velocity[3*c+2] == 0,
              "Precision correction changed solid velocities");
}

static void solid_faces()
{
  GridConfig grid; grid.nx = grid.ny = 16; grid.nz = 20;
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  BuildingArrays buildings{{12,12, 12,18, 18,18, 18,12, 12,12}, {0,5}, {0}, {24}, {0}};
  ModelInputs input(grid, model, buildings);
  input.set_condition({5, 315, 10});
  WINDSGeneralData data(make_domain(input), input.buildings, input.parameterizations, input.inflow.site_z0);
  data.applyWindProfile(input.inflow);
  data.applyParametrizations();
  PrecisionSolver solver(data.domain, 1e-10);
  require(solver.solve(&data, 2000).converged, "Solid-face precision fixture did not converge");
  const auto &d = data.domain;
  int cells = 0;
  for (int k = 1; k < d.nz()-1; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i) {
      const auto flag = data.icellflag[d.cell(i,j,k)];
      const auto f = d.face(i,j,k);
      if (flag != 0 && flag != 2) continue;
      ++cells;
      require(data.u[f] == 0 && data.u[f+1] == 0 && data.v[f] == 0 && data.v[f+d.nx()] == 0
              && data.w[f] == 0 && data.w[f+d.nx()*d.ny()] == 0,
              "Precision correction left nonzero staggered solid faces");
    }
  require(cells > 100, "Tall solid fixture does not span thread slabs");
  require(divergence_stats(data).top_band_max > 1e-5, "Top-band boundary limitation unexpectedly changed");
}

int main()
{
#ifdef _OPENMP
  omp_set_dynamic(0); omp_set_num_threads(2);
#endif
  Messages messages;
  {
    const std::lock_guard<std::mutex> lock(native_mutex());
    const BufferedLogSink sink(messages);
    for (double spacing : {.5, 2., 4.})
      for (int axis : {0,1,2}) injection(spacing, false, axis);
    for (int axis : {0,1,2}) injection(2, true, axis);
    solid_faces();
  }
  runner_modes();
}
