#include "wind_runner.h"
#include "api/canyon_contract.h"
#include "model_inputs.h"
#include "divergence.h"
#include "solver/solver.h"
#include "solver_control.h"
#include "pedestrian_policy.h"
#include "util/QESException.h"
#include "turbulence.h"
#include "winds/TURBGeneralData.h"
#include "winds/WINDSGeneralData.h"
#include <stdexcept>
#include <chrono>
#ifdef _OPENMP
#include <omp.h>
#endif

namespace dtcc_qes {
namespace {
double progress_now() {
  return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
}
class WindRunner::ProgressScope {
public:
  explicit ProgressScope(WindRunner &runner, const char *operation) : runner_(runner) {
    runner_.start_progress(operation);
  }
  ~ProgressScope() { if (!success_) runner_.progress_phase("failed",true); }
  void finish() { runner_.progress_phase("completed",true); success_=true; }
private:
  WindRunner &runner_;
  bool success_=false;
};
void WindRunner::start_progress(const char *operation) {
  const std::lock_guard<std::mutex> lock(progress_mutex_);
  ++progress_.operation_id; ++progress_.revision;
  progress_.operation=operation; progress_.phase="mutex_wait";
  progress_.last_completed_stage=""; progress_.last_checkpoint=0;
  completed_sweeps_.store(0,std::memory_order_relaxed);
  completed_checkpoint_.store(0,std::memory_order_relaxed);
  progress_.started_at=progress_.phase_started_at=progress_now();
  progress_.finished=false;
}
void WindRunner::progress_phase(const char *phase, bool finished) {
  const std::lock_guard<std::mutex> lock(progress_mutex_);
  progress_.phase=phase; progress_.finished=finished;
  progress_.phase_started_at=progress_now(); ++progress_.revision;
}
void WindRunner::stage_progress(const char *stage) {
  const std::lock_guard<std::mutex> lock(progress_mutex_);
  progress_.last_completed_stage=stage; ++progress_.revision;
}
RunnerProgress WindRunner::progress() const {
  const std::lock_guard<std::mutex> lock(progress_mutex_);
  auto value=progress_;
  value.completed_sweeps=completed_sweeps_.load(std::memory_order_relaxed);
  value.last_checkpoint=completed_checkpoint_.load(std::memory_order_relaxed);
  value.observed_at=progress_now();
  return value;
}
void WindRunner::output_transfer(std::uint64_t operation_id, bool finished, bool failed) {
  const std::lock_guard<std::mutex> lock(progress_mutex_);
  if (operation_id!=progress_.operation_id) return;
  progress_.phase=failed?"failed":finished?"completed":"output_transfer";
  progress_.finished=finished || failed;
  progress_.phase_started_at=progress_now(); ++progress_.revision;
}
struct WindRunner::Impl {
  ResourceAccount resources{ResourceKind::WindGrid};
  GridConfig grid;
  ModelInputs inputs;
  ModelSettings model;
  // Reverse destruction frees solvers, then turbulence (which points at the
  // wind data), then the wind data and its buildings.
  std::unique_ptr<WINDSGeneralData> data;
  std::unique_ptr<TURBGeneralData> turbulence;
  std::unique_ptr<solver::PoissonOperator> poisson;
  std::unique_ptr<solver::SolverState<float>> solver;
  std::unique_ptr<solver::SolverState<double>> precision_solver;
  double tolerance = 0;
  float relaxation = 1.78f;
  double preparation_seconds = 0;
  enum class Phase { Prepared, Initialized, Solving, Finalized };
  Phase phase = Phase::Prepared;

