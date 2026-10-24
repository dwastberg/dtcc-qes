#include "wind_runner.h"
#include "qes_inputs.h"
#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#include <stdexcept>

namespace dtcc_qes {
struct WindRunner::Impl {
  GridConfig grid;
  QESInputs inputs;
  // Reverse member destruction is essential: solver, data, then input owners.
  std::unique_ptr<WINDSGeneralData> data;
  std::unique_ptr<Solver> solver;
  float tolerance = 0;

  Impl(const GridConfig &g, const ModelSettings &m, const BuildingArrays &b)
    : grid(g), inputs(g, m, b),
      data(std::make_unique<WINDSGeneralData>(&inputs.input,
        qes::Domain(inputs.simulation.domain, inputs.simulation.grid), CPU_Type)) {}
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
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  auto prepared = std::make_unique<Impl>(grid, model, buildings);
  impl_.swap(prepared);
}

WindData WindRunner::solve(const WindCondition &condition, const SolverOptions &options, Messages &messages)
{
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  if (!impl_) throw std::runtime_error("Prepare the runner before solving");
  auto &state = *impl_;
  const float tolerance = qes_tolerance(options);
  state.inputs.set_condition(condition);
  auto &data = *state.data;
  data.resetICellFlag();
  data.applyWindProfile(&state.inputs.input, 0, CPU_Type);
  data.applyParametrizations(&state.inputs.input);
  if (!state.solver || state.tolerance != tolerance) {
    state.solver.reset(SolverFactory::create(CPU_Type, data.domain, tolerance));
    state.tolerance = tolerance;
  }
  state.solver->resetLambda();
  const auto diagnostics = state.solver->solve(&data, options.max_iterations);

  WindData result;
  result.nx = state.grid.nx;
  result.ny = state.grid.ny;
  result.nz = state.grid.nz;
  result.x = data.domain.x;
  result.y = data.domain.y;
  result.z.assign(data.domain.z.begin() + 1, data.domain.z.end());
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
  return result;
}
}
