#include "wind_runner.h"
#include "model_inputs.h"
#include "divergence.h"
#include "solver/solver.h"
#include "solver_control.h"
#include "turbulence.h"
#include "winds/TURBGeneralData.h"
#include "winds/WINDSGeneralData.h"
#include <stdexcept>
#include <chrono>
#ifdef _OPENMP
#include <omp.h>
#endif

namespace dtcc_qes {
struct WindRunner::Impl {
  GridConfig grid;
  ModelInputs inputs;
  // Reverse destruction frees solvers, then turbulence (which points at the
  // wind data), then the wind data and its buildings.
  std::unique_ptr<WINDSGeneralData> data;
  std::unique_ptr<TURBGeneralData> turbulence;
  std::unique_ptr<solver::PoissonOperator> poisson;
  std::unique_ptr<solver::SolverState<float>> solver;
  std::unique_ptr<solver::SolverState<double>> precision_solver;
  double tolerance = 0;
  double preparation_seconds = 0;
  enum class Phase { Prepared, Initialized, Solving, Finalized };
  Phase phase = Phase::Prepared;

  Impl(const GridConfig &g, const ModelSettings &m, const BuildingArrays &b,
       const TurbulenceSettings &t)
    : grid(g), inputs(g, m, b, t),
      data(std::make_unique<WINDSGeneralData>(make_domain(inputs), inputs.buildings,
        inputs.parameterizations, inputs.inflow.site_z0))
  {
    poisson = std::make_unique<solver::PoissonOperator>(*data,solver::CoefficientOwnership::Take);
    if (inputs.turbulence_enabled) {
      check_turbulence_margin(inputs, *data, grid);
      turbulence = std::make_unique<TURBGeneralData>(inputs.turbulence, data.get());
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
  const auto started = std::chrono::steady_clock::now();
  auto prepared = std::make_unique<Impl>(grid, model, buildings, turbulence);
  prepared->preparation_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
  impl_.swap(prepared);
}

WindData WindRunner::solve(const WindCondition &condition, const SolverOptions &options, Messages &messages,
                          const SolverControl *control,const std::function<double()> &native_test_clock)
{
  std::optional<SolverController> controller;
  if (control) controller.emplace(*control,native_test_clock);
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  if (!impl_) throw std::runtime_error("Prepare the runner before solving");
  auto &state = *impl_;
  if (controller) {
    controller->record.timings.preparation_seconds = state.preparation_seconds;
    controller->record.effective_monitor.reference_speed = condition.speed;
    controller->record.timings.mutex_wait_seconds = controller->elapsed();
    controller->check("mutex_wait");
  }
  const double tolerance = solver_tolerance(options);
  struct SolveScope {
    Impl &state;
    bool success = false;
    ~SolveScope() {
      state.phase = Impl::Phase::Prepared;
      if (!success) { state.solver.reset(); state.precision_solver.reset(); }
    }
  } scope{state};
  double phase_started = controller ? controller->now() : 0;
  if (controller) {
#ifdef _OPENMP
#pragma omp parallel
    {
#pragma omp single
      controller->record.actual_threads = omp_get_num_threads();
    }
#endif
    controller->check("before_initialization");
  }
  state.inputs.set_condition(condition);
  auto &data = *state.data;
  data.resetICellFlag();
  data.applyWindProfile(state.inputs.inflow);
  data.applyParametrizations();
  state.phase = Impl::Phase::Initialized;
  if (controller) {
    controller->record.timings.initialization_seconds = controller->now()-phase_started;
    controller->check("after_initialization");
  }
  WindData result;
  solver::SolveDiagnostics diagnostics;
  try {
    const auto run = [&](auto &workspace) {
      phase_started = controller ? controller->now() : 0;
      if (controller) controller->check("before_rhs");
      workspace.begin(solver::ConditionInputs(data),options.max_iterations);
      state.phase = Impl::Phase::Solving;
      if (controller) {
        controller->record.timings.rhs_seconds = controller->now()-phase_started;
        controller->check("after_rhs");
        controller->run(workspace);
      } else workspace.advance(options.max_iterations);
      solver::MassDiagnostics mass;
      phase_started = controller ? controller->now() : 0;
      workspace.finalize(solver::FaceDestination(data),
                         solver::CenteredDestination{result.velocity,result.cell_flags},&mass);
      if (controller) controller->record.timings.finalization_seconds = controller->now()-phase_started;
      state.phase = Impl::Phase::Finalized;
      result.divergence = {mass.interior_max,mass.interior_rms,mass.top_band_max,mass.cells,mass.top_band_cells};
      return workspace.diagnostics();
    };
    const double allocation_started = controller ? controller->now() : 0;
    if (options.precision == "float64") {
      state.solver.reset();
      if (!state.precision_solver || state.tolerance != tolerance)
        state.precision_solver = std::make_unique<solver::SolverState<double>>(*state.poisson,tolerance);
      if (controller) controller->record.timings.workspace_seconds = controller->now()-allocation_started;
      diagnostics = run(*state.precision_solver);
    } else {
      state.precision_solver.reset();
      if (!state.solver || state.tolerance != tolerance)
        state.solver = std::make_unique<solver::SolverState<float>>(*state.poisson,tolerance);
      if (controller) controller->record.timings.workspace_seconds = controller->now()-allocation_started;
      diagnostics = run(*state.solver);
    }
    state.tolerance = tolerance;
  } catch (...) {
    state.solver.reset(); state.precision_solver.reset();
    state.phase = Impl::Phase::Prepared;
    throw;
  }

  phase_started = controller ? controller->now() : 0;
  if (state.turbulence) state.turbulence->run();

  if (state.turbulence) result.turbulence = turbulence_fields(*state.turbulence, state.grid);
  result.nx = state.grid.nx;
  result.ny = state.grid.ny;
  result.nz = state.grid.nz;
  result.x = data.domain.x;
  result.y = data.domain.y;
  result.z.assign(data.domain.z.begin() + 1, data.domain.z.end());
  result.z_faces.assign(data.domain.z_face.begin() + 1, data.domain.z_face.end());
  result.building_count = state.inputs.buildings.size();
  result.iterations = diagnostics.iterations;
  result.max_lagrange_multiplier_change = diagnostics.max_lagrange_multiplier_change;
  result.tolerance = diagnostics.tolerance;
  result.converged = diagnostics.converged;
  result.precision = options.precision;
  if (controller) {
    controller->record.timings.postprocessing_seconds = controller->now()-phase_started;
    controller->finish_output();
    result.control = std::move(controller->record);
  }
  scope.success = true;
  return result;
}
}
