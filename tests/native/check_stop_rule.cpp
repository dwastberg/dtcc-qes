// Velocity-estimate stop rule (SOLVER_STOP_RULE.md section 3.1).
#include "solver/solver.h"
#include "model_inputs.h"
#include "winds/WINDSGeneralData.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#ifdef _OPENMP
#include <omp.h>
#endif

using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void require(bool value, const std::string &message) { if (!value) throw std::runtime_error(message); }
template<class Operation> static void rejects(Operation operation, const char *what) {
  try { operation(); } catch (const std::exception &) { return; }
  throw std::runtime_error(std::string("Accepted invalid input: ") + what);
}
static bool close(double a, double b, double relative) { return std::abs(a-b) <= relative*std::max(std::abs(a),std::abs(b)); }

static std::unique_ptr<WINDSGeneralData> fixture(bool stretched = false) {
  GridConfig grid; grid.nx = 18; grid.ny = 16; grid.nz = 14;
  if (stretched) grid.dz_layers = {.5,.5,.5,.75,.75,1,1,1.25,1.5,2,2.5,3,4,5};
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  BuildingArrays buildings{{12,12,12,18,18,18,18,12,12,12},{0,5},{0},{6},{0}};
  ModelInputs inputs(grid,model,buildings);
  inputs.set_condition({5,33,10});
  auto data = std::make_unique<WINDSGeneralData>(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  data->applyWindProfile(inputs.inflow); data->applyParametrizations();
  return data;
}
static EstimateOptions estimate(double tolerance, int interval = 25) {
  EstimateOptions out; out.enabled = true; out.reference_speed = 5; out.tolerance = tolerance; out.interval = interval;
  return out;
}

// r is the larger of the last two block ratios; e = S c r/(1-r), with r clipped at the limit.
static void pure_step() {
  const double q = .8, S = estimate_safety_factor, limit = estimate_contraction_limit;
  const auto first = estimate_step(25, 1.0, std::nullopt, std::nullopt, 0);
  const auto second = estimate_step(50, q, 1.0, std::nullopt, 0);
  require(std::isnan(first.contraction) && std::isinf(first.estimate)
          && std::isnan(second.contraction) && std::isinf(second.estimate), "Estimate available before the third check");
  const auto third = estimate_step(75, q*q, q, 1.0, 0);
  require(close(third.contraction, q, 1e-14), "Contraction of a geometric sequence");
  require(close(third.estimate, S*q*q*q/(1-q), 1e-14), "Remaining change of a geometric sequence");
  const auto rising = estimate_step(75, .3*.1, .1, 1.0, 0);
  require(close(rising.contraction, .3, 1e-14), "A rising contraction uses the latest ratio");
  const auto falling = estimate_step(75, .1*.3, .3, 1.0, 0);
  require(close(falling.contraction, .3, 1e-14), "A falling contraction keeps the earlier ratio");
  const auto slow = estimate_step(75, .995*.995, .995, 1.0, 0);
  require(close(slow.contraction, .995, 1e-14), "Reported contraction is unclipped");
  require(close(slow.estimate, S*.995*.995*limit/(1-limit), 1e-14), "Slow contraction uses the limit");
  const auto growing = estimate_step(75, 2.0, 1.0, 1.0, 0);
  require(close(growing.estimate, S*2.0*limit/(1-limit), 1e-14), "Growth uses the limit");
  require(estimate_step(75, 0.0, 1.0, 1.0, 0).estimate == 0, "No change leaves no remaining change");
}

template<class Real> static std::size_t baseline_bytes(const PoissonOperator &op, const WINDSGeneralData &data) {
  return sizeof(Real)*(2*data.domain.numCellCentered()+op.tables().size());
}

// The snapshot exists only while the estimate is enabled; the estimate never perturbs the iterate.
template<class Real> static void storage_and_identity() {
  auto data = fixture();
  const PoissonOperator op(*data);
  SolverState<Real> plain(op,1e-5), recorded(op,1e-5);
  plain.begin(ConditionInputs(*data),200,StopRule::FixedSweeps);
  plain.advance(200);
  require(plain.workspace_bytes() == baseline_bytes<Real>(op,*data) && !plain.estimate_report(), "Disabled estimate allocated storage");
  recorded.begin(ConditionInputs(*data),200,StopRule::FixedSweeps,nullptr,estimate(1e-3));
  require(recorded.workspace_bytes() == baseline_bytes<Real>(op,*data)+sizeof(Real)*data->domain.numCellCentered(),
          "Enabled estimate must own one snapshot");
  const auto work = recorded.advance(200);
  require(work.completed_sweeps == 200 && work.termination == Termination::FixedBudget, "Fixed work changed by the estimate");
  const auto a = plain.copy_state_for_study(), b = recorded.copy_state_for_study();
  require(std::memcmp(a.multipliers.data(),b.multipliers.data(),a.multipliers.size()*sizeof(Real)) == 0,
          "Estimate perturbed the multipliers");
  const auto report = recorded.estimate_report();
  require(report && report->history.size() == 8 && report->checks == 8, "One check per completed block");
  for (std::size_t n = 0; n < report->history.size(); ++n)
    require(report->history[n].iteration == int(25*(n+1)), "Check iterations");
  require(std::isinf(report->history[1].estimate) && std::isfinite(report->history[2].estimate), "Estimate from the third check");
  recorded.begin(ConditionInputs(*data),10,StopRule::FixedSweeps);
  require(recorded.workspace_bytes() == baseline_bytes<Real>(op,*data) && !recorded.estimate_report(), "Snapshot not released");
}

// Faces the solver corrects, materialized without finalizing.
template<class Real> static std::vector<float> faces(const SolverState<Real> &state, WINDSGeneralData &data) {
  state.observe_faces(FaceDestination(data));
  auto out = data.u;
  out.insert(out.end(),data.v.begin(),data.v.end()); out.insert(out.end(),data.w.begin(),data.w.end());
  return out;
}

// The block change is the largest change of the materialized faces (float output rounding aside).
static void face_formula(bool stretched) {
  auto data = fixture(stretched);
  const PoissonOperator op(*data);
  SolverState<double> state(op,1e-5);
  state.begin(ConditionInputs(*data),50,StopRule::FixedSweeps,nullptr,estimate(1e-3));
  auto before = faces(state,*data);
  for (int block = 0; block < 2; ++block) {
    state.advance(25);
    const auto after = faces(state,*data);
    double observed = 0;
    for (std::size_t f = 0; f < after.size(); ++f) observed = std::max(observed,std::abs(double(after[f])-before[f]));
    const double recorded = state.estimate_report()->history[block].change;
    require(std::abs(observed/5-recorded) <= 1e-6, "Block change differs from the materialized faces");
    before = after;
  }
}

// Three buildings on a grid large enough for SOR's slow modes to dominate.
static std::unique_ptr<WINDSGeneralData> district() {
  GridConfig grid; grid.nx = 64; grid.ny = 48; grid.nz = 24;
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  const double blocks[3][5] = {{30,30,20,20,20},{60,20,10,20,12},{60,55,20,15,30}};
  BuildingArrays buildings;
  buildings.offsets = {0};
  for (int b = 0; b < 3; ++b) {
    const double x = blocks[b][0], y = blocks[b][1], w = blocks[b][2], d = blocks[b][3];
    for (double v : {x,y, x,y+d, x+w,y+d, x+w,y, x,y}) buildings.vertices.push_back(v);
    buildings.offsets.push_back(std::int64_t(buildings.vertices.size()/2));
    buildings.ids.push_back(b); buildings.heights.push_back(blocks[b][4]); buildings.base_heights.push_back(0);
  }
  ModelInputs inputs(grid,model,buildings);
  inputs.set_condition({5,33,10});
  auto data = std::make_unique<WINDSGeneralData>(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  data->applyWindProfile(inputs.inflow); data->applyParametrizations();
  return data;
}
// Largest remaining face-velocity error of an iterate, in double, relative to the reference speed.
static double remaining(const WINDSGeneralData &data, const PoissonOperator &op,
                        const std::vector<double> &now, const std::vector<double> &exact) {
  const auto &d = data.domain;
  const auto solid = [&](int i, int j, int k) {
    if (i < 0 || i >= d.nx()-1 || j < 0 || j >= d.ny()-1 || k < 1 || k >= d.nz()-1) return false;
    const auto f = data.icellflag[d.cell(i,j,k)]; return f == 0 || f == 2;
  };
  const auto e = [&](std::size_t c) { return now[c]-exact[c]; };
  double out = 0;
  for (int k = 1; k < d.nz()-2; ++k) for (int j = 1; j < d.ny()-1; ++j) for (int i = 1; i < d.nx()-1; ++i) {
    if (solid(i,j,k)) continue;
    const auto c = d.cell(i,j,k);
    const auto a = op.stencil(c,k);
    if (!solid(i-1,j,k)) out = std::max(out,std::abs(.5*a.f*d.dx()*(e(c)-e(d.cellAdd(c,-1,0,0)))));
    if (!solid(i,j-1,k)) out = std::max(out,std::abs(.5*a.h*d.dy()*(e(c)-e(d.cellAdd(c,0,-1,0)))));
    if (!solid(i,j,k-1)) out = std::max(out,std::abs(.5*a.n*d.dz_array[k]*(e(c)-e(d.cellAdd(c,0,0,-1)))));
  }
  return out/5;
}

// At the sweep where the rule stops, the estimate bounds the actual remaining error.
// The converged field does not depend on the relaxation; 1.78 reaches the
// multiplier tolerance, while 1.90 (above optimal on this small grid) only
// fluctuates at double rounding.
static void conservative_stop() {
  auto data = district();
  const PoissonOperator op(*data);
  SolverState<double> reference(op,1e-13);
  reference.begin(ConditionInputs(*data),60000,StopRule::LegacyTolerance);
  require(reference.advance(60000).termination == Termination::LegacyTolerance, "Reference did not converge");
  const auto exact = reference.copy_state_for_study().multipliers;
  for (float relaxation : {1.78f, 1.90f}) for (double tolerance : {1e-3, 1e-4, 1e-5}) {
    SolverState<double> state(op,1e-5,default_order(),relaxation);
    state.begin(ConditionInputs(*data),60000,StopRule::VelocityEstimate,nullptr,estimate(tolerance));
    const auto work = state.advance(60000);
    require(work.termination == Termination::VelocityEstimate, "Velocity rule did not stop on its estimate");
    const auto report = *state.estimate_report();
    const auto &last = report.history.back(), &before = report.history[report.history.size()-2];
    require(last.estimate <= tolerance && before.estimate <= tolerance, "Stop needs two passing checks");
    require(last.iteration == work.diagnostics.iterations, "Stop happens at a check");
    const double actual = remaining(*data,op,state.copy_state_for_study().multipliers,exact);
    char text[200];
    std::snprintf(text,sizeof text,"omega %.2f tolerance %.0e: estimate %.3e below actual %.3e at sweep %d (r %.4f)",
                  relaxation,tolerance,last.estimate,actual,last.iteration,last.contraction);
    require(actual <= tolerance && actual <= last.estimate, text);
    std::printf("omega %.2f tolerance %.0e: stop %d, estimate %.3e, actual %.3e\n",
                relaxation,tolerance,last.iteration,last.estimate,actual);
  }
}

// A huge tolerance stops at the earliest admissible check: passes count from the fourth check, and two are needed.
static void earliest_stop() {
  auto data = fixture();
  const PoissonOperator op(*data);
  SolverState<float> state(op,1e-5);
  state.begin(ConditionInputs(*data),1000,StopRule::VelocityEstimate,nullptr,estimate(1e6,10));
  const auto work = state.advance(1000);
  require(work.termination == Termination::VelocityEstimate && work.diagnostics.iterations == 50, "Earliest stop is the fifth check");
}

// float32 reaches rounding before a tolerance it cannot resolve; the floor stops it.
static void precision_floor() {
  auto data = fixture();
  const PoissonOperator op(*data);
  SolverState<float> state(op,1e-5);
  state.begin(ConditionInputs(*data),40000,StopRule::VelocityEstimate,nullptr,estimate(1e-12));
  const auto work = state.advance(40000);
  require(work.termination == Termination::PrecisionFloor, "float32 did not stop at its rounding floor");
  require(work.completed_sweeps < 40000, "Floor stop before the cap");
  const auto report = state.estimate_report();  // returned by value: keep it alive
  const auto &last = report->history.back();
  require(last.change <= last.floor, "Floor stop below its floor");
}

#ifdef _OPENMP
static void thread_independent() {
  auto data = fixture(true);
  const PoissonOperator op(*data);
  std::vector<EstimateCheck> first;
  for (int threads : {1, 2, 4}) {
    omp_set_num_threads(threads);
    SolverState<float> state(op,1e-5);
    state.begin(ConditionInputs(*data),300,StopRule::FixedSweeps,nullptr,estimate(1e-3));
    state.advance(300);
    const auto history = state.estimate_report()->history;
    if (first.empty()) { first = history; continue; }
    for (std::size_t n = 0; n < history.size(); ++n)
      require(std::memcmp(&history[n],&first[n],sizeof(EstimateCheck)) == 0, "Estimate depends on the thread team");
  }
}
#endif

static void invalid_inputs() {
  auto data = fixture();
  const PoissonOperator op(*data);
  SolverState<float> state(op,1e-5);
  rejects([&] { state.begin(ConditionInputs(*data),10,StopRule::VelocityEstimate); }, "velocity rule without estimate");
  for (double speed : {0.0, -1.0, std::nan("")}) {
    auto value = estimate(1e-3); value.reference_speed = speed;
    rejects([&] { state.begin(ConditionInputs(*data),10,StopRule::FixedSweeps,nullptr,value); }, "reference speed");
  }
  for (double tolerance : {0.0, -1.0, std::nan("")}) {
    rejects([&] { state.begin(ConditionInputs(*data),10,StopRule::VelocityEstimate,nullptr,estimate(tolerance)); }, "tolerance");
  }
  rejects([&] { state.begin(ConditionInputs(*data),10,StopRule::FixedSweeps,nullptr,estimate(1e-3,0)); }, "interval");
  state.begin(ConditionInputs(*data),10,StopRule::FixedSweeps,nullptr,estimate(1e-3));
  require(state.advance(10).completed_sweeps == 10, "Valid estimate after rejected inputs");
}

int main() {
  pure_step();
  storage_and_identity<float>();
  storage_and_identity<double>();
  face_formula(false);
  face_formula(true);
  conservative_stop();
  earliest_stop();
  precision_floor();
#ifdef _OPENMP
  thread_independent();
#endif
  invalid_inputs();
  return 0;
}
