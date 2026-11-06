// QES-derived workspace and phase driver; GPL-3.0-or-later.
#include "solver.h"
#include "mass_diagnostics.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <type_traits>

namespace dtcc_qes::solver {
PoissonOperator::PoissonOperator(const WINDSGeneralData &wind, OperatorStorage storage)
  : domain(wind.domain) { build(wind,nullptr,storage); }
PoissonOperator::PoissonOperator(WINDSGeneralData &wind, CoefficientOwnership, OperatorStorage storage)
  : domain(wind.domain) { build(wind,&wind,storage); }
void PoissonOperator::build(const WINDSGeneralData &wind, WINDSGeneralData *take, OperatorStorage storage) {
  const std::array<const std::vector<float> *,6> arrays{&wind.e,&wind.f,&wind.g,&wind.h,&wind.m,&wind.n};
  const auto count = std::size_t(domain.numCellCentered());
  for (const auto *a : arrays)
    if (a->size() != count || !std::all_of(a->begin(),a->end(),[](float x) { return std::isfinite(x); }))
      throw qes::InputError("Solver coefficients must have the expected length and finite values");
  if (storage != OperatorStorage::Automatic && storage != OperatorStorage::Explicit)
    throw qes::InputError("Invalid operator storage preference");
  const auto same = [](float a,float b) { return std::memcmp(&a,&b,sizeof(float)) == 0; };
  if (storage == OperatorStorage::Automatic) {
    masks_.resize(count);
    tables_.resize(std::size_t(domain.nz()-1)*64);
    compact_ = true;
    const auto plane = std::size_t(domain.numHorizontalCellCentered());
    for (int k = 0; k < domain.nz()-1; ++k) {
      // Wall only scales solved layers; preserve the unscaled shell exactly.
      std::array<float,6> constants{1,1,1,1,1,1};
      if (k >= 1 && k < domain.nz()-2) {
        constants = {1.0f/(domain.dx()*domain.dx()),1.0f/(domain.dx()*domain.dx()),
                     1.0f/(domain.dy()*domain.dy()),1.0f/(domain.dy()*domain.dy()),
                     1.0f/(domain.dz_array[k]*0.5f*(domain.dz_array[k]+domain.dz_array[k+1])),
                     1.0f/(domain.dz_array[k]*0.5f*(domain.dz_array[k]+domain.dz_array[k-1]))};
      }
      for (unsigned mask = 0; mask < 64; ++mask)
        tables_[std::size_t(k)*64+mask] = {mask&1 ? constants[0] : 0.0f,mask&2 ? constants[1] : 0.0f,
          mask&4 ? constants[2] : 0.0f,mask&8 ? constants[3] : 0.0f,
          mask&16 ? constants[4] : 0.0f,mask&32 ? constants[5] : 0.0f};
      for (std::size_t c = std::size_t(k)*plane; c < std::size_t(k+1)*plane; ++c) {
        unsigned mask = 0;
        for (unsigned axis = 0; axis < 6; ++axis) {
          const float value = (*arrays[axis])[c];
          if (same(value,constants[axis])) mask |= 1u<<axis;
          else if (!same(value,0.0f)) compact_ = false;
        }
        masks_[c] = std::uint8_t(mask);
      }
    }
  }
  if (!compact_) {
    std::vector<std::uint8_t>().swap(masks_); std::vector<Stencil>().swap(tables_);
    if (take) {
      std::array<std::vector<float> *,6> owned{&take->e,&take->f,&take->g,&take->h,&take->m,&take->n};
      for (unsigned axis = 0; axis < 6; ++axis) explicit_[axis].swap(*owned[axis]);
    } else for (unsigned axis = 0; axis < 6; ++axis) explicit_[axis] = *arrays[axis];
  }
  if (take) for (auto *a : {&take->e,&take->f,&take->g,&take->h,&take->m,&take->n}) std::vector<float>().swap(*a);
  resources_.set_bytes(storage_bytes());
}
std::size_t PoissonOperator::storage_bytes() const {
  std::size_t bytes = masks_.capacity()*sizeof(std::uint8_t)+tables_.capacity()*sizeof(Stencil);
  for (const auto &a : explicit_) bytes += a.capacity()*sizeof(float);
  return bytes;
}
float PoissonOperator::coefficient(int axis,std::size_t c) const {
  const auto a = stencil(c,int(c/std::size_t(domain.numHorizontalCellCentered())));
  switch (axis) { case 0: return a.e; case 1: return a.f; case 2: return a.g;
                  case 3: return a.h; case 4: return a.m; case 5: return a.n; }
  throw qes::InputError("Invalid coefficient axis");
}
ConditionInputs::ConditionInputs(const WINDSGeneralData &wind)
  : domain(wind.domain),u0(wind.u0),v0(wind.v0),w0(wind.w0),icellflag(wind.icellflag) {}
FaceDestination::FaceDestination(WINDSGeneralData &wind) : u(wind.u),v(wind.v),w(wind.w) {}

template<class Real> SolverState<Real>::SolverState(const PoissonOperator &op,
    double tolerance, SweepOrder order, float relaxation)
  : operator_(op),domain(op.domain),tolerance_(std::is_same_v<Real,float> ? double(float(tolerance)) : tolerance),
    order_(order),omega(Real(relaxation)) {
  if (!std::isfinite(tolerance_) || tolerance_ < std::numeric_limits<Real>::epsilon())
    throw qes::InputError("Solver tolerance must be finite and at least the arithmetic epsilon");
  if (order != SweepOrder::Lexicographic && order != SweepOrder::RedBlack)
    throw qes::InputError("Invalid CPU sweep order");
  if (!std::isfinite(relaxation) || relaxation <= 0 || relaxation >= 2)
    throw qes::InputError("Relaxation must be finite and between zero and two");
  R.resize(domain.numCellCentered(),0);
  lambda.resize(domain.numCellCentered(),0);
  if (op.compact()) {
    factors_.reserve(op.tables().size());
    for (const auto &a : op.tables()) {
      const Real diagonal = Real(a.e)+a.f+a.g+a.h+a.m+a.n;
      // Zero diagonals are handled by the existing solve-time nonfinite gate.
      factors_.push_back(omega/diagonal);
    }
  }
  resources_.set_bytes(workspace_bytes());
}

template<class Real> void SolverState<Real>::begin(ConditionInputs input, int sweeps, StopRule rule,
                                                  std::atomic<int> *completed_sweeps) {
  completed_sweeps_=completed_sweeps;
  if (completed_sweeps_) completed_sweeps_->store(0,std::memory_order_relaxed);
  phase_ = Phase::Failed;
  fields_.reset();
  last_trend_.reset(); collect_residual_ = false;
  ++condition_epoch_;
  if (sweeps < 1 || (rule != StopRule::LegacyTolerance && rule != StopRule::FixedSweeps))
    throw qes::InputError("A positive total sweep limit and valid stop rule are required");
  if (input.domain.getDomainCellNum() != domain.getDomainCellNum() || input.domain.dx() != domain.dx()
      || input.domain.dy() != domain.dy() || input.domain.dz_array != domain.dz_array)
    throw qes::InputError("Solver and wind-field domains differ");
  for (const auto *a : {&input.u0,&input.v0,&input.w0})
    if (a->size() != std::size_t(domain.numFaceCentered())
        || !std::all_of(a->begin(),a->end(),[](float x) { return std::isfinite(x); }))
      throw qes::InputError("Initial wind arrays must have the expected length and finite values");
  if (input.icellflag.size() != std::size_t(domain.numCellCentered()))
    throw qes::InputError("Condition cell flags have the wrong length");
  std::fill(R.begin(),R.end(),Real(0));
  std::fill(lambda.begin(),lambda.end(),Real(0));
  iterations_ = 0; last_change_ = 0; total_sweeps_ = sweeps; stop_rule_ = rule;
  fields_.emplace(KernelFields{input.u0,input.v0,input.w0,input.icellflag});
  try { build_rhs(); phase_ = Phase::Active; }
  catch (...) { fields_.reset(); throw; }
}

template<class Real> void SolverState<Real>::require_iterate() const {
  if (!fields_ || (phase_ != Phase::Active && phase_ != Phase::Finalized))
    throw qes::InputError("Begin a valid condition before accessing solver state");
}
template<class Real> SolveDiagnostics SolverState<Real>::diagnostics() const {
  require_iterate();
  return {iterations_,double(last_change_),tolerance_,iterations_ > 0 && std::isfinite(last_change_)
          && last_change_ <= tolerance_};
}
template<class Real> Termination SolverState<Real>::termination() const {
  require_iterate();
  if (stop_rule_ == StopRule::LegacyTolerance && diagnostics().converged) return Termination::LegacyTolerance;
  if (iterations_ == total_sweeps_) return stop_rule_ == StopRule::FixedSweeps ? Termination::FixedBudget : Termination::IterationLimit;
  return Termination::None;
}
template<class Real> WorkReport SolverState<Real>::advance(int sweeps, bool collect_residual_trend) {
  require_iterate();
  if (phase_ != Phase::Active || sweeps < 0)
    throw qes::InputError("Advance requires an active condition and nonnegative work");
  collect_residual_ = collect_residual_trend;
  if (!collect_residual_) last_trend_.reset();
  const int before = iterations_;
  const int work = std::min(sweeps,total_sweeps_-iterations_);
  try {
    for (int i = 0; i < work && termination() == Termination::None; ++i) {
      last_change_ = order_ == SweepOrder::RedBlack ? sweep_red_black() : sweep_lexicographic();
      ++iterations_;
      if (completed_sweeps_) completed_sweeps_->store(iterations_,std::memory_order_relaxed);
    }
  } catch (...) { phase_ = Phase::Failed; fields_.reset(); throw; }
  return {iterations_-before,diagnostics(),termination()};
}
template<class Real> bool SolverState<Real>::solid(int i,int j,int k) const {
  if (i < 0 || i >= domain.nx()-1 || j < 0 || j >= domain.ny()-1 || k < 1 || k >= domain.nz()-1) return false;
  const auto flag = fields_->icellflag[domain.cell(i,j,k)];
  return flag == 0 || flag == 2;
}
template<class Real> float SolverState<Real>::face_value(int component,int i,int j,int k) const {
  // Match the original face-owned mask, including the excluded ground ghost.
  if (k >= 1 && (solid(i,j,k) || solid(i-(component==0),j-(component==1),k-(component==2)))) return 0;
  if (k >= 1 && k < domain.nz()-2 && i >= 1 && i < domain.nx()-1 && j >= 1 && j < domain.ny()-1)
    return corrected_face(component,i,j,k);
  const auto f = domain.face(i,j,k);
  return component == 0 ? fields_->u0[f] : component == 1 ? fields_->v0[f] : fields_->w0[f];
}

// The same collocation expression is used for pure observation and full output.
template<class FaceValue> static void centers(const qes::Domain &domain, const std::vector<int> &flags,
    LayerRange layers, CenteredDestination out, FaceValue face) {
  const int nx = domain.nx()-1, ny = domain.ny()-1;
  if (layers.first < 0 || layers.last < layers.first || layers.last > domain.nz()-2)
    throw qes::InputError("Observation layers are outside the physical grid");
  const auto count = std::size_t(layers.last-layers.first)*ny*nx;
  out.velocity.resize(count*3); out.cell_flags.resize(count);
  for (int k = layers.first+1; k <= layers.last; ++k)
    for (int j = 0; j < ny; ++j) for (int i = 0; i < nx; ++i) {
      const auto c = (std::size_t(k-1-layers.first)*ny+j)*nx+i;
      out.velocity[3*c] = 0.5f * (face(0,i+1,j,k) + face(0,i,j,k));
      out.velocity[3*c+1] = 0.5f * (face(1,i,j+1,k) + face(1,i,j,k));
      out.velocity[3*c+2] = 0.5f * (face(2,i,j,k+1) + face(2,i,j,k));
      out.cell_flags[c] = flags[domain.cell(i,j,k)];
    }
}
template<class Real> Observation SolverState<Real>::observe(LayerRange layers) const {
  require_iterate();
  Observation result{layers,domain.nx()-1,domain.ny()-1,{}, {}};
  observe(layers,{result.velocity,result.cell_flags});
  return result;
}
template<class Real> void SolverState<Real>::observe(LayerRange layers, CenteredDestination out) const {
  require_iterate();
  if (&out.velocity == &fields_->u0 || &out.velocity == &fields_->v0 || &out.velocity == &fields_->w0
      || static_cast<const void *>(&out.cell_flags) == static_cast<const void *>(&fields_->icellflag))
    throw qes::InputError("Observation destinations must not alias condition inputs");
  centers(domain,fields_->icellflag,layers,out,
          [&](int c,int i,int j,int k) { return face_value(c,i,j,k); });
}
template<class Real> MassDiagnostics SolverState<Real>::diagnose(MassRegion region, FluxOptions flux) const {
  require_iterate();
  return mass_diagnostics(operator_,fields_->icellflag,
      [&](int c,int i,int j,int k) { return face_value(c,i,j,k); },region,flux);
}
template<class Real> void SolverState<Real>::finalize(FaceDestination out, std::optional<CenteredDestination> centered,
                                                     MassDiagnostics *final_mass) {
  require_iterate();
  if (!iterations_) throw qes::InputError("Finalize requires at least one complete sweep");
  const auto immutable = [&](const std::vector<float> &a) {
    return &a == &fields_->u0 || &a == &fields_->v0 || &a == &fields_->w0;
  };
  if (immutable(out.u) || immutable(out.v) || immutable(out.w)
      || (centered && (immutable(centered->velocity) || &centered->velocity == &out.u
          || &centered->velocity == &out.v || &centered->velocity == &out.w
          || static_cast<const void *>(&centered->cell_flags) == static_cast<const void *>(&fields_->icellflag))))
    throw qes::InputError("Finalization destinations must not alias immutable solver inputs");
  if (&out.u == &out.v || &out.u == &out.w || &out.v == &out.w)
    throw qes::InputError("Finalization face destinations must not alias each other");
  try {
    const auto count = std::size_t(domain.numFaceCentered());
    out.u.resize(count); out.v.resize(count); out.w.resize(count);
#pragma omp parallel for if(order_ == SweepOrder::RedBlack)
    for (int k = 0; k < domain.nz(); ++k)
      for (int j = 0; j < domain.ny(); ++j) for (int i = 0; i < domain.nx(); ++i) {
        const auto f = domain.face(i,j,k);
        out.u[f] = face_value(0,i,j,k); out.v[f] = face_value(1,i,j,k); out.w[f] = face_value(2,i,j,k);
      }
    if constexpr (std::is_same_v<Real,double>)
      for (const auto *a : {&out.u,&out.v,&out.w})
        if (!std::all_of(a->begin(),a->end(),[](float x) { return std::isfinite(x); }))
          throw qes::RuntimeError("Non-finite corrected velocity during solve");
    if (centered) centers(domain,fields_->icellflag,{0,domain.nz()-2},*centered,
        [&](int c,int i,int j,int k) { const auto f = domain.face(i,j,k); return c == 0 ? out.u[f] : c == 1 ? out.v[f] : out.w[f]; });
    // The final caller already needs these complete faces. Read them directly
    // for its global diagnostic instead of reconstructing all six again.
    if (final_mass) *final_mass = mass_diagnostics(operator_,fields_->icellflag,
        [&](int c,int i,int j,int k) { const auto f = domain.face(i,j,k); return c == 0 ? out.u[f] : c == 1 ? out.v[f] : out.w[f]; });
    phase_ = Phase::Finalized;
  } catch (...) { phase_ = Phase::Failed; fields_.reset(); throw; }
}
template<class Real> std::size_t SolverState<Real>::workspace_bytes() const {
  return (R.capacity()+lambda.capacity()+factors_.capacity())*sizeof(Real);
}
template<class Real> StudyState<Real> SolverState<Real>::copy_state_for_study() const {
  require_iterate();
  return {lambda,R};
}

template<class Real> double SolverState<Real>::row_residual(std::size_t c, int k) const {
  const auto a = operator_.stencil(c,k);
  const double values[] = {double(lambda[c]),double(R[c]),
    double(lambda[domain.cellAdd(c,1,0,0)]),double(lambda[domain.cellAdd(c,-1,0,0)]),
    double(lambda[domain.cellAdd(c,0,1,0)]),double(lambda[domain.cellAdd(c,0,-1,0)]),
    double(lambda[domain.cellAdd(c,0,0,1)]),double(lambda[domain.cellAdd(c,0,0,-1)])};
  for (double value : values) if (!std::isfinite(value))
    throw qes::RuntimeError("Non-finite completed-iterate residual operand");
  const double neighbours = double(a.e)*values[2]+double(a.f)*values[3]
    +double(a.g)*values[4]+double(a.h)*values[5]+double(a.m)*values[6]+double(a.n)*values[7];
  const double diagonal = double(a.e)+a.f+a.g+a.h+a.m+a.n;
  const double r = (neighbours-values[1])-diagonal*values[0];
  if (!std::isfinite(r)) throw qes::RuntimeError("Non-finite completed-iterate residual");
  return r;
}
template<class Real> EquationResidual SolverState<Real>::equation_residual(
    MassRegion region, ResidualNormalization floors) const {
  require_iterate();
  if (!std::isfinite(floors.maximum_floor) || floors.maximum_floor <= 0
      || !std::isfinite(floors.rms_floor) || floors.rms_floor <= 0)
    throw qes::InputError("Residual normalization floors must be finite and positive");
  const int nx=domain.nx()-1, ny=domain.ny()-1, nz=domain.nz()-2;
  if (region.i_last == -1) region.i_last=nx-1;
  if (region.j_last == -1) region.j_last=ny-1;
  if (region.k_last == -1) region.k_last=nz-1;
  if (region.i_first < 1 || region.i_last > nx-1 || region.i_last < region.i_first
      || region.j_first < 1 || region.j_last > ny-1 || region.j_last < region.j_first
      || region.k_first < 0 || region.k_last > nz-1 || region.k_last < region.k_first)
    throw qes::InputError("Residual region is outside the solved cells");
  EquationResidual out; out.iteration=iterations_; out.floors=floors;
  double square=0, rhs_square=0;
  // Fixed traversal makes diagnostic reductions reproducible across teams.
  for (int k=region.k_first+1; k<region.k_last+1; ++k)
    for (int j=region.j_first; j<region.j_last; ++j)
      for (int i=region.i_first; i<region.i_last; ++i) {
        const auto c=domain.cell(i,j,k);
        if (fields_->icellflag[c] == 0 || fields_->icellflag[c] == 2) {
          ++out.excluded_solid_cells; continue;
        }
        const double r=row_residual(c,k), b=double(R[c]);
        const double volume=double(domain.dx())*domain.dy()*domain.dz_array[k];
        out.maximum=std::max(out.maximum,std::abs(r));
        out.rhs_maximum=std::max(out.rhs_maximum,std::abs(b));
        square+=volume*r*r; rhs_square+=volume*b*b;
        out.volume+=volume; ++out.fluid_cells;
      }
  if (!std::isfinite(square) || !std::isfinite(rhs_square) || !std::isfinite(out.volume))
    throw qes::RuntimeError("Non-finite completed-iterate residual norm");
  if (out.fluid_cells) {
    out.volume_weighted_rms=std::sqrt(square/out.volume);
    out.rhs_volume_weighted_rms=std::sqrt(rhs_square/out.volume);
    out.relative_maximum=out.maximum/std::max(out.rhs_maximum,floors.maximum_floor);
    out.relative_volume_weighted_rms=out.volume_weighted_rms/std::max(out.rhs_volume_weighted_rms,floors.rms_floor);
    if (!std::isfinite(*out.relative_maximum) || !std::isfinite(*out.relative_volume_weighted_rms))
      throw qes::RuntimeError("Non-finite normalized completed-iterate residual");
  }
  return out;
}
template<class Real> CellDiagnostics SolverState<Real>::diagnose_cell(int i,int j,int k) const {
  require_iterate();
  // Neighbour access requires a lateral interior cell and a solved layer.
  if (i<1 || i>=domain.nx()-2 || j<1 || j>=domain.ny()-2 || k<0 || k>=domain.nz()-3)
    throw qes::InputError("Cell diagnostic requires an interior solved physical cell");
  const int sk=k+1;
  const auto c=domain.cell(i,j,sk);
  CellDiagnostics out; out.i=i; out.j=j; out.k=k; out.flag=fields_->icellflag[c];
  out.assessed=out.flag!=0 && out.flag!=2; out.top_band=sk==domain.nz()-3;
  out.multiplier=double(lambda[c]); out.rhs=double(R[c]); out.coefficients=operator_.stencil(c,sk);
  // Residual on excluded solid rows is retained as evidence, never assessed.
  out.equation_residual=row_residual(c,sk);
  const int di[]={1,-1,0,0,0,0}, dj[]={0,0,1,-1,0,0}, dk[]={0,0,0,0,1,-1};
  for (int a=0;a<6;++a) out.neighbour_multipliers[a]=double(lambda[domain.cell(i+di[a],j+dj[a],sk+dk[a])]);
  out.faces={face_value(0,i+1,j,sk),face_value(0,i,j,sk),face_value(1,i,j+1,sk),
             face_value(1,i,j,sk),face_value(2,i,j,sk+1),face_value(2,i,j,sk)};
  out.initial_faces={fields_->u0[domain.face(i+1,j,sk)],fields_->u0[domain.face(i,j,sk)],
    fields_->v0[domain.face(i,j+1,sk)],fields_->v0[domain.face(i,j,sk)],
    fields_->w0[domain.face(i,j,sk+1)],fields_->w0[domain.face(i,j,sk)]};
  for (const auto &values : {out.faces,out.initial_faces}) for (double value : values)
    if (!std::isfinite(value)) throw qes::RuntimeError("Non-finite cell diagnostic face");
  return out;
}

template<class Real> void SolverState<Real>::TrendTotals::merge(const TrendTotals &b) {
  maximum = std::max(maximum,b.maximum); weighted_square += b.weighted_square;
  volume += b.volume; cells += b.cells;
}
template<class Real> void SolverState<Real>::finish_residual(const TrendTotals &out) {
  if (!std::isfinite(out.maximum) || !std::isfinite(out.weighted_square))
    throw qes::RuntimeError("Non-finite algebraic residual trend");
  last_trend_ = ResidualTrend{iterations_+1,out.maximum,
    out.cells ? std::sqrt(out.weighted_square/out.volume) : 0,out.cells};
}

template class SolverState<float>;
template class SolverState<double>;
}
