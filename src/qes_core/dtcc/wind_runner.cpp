#include "wind_runner.h"
#include "qes_inputs.h"
#include "divergence.h"
#include "precision_solver.h"
#include "turbulence.h"
#include "winds/TURBGeneralData.h"
#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#include <stdexcept>

namespace dtcc_qes {
struct WindRunner::Impl {
  GridConfig grid;
  QESInputs inputs;
  // Reverse destruction frees solvers, then turbulence, then wind data and inputs.
  std::unique_ptr<WINDSGeneralData> data;
  std::unique_ptr<TURBGeneralData> turbulence;
  std::unique_ptr<Solver> solver;
  std::unique_ptr<PrecisionSolver> precision_solver;
  double tolerance = 0;

  Impl(const GridConfig &g, const ModelSettings &m, const BuildingArrays &b,
       const TurbulenceSettings &t)
    : grid(g), inputs(g, m, b, t),
      data(std::make_unique<WINDSGeneralData>(&inputs.input,
        make_domain(inputs), CPU_Type))
  {
    if (t.enabled) {
      check_turbulence_margin(inputs.input, *data, grid);
      turbulence = std::make_unique<TURBGeneralData>(&inputs.input, data.get());
    }
  }
};

WindRunner::WindRunner() = default;
WindRunner::~WindRunner()
{
  const std::lock_guard<std::mutex> lock(native_mutex());
  impl_.reset();
}

void WindRunner::prepare(const GridConfig &grid, const ModelSettings &model,
                         const BuildingArrays &buildings, Messages &messages)
{
  prepare(grid, model, buildings, TurbulenceSettings{}, messages);
}

void WindRunner::prepare(const GridConfig &grid, const ModelSettings &model,
                         const BuildingArrays &buildings, const TurbulenceSettings &turbulence,
                         Messages &messages)
{
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  auto prepared = std::make_unique<Impl>(grid, model, buildings, turbulence);
  impl_.swap(prepared);
}

WindData WindRunner::solve(const WindCondition &condition, const SolverOptions &options, Messages &messages)
{
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  if (!impl_) throw std::runtime_error("Prepare the runner before solving");
  auto &state = *impl_;
  const double tolerance = solver_tolerance(options);
  state.inputs.set_condition(condition);
  auto &data = *state.data;
  data.resetICellFlag();
  data.applyWindProfile(&state.inputs.input, 0, CPU_Type);
  data.applyParametrizations(&state.inputs.input);
  PrecisionDiagnostics diagnostics;
  if (options.precision == "float64") {
    state.solver.reset();
    if (!state.precision_solver || state.tolerance != tolerance)
      state.precision_solver = std::make_unique<PrecisionSolver>(data.domain, tolerance);
    state.tolerance = tolerance;
    diagnostics = state.precision_solver->solve(&data, options.max_iterations);
  } else {
    state.precision_solver.reset();
    if (!state.solver || state.tolerance != tolerance)
      state.solver.reset(SolverFactory::create(CPU_Type, data.domain, float(tolerance)));
    state.tolerance = tolerance;
    state.solver->resetLambda();
    const auto legacy = state.solver->solve(&data, options.max_iterations);
    diagnostics = {legacy.iterations, legacy.max_lagrange_multiplier_change,
                   legacy.tolerance, legacy.converged};
  }

  if (state.turbulence) state.turbulence->run();

  WindData result;
  if (state.turbulence) result.turbulence = turbulence_fields(*state.turbulence, state.grid);
  result.divergence = divergence_stats(data);
  result.nx = state.grid.nx;
  result.ny = state.grid.ny;
  result.nz = state.grid.nz;
  result.x = data.domain.x;
  result.y = data.domain.y;
  result.z.assign(data.domain.z.begin() + 1, data.domain.z.end());
  result.z_faces.assign(data.domain.z_face.begin() + 1, data.domain.z_face.end());
  result.building_count = state.inputs.polygons.size();
  const auto count = std::size_t(result.nx) * result.ny * result.nz;
  result.velocity.resize(count * 3);
  result.cell_flags.resize(count);
  const auto nx = data.domain.nx(), ny = data.domain.ny();
  for (int k = 1; k <= result.nz; ++k)
    for (int j = 0; j < result.ny; ++j)
      for (int i = 0; i < result.nx; ++i) {
        const auto face = data.domain.face(i, j, k);
        const auto cell = (std::size_t(k - 1) * result.ny + j) * result.nx + i;
        // Match WINDSOutputVisualization, including operand order and ghosts.
        result.velocity[3 * cell] = 0.5f * (data.u[face + 1] + data.u[face]);
        result.velocity[3 * cell + 1] = 0.5f * (data.v[face + nx] + data.v[face]);
        result.velocity[3 * cell + 2] = 0.5f * (data.w[face + nx * ny] + data.w[face]);
        result.cell_flags[cell] = data.icellflag[data.domain.cell(i, j, k)];
      }
  result.iterations = diagnostics.iterations;
  result.max_lagrange_multiplier_change = diagnostics.max_lagrange_multiplier_change;
  result.tolerance = diagnostics.tolerance;
  result.converged = diagnostics.converged;
  result.precision = options.precision;
  return result;
}
}
