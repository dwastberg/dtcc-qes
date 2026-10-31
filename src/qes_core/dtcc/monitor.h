#pragma once
#include "api/monitor_types.h"
#include "solver/solver.h"
#include <functional>

namespace dtcc_qes {
// Compiled once for one begun condition. Owns only slab/window/history buffers,
// never a checkpoint volume. Returned record/sample references live until their
// ring slot is reused. No stopping or acceptance decision is made here.
class Monitor {
public:
  struct Support { int lo = -1, hi = -1; double weight = 0; };
  struct Region {
    std::string name;
    solver::MassRegion bounds;
    std::size_t excluded_lateral_cells = 0, excluded_highest_cells = 0;
  };
  // Native read-only backend adapter, also used by manufactured sampling tests.
  // It supplies the same rounded/collocated slabs and mass definition as state.
  struct Source {
    const void *condition;
    std::uint64_t epoch;
    int iteration;
    std::function<void(solver::LayerRange,solver::CenteredDestination)> observe;
    std::function<solver::MassDiagnostics(solver::MassRegion,solver::FluxOptions)> diagnose;
    std::optional<solver::ResidualTrend> residual_trend;
  };
  static Monitor compile_source(const qes::Domain &domain,const void *condition,std::uint64_t epoch,MonitorSpec spec) {
    return Monitor(domain,condition,epoch,std::move(spec));
  }
  const MonitorCheckpoint &capture_source(const Source &source,double elapsed_seconds) {
    try {
      return capture_impl(source.condition,source.epoch,source.iteration,elapsed_seconds,
                          source.observe,source.diagnose,source.residual_trend);
    } catch (...) { failed_ = true; throw; }
  }
  template<class Real> Monitor(const solver::SolverState<Real> &state, MonitorSpec spec)
    : Monitor(state.prepared_operator().domain,&state,state.condition_epoch(),std::move(spec)) {}
  template<class Real> const MonitorCheckpoint &capture(const solver::SolverState<Real> &state, double elapsed_seconds) {
    return capture_source({&state,state.condition_epoch(),state.diagnostics().iterations,
        [&](solver::LayerRange layers,solver::CenteredDestination out) { state.observe(layers,out); },
        [&](solver::MassRegion region,solver::FluxOptions options) { return state.diagnose(region,options); },
        state.residual_trend()},elapsed_seconds);
  }
  const MonitorSpec &specification() const { return spec_; }
  const std::vector<Region> &regions() const { return regions_; }
  const std::vector<solver::Observation> &slabs() const { return slabs_; }
  std::size_t plane_points() const { return plane_points_; }
  std::size_t planned_bytes() const { return planned_bytes_; }
  std::size_t allocated_bytes() const;
  std::size_t history_size() const { return history_count_; }
  const MonitorCheckpoint &history_at(std::size_t chronological) const;
  const std::vector<MonitorSample> &samples() const;
private:
  struct ReceptorSupport {
    Support vertical;
    std::array<std::size_t,4> cells{};
    std::array<double,4> weights{};
    std::size_t count = 0;
  };
  struct Frame {
    int iteration = 0;
    std::vector<MonitorSample> samples;
    std::vector<MonitorPeak> peaks;
  };
  MonitorSpec spec_;
  qes::Domain domain_;
  const void *state_;
  std::uint64_t epoch_;
  int i_first_ = 0, i_last_ = 0, j_first_ = 0, j_last_ = 0;
  std::size_t plane_points_ = 0, planned_bytes_ = 0;
  std::vector<Support> heights_;
  std::vector<ReceptorSupport> receptors_;
  std::vector<Region> regions_;
  std::vector<solver::Observation> slabs_;
  std::vector<Frame> frames_;
  std::size_t frame_count_ = 0, next_frame_ = 0, latest_frame_ = 0;
  std::vector<MonitorCheckpoint> history_;
  std::size_t history_count_ = 0, next_history_ = 0;
  bool failed_ = false;
  std::vector<double> vector_scratch_, speed_scratch_;
  Monitor(const qes::Domain &,const void *,std::uint64_t,MonitorSpec);
  Support vertical(double) const;
  MonitorLocation location(std::size_t point,double height) const;
  MonitorSample sample(const Support &,std::size_t cell) const;
  MonitorSample receptor_sample(const ReceptorSupport &) const;
  const Frame &previous_frame(std::size_t back) const;
  MonitorWindow window(std::size_t offset,std::size_t count,std::size_t span,
                       const Frame &,const MonitorWindow *previous);
  const MonitorCheckpoint &capture_impl(const void *,std::uint64_t,int,double,
    const std::function<void(solver::LayerRange,solver::CenteredDestination)> &,
    const std::function<solver::MassDiagnostics(solver::MassRegion,solver::FluxOptions)> &,
    std::optional<solver::ResidualTrend>);
};
}