  Impl(const GridConfig &g, const ModelSettings &m, const BuildingArrays &b,
       const TurbulenceSettings &t)
    : grid(g), inputs(g, m, b, t),model(m),
      data(std::make_unique<WINDSGeneralData>(make_domain(inputs), inputs.buildings,
        inputs.parameterizations, inputs.inflow.site_z0))
  {
    poisson = std::make_unique<solver::PoissonOperator>(*data,solver::CoefficientOwnership::Take);
    if (inputs.turbulence_enabled) {
      check_turbulence_margin(inputs, *data, grid);
      turbulence = std::make_unique<TURBGeneralData>(inputs.turbulence, data.get());
    }
    refresh_memory();
  }
  void refresh_memory() {
    const auto &d=*data;
    std::size_t bytes=0;
    for (const auto *a : {&d.z0_domain_u,&d.z0_domain_v,&d.e,&d.f,&d.g,&d.h,&d.m,&d.n,
                         &d.building_volume_frac,&d.ni,&d.nj,&d.nk,&d.wall_distance,&d.terrain,
                         &d.base_height,&d.effective_height,&d.u0,&d.v0,&d.w0,&d.u,&d.v,&d.w})
      bytes+=a->capacity()*sizeof(float);
    for (const auto *a : {&d.ibuilding_flag,&d.building_id,&d.icellflag,&d.icellflag_initial,&d.center_id,&d.terrain_face_id})
      bytes+=a->capacity()*sizeof(int);
    bytes+=d.mixingLengths.capacity()*sizeof(double);
    resources.set_bytes(bytes);
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
  const std::lock_guard<std::mutex> operation(operation_mutex_);
  ProgressScope progress_scope(*this,"prepare");
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  const auto started = std::chrono::steady_clock::now();
  progress_phase("preparation");
  auto prepared = std::make_unique<Impl>(grid, model, buildings, turbulence);
  prepared->preparation_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
  impl_.swap(prepared);
  prepared.reset();
  progress_scope.finish();
}

WindData WindRunner::solve(const WindCondition &condition, const SolverOptions &options, Messages &messages,
                          const SolverControl *control,const std::function<double()> &native_test_clock,
                          const ExperimentOptions *experiment)
{
  const auto steady_now = [] {return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();};
  const double native_started=steady_now();
  ControlTimings legacy_timings;
  if(control && control->mode=="adaptive" && !(condition.speed>0))
    throw qes::InputError("Adaptive pedestrian acceptance is unavailable for calm wind");
  std::optional<SolverController> controller;
  if (control) controller.emplace(*control,native_test_clock);
  const std::lock_guard<std::mutex> operation(operation_mutex_);
  ProgressScope progress_scope(*this,"solve");
  const std::lock_guard<std::mutex> lock(native_mutex());
  const BufferedLogSink sink(messages);
  progress_phase("validation");
  if (!impl_) throw std::runtime_error("Prepare the runner before solving");
  auto &state = *impl_;
  auto &data = *state.data;
  if(experiment && control) throw qes::InputError("Research settings cannot inherit a solver qualification");
  if(experiment) validate_canyon_contract(*experiment,state.model,state.inputs.turbulence_enabled,
                                        state.inputs.turbulence.methodLocalMixing);
  WindData result;
  result.operation_id=progress().operation_id;
  if(experiment) {
    for(const auto& c:experiment->cells)
      if(c[0]<0 || c[0]>=state.grid.nx || c[1]<0 || c[1]>=state.grid.ny || c[2]<0 || c[2]>=state.grid.nz)
        throw qes::InputError("Research sample cell is outside the physical domain");
    if(!std::isfinite(experiment->boundary_flux_area) || experiment->boundary_flux_area<0 ||
       !std::isfinite(experiment->boundary_flux_tolerance) || experiment->boundary_flux_tolerance<=0)
      throw qes::InputError("Invalid research boundary-flux normalization");
    result.experiment.emplace();
    result.experiment->canyon_model=experiment->canyon_model;
    result.experiment->sample_count=experiment->cells.size();
#ifdef _OPENMP
#pragma omp parallel
    {
#pragma omp single
      result.experiment->actual_threads=omp_get_num_threads();
    }
#endif
  }
  const auto capture = [&](const char *stage, bool projected = false) {
    if (!experiment || experiment->cells.empty()) return;
    auto &out = *result.experiment;
    out.stages.emplace_back(stage);
    const auto &d = data.domain;
    const auto &u = projected ? data.u : data.u0;
    const auto &v = projected ? data.v : data.v0;
    const auto &w = projected ? data.w : data.w0;
    for (const auto &cell : experiment->cells) {
      const int i=cell[0], j=cell[1], k=cell[2]+1;
      out.stage_velocity.push_back(0.5f*(u[d.face(i,j,k)]+u[d.face(i+1,j,k)]));
      out.stage_velocity.push_back(0.5f*(v[d.face(i,j,k)]+v[d.face(i,j+1,k)]));
      out.stage_velocity.push_back(0.5f*(w[d.face(i,j,k)]+w[d.face(i,j,k+1)]));
      out.stage_flags.push_back(data.icellflag[d.cell(i,j,k)]);
    }
  };
  auto &timings=controller?controller->record.timings:legacy_timings;
  const auto now=[&] {return controller?controller->now():steady_now();};
  if(!controller) {
    timings.preparation_seconds=state.preparation_seconds;
    timings.mutex_wait_seconds=steady_now()-native_started;
  }

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
      state.data->research_canyon_model=CanyonModel::Legacy;
      state.data->research_aligned_canyon=false;
      state.data->canyon_trace_roof=false;state.data->canyon_roof_trace.clear();
      state.data->canyon_voxel_roof_changes=0;
      state.data->canyon_incident_u.clear();state.data->canyon_incident_v.clear();
      state.data->canyon_fallback_reasons.clear();
      state.data->canyon_core_u=state.data->canyon_core_v=state.data->canyon_core_w=state.data->canyon_roof_skipped=0;
      state.data->canyon_changed_faces=state.data->canyon_roof_changes=state.data->canyon_audit_zones=state.data->canyon_W_changes=0;
      state.data->canyon_qualified=state.data->canyon_fallback=state.data->canyon_writes=0;
      state.refresh_memory();
      state.phase = Impl::Phase::Prepared;
      if (!success) { state.solver.reset(); state.precision_solver.reset(); }
    }
  } scope{state};
  data.research_canyon_model=experiment ? experiment->canyon_model : CanyonModel::Legacy;
  data.research_aligned_canyon=data.research_canyon_model!=CanyonModel::Legacy;
  data.canyon_trace_roof=experiment && experiment->canyon_trace_roof;
  data.canyon_voxel_roof_changes=0;
  data.canyon_core_u=data.canyon_core_v=data.canyon_core_w=data.canyon_roof_skipped=0;
  data.canyon_changed_faces=data.canyon_roof_changes=data.canyon_audit_zones=data.canyon_W_changes=0;
  data.canyon_qualified=data.canyon_fallback=data.canyon_writes=0;
#ifdef DTCC_QES_CANYON_TEST_HOOKS
  if(experiment && experiment->test_canyon_failure)
    throw std::runtime_error("canyon validation: deliberate failure after state attachment");
#endif

