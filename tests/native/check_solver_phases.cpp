#include "solver/solver.h"
#include "model_inputs.h"
#include "divergence.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>
#include <type_traits>
#ifdef _OPENMP
#include <omp.h>
#endif

using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void require(bool value,const char *message) { if (!value) throw std::runtime_error(message); }
template<class Operation> static void rejects(Operation operation) {
  try { operation(); } catch (const std::exception &) { return; }
  throw std::runtime_error("Invalid solver phase operation was accepted");
}
template<class T> static bool bits(const std::vector<T> &a,const std::vector<T> &b) {
  return a.size() == b.size() && (a.empty() || std::memcmp(a.data(),b.data(),a.size()*sizeof(T)) == 0);
}
template<class Real> static bool same(const StudyState<Real> &a,const StudyState<Real> &b) {
  return bits(a.multipliers,b.multipliers) && bits(a.rhs,b.rhs);
}
static std::unique_ptr<WINDSGeneralData> fixture(bool stretched) {
  GridConfig grid; grid.nx = 18; grid.ny = 16; grid.nz = 14;
  if (stretched) grid.dz_layers = {.5,.5,.5,.75,.75,1,1,1.25,1.5,2,2.5,3,4,5};
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  BuildingArrays buildings{{12,12,12,18,18,18,18,12,12,12},{0,5},{0},{6},{0}};
  ModelInputs inputs(grid,model,buildings);
  inputs.set_condition({5,33,10});
  auto data = std::make_unique<WINDSGeneralData>(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  data->applyWindProfile(inputs.inflow); data->applyParametrizations();
  data->u0[data->domain.face(5,5,3)] += .25f;
  return data;
}
static void compare_mass(const MassDiagnostics &a,const DivergenceStats &b) {
  require(a.interior_max == b.interior_max && a.interior_rms == b.interior_rms
       && a.top_band_max == b.top_band_max && a.cells == b.cells && a.top_band_cells == b.top_band_cells,
          "Pure diagnostic differs from materialized six-face fluxes");
}

template<class Real> static void partition(bool stretched,SweepOrder order) {
  auto data = fixture(stretched);
  const PoissonOperator op(*data);
  SolverState<Real> contiguous(op,1e-5,order), split(op,1e-5,order);
  require(contiguous.workspace_bytes() == sizeof(Real)*(2*data->domain.numCellCentered()+op.tables().size()), "Unexpected workspace storage");
  const auto input_u = data->u0, input_v = data->v0, input_w = data->w0;
  const auto input_flags = data->icellflag;
  contiguous.begin(ConditionInputs(*data),83,StopRule::FixedSweeps);
  contiguous.advance(83);
  const auto expected = contiguous.copy_state_for_study();
  split.begin(ConditionInputs(*data),83,StopRule::FixedSweeps);
  const auto zero = split.advance(0);
  require(zero.completed_sweeps == 0 && !zero.diagnostics.converged, "Unmeasured iterate reported convergence");
  require(split.advance(1).completed_sweeps == 1, "First block has wrong work count");
  split.observe({0,3}); split.diagnose();
  require(split.advance(7).diagnostics.iterations == 8, "Cumulative work was reset at a block boundary");
  const auto before = split.copy_state_for_study();
  const auto slab = split.observe({1,4});
  const auto mass = split.diagnose();
  const auto empty = split.observe({2,2});
  require(empty.velocity.empty() && empty.cell_flags.empty(), "Empty observation allocated a field");
  require(same(before,split.copy_state_for_study()), "Observation or diagnostic mutated solver state");
  rejects([&] { split.observe({-1,2}); });
  rejects([&] { split.observe({0,data->domain.nz()-1}); });
  rejects([&] { split.diagnose({0,2,1,2,0,1}); });
  rejects([&] { split.advance(-1); });

  // Materialize the same eighth iterate independently to check slab and flux
  // reconstruction without ending the continued trajectory.
  SolverState<Real> eighth(op,1e-5,order);
  eighth.begin(ConditionInputs(*data),8,StopRule::FixedSweeps); eighth.advance(8);
  std::vector<float> velocity;
  std::vector<std::int32_t> flags;
  eighth.finalize(FaceDestination(*data),CenteredDestination{velocity,flags});
  const auto plane = std::size_t(data->domain.nx()-1)*(data->domain.ny()-1);
  require(bits(slab.velocity,std::vector<float>(velocity.begin()+3*plane,velocity.begin()+12*plane)),
          "Slab differs bitwise from full finalization at the same iterate");
  require(bits(slab.cell_flags,std::vector<std::int32_t>(flags.begin()+plane,flags.begin()+4*plane)),
          "Slab flags differ from full finalization");
  compare_mass(mass,divergence_stats(*data,op));
  const auto short_region = split.diagnose({2,5,3,7,0,2});
  std::size_t counted = 0;
  for (int k = 1; k <= 2; ++k) for (int j = 3; j < 7; ++j) for (int i = 2; i < 5; ++i) {
    const auto flag = data->icellflag[data->domain.cell(i,j,k)];
    counted += flag != 0 && flag != 2;
  }
  require(short_region.cells == counted && short_region.top_band_cells == 0, "Regional diagnostic has wrong cell bounds");
  require(split.advance(75).completed_sweeps == 75 && split.diagnostics().iterations == 83,
          "Final partition lost sweeps");
  require(same(expected,split.copy_state_for_study()), "Partitioning changed RHS, multipliers or previous iterate");
  require(split.termination() == Termination::FixedBudget && split.advance(10).completed_sweeps == 0,
          "Fixed-work termination allowed extra sweeps");
  require(split.diagnostics().max_lagrange_multiplier_change == contiguous.diagnostics().max_lagrange_multiplier_change,
          "Partitioning changed the measured update");
  const auto observed = split.observe({0,data->domain.nz()-2});
  MassDiagnostics final_mass;
  split.finalize(FaceDestination(*data),CenteredDestination{velocity,flags},&final_mass);
  compare_mass(final_mass,divergence_stats(*data,op));
  require(bits(observed.velocity,velocity) && bits(observed.cell_flags,flags), "Full observation and output differ");
  compare_mass(split.diagnose(),divergence_stats(*data,op));
  const auto final_u = data->u, final_v = data->v, final_w = data->w;
  split.finalize(FaceDestination(*data));
  require(bits(data->u,final_u) && bits(data->v,final_v) && bits(data->w,final_w), "Finalization accumulated corrections");
  rejects([&] { split.advance(1); });
  split.begin(ConditionInputs(*data),83,StopRule::FixedSweeps); split.advance(83);
  require(same(expected,split.copy_state_for_study()), "New condition did not start from zero");
  require(bits(data->u0,input_u) && bits(data->v0,input_v) && bits(data->w0,input_w)
       && data->icellflag == input_flags, "Solver changed borrowed condition inputs");

  // Condition flags can legitimately differ from operator geometry flags.
  const auto solid = data->domain.cell(5,5,3);
  data->icellflag[solid] = 0;
  split.begin(ConditionInputs(*data),1,StopRule::FixedSweeps); split.advance(1);
  const auto changed = split.observe({2,3});
  const auto index = std::size_t(5)*(data->domain.nx()-1)+5;
  require(changed.cell_flags[index] == 0 && changed.velocity[3*index] == 0
       && changed.velocity[3*index+1] == 0 && changed.velocity[3*index+2] == 0,
          "Finalization used geometry flags instead of condition flags");
}

template<class Real> static void stopping(SweepOrder order) {
  auto data = fixture(false);
  const PoissonOperator op(*data);
  SolverState<Real> baseline(op,1e-3,order);
  baseline.begin(ConditionInputs(*data),5000);
  const auto reference = baseline.advance(5000);
  const auto n = reference.diagnostics.iterations;
  require(reference.diagnostics.converged && n > 1 && n < 5000, "Stopping fixture did not converge inside its budget");
  for (int cap : {n-1,n,n+7}) {
    SolverState<Real> state(op,1e-3,order);
    state.begin(ConditionInputs(*data),cap);
    const auto report = state.advance(cap);
    require(report.diagnostics.iterations == std::min(n,cap), "Wrong early-stop work count");
    require(report.diagnostics.converged == (cap >= n), "Convergence on the last permitted sweep was lost");
    require(report.termination == (cap >= n ? Termination::LegacyTolerance : Termination::IterationLimit),
            "Wrong legacy termination precedence");
    require(state.advance(1).completed_sweeps == 0, "A finished block took an extra sweep");
  }
  baseline.begin(ConditionInputs(*data),n);
  const auto first = baseline.advance(n-1);
  require(!first.diagnostics.converged && first.completed_sweeps == n-1, "Block ended before its requested work");
  require(baseline.advance(1).diagnostics.converged, "Boundary convergence was lost");
  SolverState<Real> loose(op,1e30,order);
  loose.begin(ConditionInputs(*data),100);
  require(!loose.diagnostics().converged, "Unmeasured sentinel qualified a solve");
  const auto measured = loose.advance(100);
  require(measured.completed_sweeps == 1 && measured.diagnostics.converged
       && measured.diagnostics.max_lagrange_multiplier_change > 0, "Permissive tolerance skipped the first measurement");
}

template<class Real> static void lifecycle() {
  auto data = fixture(true);
  const PoissonOperator op(*data);
  SolverState<Real> state(op);
  rejects([&] { state.advance(1); }); rejects([&] { state.observe({0,1}); });
  rejects([&] { state.diagnose(); }); rejects([&] { state.copy_state_for_study(); });
  rejects([&] { state.finalize(FaceDestination(*data)); });
  rejects([&] { state.begin(ConditionInputs(*data),0); });
  state.begin(ConditionInputs(*data),5,StopRule::FixedSweeps);
  rejects([&] { state.finalize(FaceDestination(*data)); });
  state.advance(5);
  const auto expected = state.copy_state_for_study();
  const float first = data->u0.front();
  data->u0.front() = std::numeric_limits<float>::quiet_NaN();
  rejects([&] { state.begin(ConditionInputs(*data),5); });
  require(state.phase() == Phase::Failed, "Failed initialization retained resumable state");
  rejects([&] { state.advance(1); }); rejects([&] { state.observe({0,1}); });
  data->u0.front() = first;
  state.begin(ConditionInputs(*data),5,StopRule::FixedSweeps); state.advance(5);
  require(same(expected,state.copy_state_for_study()), "Recovery retained a partial workspace");
  std::vector<float> velocity;
  std::vector<std::int32_t> flags;
  const auto original = data->u0;
  rejects([&] { state.finalize(FaceDestination(*data),CenteredDestination{data->u0,flags}); });
  rejects([&] { state.finalize(FaceDestination(*data),CenteredDestination{data->u,flags}); });
  state.finalize(FaceDestination(*data),CenteredDestination{velocity,flags});
  require(bits(data->u0,original), "Finalization overwrote original face velocities");
  const auto copy = state.copy_state_for_study();
  auto edited = copy;
  edited.multipliers.front() = Real(123);
  require(same(copy,state.copy_state_for_study()), "Study copy aliases live workspace");

  // Zero diagonal is finite at operator build, matching legacy runtime failure.
  auto broken = fixture(false);
  const auto c = broken->domain.cell(3,3,3);
  for (auto *a : {&broken->e,&broken->f,&broken->g,&broken->h,&broken->m,&broken->n}) (*a)[c] = 0;
  const PoissonOperator invalid(*broken);
  SolverState<Real> failed(invalid);
  failed.begin(ConditionInputs(*broken),5);
  rejects([&] { failed.advance(5); });
  require(failed.phase() == Phase::Failed, "Numerical failure retained an active state");
  rejects([&] { failed.advance(1); }); rejects([&] { failed.observe({0,1}); });
}

template<class Real> static void representations(bool stretched,SweepOrder order,float relaxation) {
  auto data = fixture(stretched);
  const auto &d = data->domain;
  // Exercise every nonzero face mask, including solid and boundary-adjacent
  // cells, without deriving operator structure from the condition flags.
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i) {
      const auto c = d.cell(i,j,k);
      const unsigned mask = unsigned(c%63)+1;
      const float constants[] = {1.0f/(d.dx()*d.dx()),1.0f/(d.dx()*d.dx()),
        1.0f/(d.dy()*d.dy()),1.0f/(d.dy()*d.dy()),
        1.0f/(d.dz_array[k]*0.5f*(d.dz_array[k]+d.dz_array[k+1])),
        1.0f/(d.dz_array[k]*0.5f*(d.dz_array[k]+d.dz_array[k-1]))};
      const std::array<std::vector<float> *,6> arrays{&data->e,&data->f,&data->g,&data->h,&data->m,&data->n};
      for (unsigned axis = 0; axis < 6; ++axis) (*arrays[axis])[c] = mask&(1u<<axis) ? constants[axis] : 0.0f;
    }
  const PoissonOperator compact(*data), explicit_op(*data,OperatorStorage::Explicit);
  require(compact.compact() && !explicit_op.compact(), "Wrong operator representation");
  for (std::size_t c = 0; c < std::size_t(d.numCellCentered()); ++c)
    for (int axis = 0; axis < 6; ++axis) {
      const float a = compact.coefficient(axis,c), b = explicit_op.coefficient(axis,c);
      require(std::memcmp(&a,&b,sizeof(float)) == 0, "Compact coefficient bits changed");
    }
  SolverState<Real> a(compact,1e-5,order,relaxation), b(explicit_op,1e-5,order,relaxation);
  a.begin(ConditionInputs(*data),17,StopRule::FixedSweeps);
  b.begin(ConditionInputs(*data),17,StopRule::FixedSweeps);
  require(same(a.copy_state_for_study(),b.copy_state_for_study()), "Compact RHS changed");
  for (int work : {1,7,9}) {
    a.advance(work); b.advance(work);
    require(same(a.copy_state_for_study(),b.copy_state_for_study()), "Compact iterate changed");
    require(a.diagnostics().max_lagrange_multiplier_change == b.diagnostics().max_lagrange_multiplier_change
         && a.termination() == b.termination(), "Compact change or termination changed");
    const auto x = a.observe({0,d.nz()-2}), y = b.observe({0,d.nz()-2});
    require(bits(x.velocity,y.velocity) && bits(x.cell_flags,y.cell_flags), "Compact observation changed");
    const auto ma = a.diagnose(), mb = b.diagnose();
    require(ma.interior_max == mb.interior_max && ma.interior_rms == mb.interior_rms
         && ma.top_band_max == mb.top_band_max && ma.cells == mb.cells && ma.top_band_cells == mb.top_band_cells,
            "Compact mass diagnostic changed");
  }
  a.finalize(FaceDestination(*data));
  const auto u = data->u, v = data->v, w = data->w;
  b.finalize(FaceDestination(*data));
  require(bits(u,data->u) && bits(v,data->v) && bits(w,data->w), "Compact final faces changed");
}

static void operator_lifetime() {
  for (bool fallback : {false,true}) {
    auto data = fixture(true);
    if (fallback) data->e[5] = .12345f;
    const auto expected = data->e;
    const PoissonOperator op(*data,CoefficientOwnership::Take);
    require(op.compact() != fallback, "Fallback representation not recorded");
    for (const auto *a : {&data->e,&data->f,&data->g,&data->h,&data->m,&data->n})
      require(a->empty() && !a->capacity(), "Transferred setup coefficients retained storage");
    data.reset();
    for (std::size_t c = 0; c < expected.size(); ++c) {
      const auto actual = op.coefficient(0,c);
      require(std::memcmp(&actual,&expected[c],sizeof(float)) == 0, "Operator borrowed freed coefficients");
    }
  }
  auto data = fixture(false);
  data->e[0] = -0.0f;
  const PoissonOperator negative_zero(*data);
  require(!negative_zero.compact() && std::signbit(negative_zero.coefficient(0,0)), "Signed zero was lost");
  data->e[0] = .125f;
  const PoissonOperator copied(*data);
  data->e[0] = .25f;
  require(!copied.compact() && copied.coefficient(0,0) == .125f, "Explicit fallback aliases geometry");
}

static void optional_allocations() {
  auto data = fixture(true); // Includes stair-step buildings and Wall::defineWalls.
  for (const auto *a : {&data->building_volume_frac,&data->ni,&data->nj,&data->nk,&data->wall_distance})
    require(a->empty() && !a->capacity(), "Stair-step geometry allocated cut-cell fields");
  require(data->center_id.empty() && data->mixingLengths.empty(), "Wind-only geometry allocated optional fields");
  data->ensureCutCellStorage();
  require(data->building_volume_frac.size() == std::size_t(data->domain.numCellCentered())
       && data->building_volume_frac.front() == 1 && data->center_id.front() == 1
       && data->ni.front() == 0 && data->wall_distance.front() == 0, "Cut-cell defaults changed");
  data->building_volume_frac.front() = .25f;
  data->ensureCutCellStorage();
  require(data->building_volume_frac.front() == .25f, "Cut-cell allocation reset existing geometry");
}

int main() {
  require(default_order() == SweepOrder::RedBlack, "CPU default ordering differs between builds");
#ifdef _OPENMP
  omp_set_dynamic(0);
#endif
  for (int threads : {1,2,4}) {
#ifdef _OPENMP
    omp_set_num_threads(threads);
#endif
    for (auto order : {SweepOrder::Lexicographic,SweepOrder::RedBlack}) {
      for (bool stretched : {false,true}) { partition<float>(stretched,order); partition<double>(stretched,order); }
      stopping<float>(order); stopping<double>(order);
    }
  }
  lifecycle<float>(); lifecycle<double>();
  operator_lifetime();
  optional_allocations();
  for (auto order : {SweepOrder::Lexicographic,SweepOrder::RedBlack})
    for (bool stretched : {false,true}) for (float relaxation : {1.05f,1.78f,1.92f}) {
      representations<float>(stretched,order,relaxation);
      representations<double>(stretched,order,relaxation);
    }
}