  double phase_started = now();
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
  progress_phase("initialization");
  state.inputs.set_condition(condition);
  if(controller && control->mode=="adaptive")
    controller->configure_adaptive(pedestrian_exclusions(state.grid,state.model,state.inputs,options,
      controller->record.effective_monitor,controller->record.actual_threads));
  data.resetICellFlag();
  data.applyWindProfile(state.inputs.inflow);
  if(data.research_canyon_model==CanyonModel::JoinedV1) {
    const auto& d=data.domain;
    data.canyon_incident_u.resize(d.nz());data.canyon_incident_v.resize(d.nz());
    for(int k=0;k<d.nz();++k) {
      data.canyon_incident_u[k]=data.u0[d.face(0,0,k)];
      data.canyon_incident_v[k]=data.v0[d.face(0,0,k)];
    }
  }
  capture("inflow");
  stage_progress("inflow");
  progress_phase("parameterization");
  data.applyParametrizations([&](const char *name) { capture(name); stage_progress(name); });
  if(experiment) {
    auto& out=*result.experiment;
    out.canyon_model=data.research_canyon_model;
    out.canyon_roof_trace=std::move(data.canyon_roof_trace);
    out.canyon_voxel_roof_changes=data.canyon_voxel_roof_changes;
    if(experiment->canyon_capture) out.canyon_initial_w=data.w0;
    out.canyon_core_u=data.canyon_core_u;
    out.canyon_core_v=data.canyon_core_v;
    out.canyon_core_w=data.canyon_core_w;
    out.canyon_roof_skipped=data.canyon_roof_skipped;
    out.canyon_changed_faces=data.canyon_changed_faces;
    out.canyon_roof_changes=data.canyon_roof_changes;
    out.canyon_audit_zones=data.canyon_audit_zones;
    out.canyon_W_changes=data.canyon_W_changes;
    out.canyon_qualified=data.canyon_qualified;
    out.canyon_fallback=data.canyon_fallback;
    out.canyon_writes=data.canyon_writes;
    for(const auto& reason:data.canyon_fallback_reasons) {
      out.canyon_fallback_reasons.push_back(reason.first);
      out.canyon_fallback_counts.push_back(reason.second);
    }
  }
  state.refresh_memory();
  state.phase = Impl::Phase::Initialized;
  timings.initialization_seconds = now()-phase_started;
  if (controller) {
    controller->check("after_initialization");
  }
  solver::SolveDiagnostics diagnostics;
  try {
    const auto run = [&](auto &workspace) {
      progress_phase("rhs");
      phase_started = now();
      if (controller) controller->check("before_rhs");
      workspace.begin(solver::ConditionInputs(data),options.max_iterations,
        controller && controller->adaptive_enabled()?solver::StopRule::FixedSweeps:solver::StopRule::LegacyTolerance, &completed_sweeps_);
      state.phase = Impl::Phase::Solving;
      timings.rhs_seconds = now()-phase_started;
      progress_phase("projection");
      if (controller) {
        controller->check("after_rhs");
        controller->run(workspace,&completed_checkpoint_);
      } else {
        const double started=now();
        workspace.advance(options.max_iterations);
        timings.sweeps_seconds=now()-started;
      }
      solver::MassDiagnostics mass;
      phase_started = now();
      progress_phase("finalization");
      workspace.finalize(solver::FaceDestination(data),
                         solver::CenteredDestination{result.velocity,result.cell_flags},&mass);
      stage_progress("projection");
      state.refresh_memory();
      timings.finalization_seconds = now()-phase_started;
      state.phase = Impl::Phase::Finalized;
      result.divergence = {mass.interior_max,mass.interior_rms,mass.top_band_max,mass.cells,mass.top_band_cells};
      capture("projection",true);
      if (experiment && experiment->diagnose_flux) {
        progress_phase("flux_diagnostics");
        const auto flux=workspace.diagnose({},solver::FluxOptions{true,condition.speed,{}});
        const auto &d=data.domain;
        double solid_max=0;
        const auto solid=[&](int i,int j,int k) {
          if(i<0 || i>=d.nx()-1 || j<0 || j>=d.ny()-1 || k<1 || k>=d.nz()-1)return false;
          const auto f=data.icellflag[d.cell(i,j,k)];return f==0 || f==2;
        };
        for(int k=1;k<d.nz();++k)for(int j=0;j<d.ny();++j)for(int i=0;i<d.nx();++i) {
          const auto f=d.face(i,j,k);
          if(solid(i,j,k)||solid(i-1,j,k))solid_max=std::max(solid_max,std::abs(double(data.u[f])));
          if(solid(i,j,k)||solid(i,j-1,k))solid_max=std::max(solid_max,std::abs(double(data.v[f])));
          if(solid(i,j,k)||solid(i,j,k-1))solid_max=std::max(solid_max,std::abs(double(data.w[f])));
        }
        result.experiment->mass={flux.interior_max,flux.interior_rms,flux.top_band_max,
          flux.interior_flux.boundary_flux,flux.top_band_flux.boundary_flux,solid_max};
      }
      return workspace.diagnostics();
    };
    const double allocation_started = now();
    const float relaxation=controller && controller->adaptive_enabled()?1.90f:1.78f;
    if (options.precision == "float64") {
      state.solver.reset();
      if (!state.precision_solver || state.tolerance != tolerance || state.relaxation!=relaxation) {
        progress_phase("workspace_release");
        state.precision_solver.reset();
        progress_phase("workspace_allocation");
        state.precision_solver = std::make_unique<solver::SolverState<double>>(*state.poisson,tolerance,solver::default_order(),relaxation);
      }
      timings.workspace_seconds = now()-allocation_started;
      diagnostics = run(*state.precision_solver);
    } else {
      state.precision_solver.reset();
      if (!state.solver || state.tolerance != tolerance || state.relaxation!=relaxation) {
        progress_phase("workspace_release");
        state.solver.reset();
        progress_phase("workspace_allocation");
        state.solver = std::make_unique<solver::SolverState<float>>(*state.poisson,tolerance,solver::default_order(),relaxation);
      }
      timings.workspace_seconds = now()-allocation_started;
      diagnostics = run(*state.solver);
    }
    state.tolerance = tolerance;
    state.relaxation = relaxation;
  } catch (const qes::RuntimeError &error) {
    state.solver.reset();state.precision_solver.reset();state.phase=Impl::Phase::Prepared;
    if(controller && control->mode=="adaptive")controller->numerical_failure(error.what());
    throw;
  } catch (...) {
    state.solver.reset(); state.precision_solver.reset();
    state.phase = Impl::Phase::Prepared;
    throw;
  }

  if(!controller)timings.solve_seconds=steady_now()-native_started;
  phase_started = now();
  progress_phase("postprocessing");
  if (state.turbulence) state.turbulence->run();
  state.refresh_memory();

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
  timings.postprocessing_seconds = now()-phase_started;
  if (controller) {
    controller->finish_output();
    result.timings=controller->record.timings;
    result.control = std::move(controller->record);
  } else {
    timings.native_total_seconds=steady_now()-native_started;
    result.timings=timings;
  }
  scope.success = true;
  progress_scope.finish();
  return result;
}
}
