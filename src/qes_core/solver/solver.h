// QES-derived mass-consistency solver; GPL-3.0-or-later. See cpu_float32.cpp
// for the original University of Utah / Minnesota Duluth contributor notices.
#pragma once

#include "qes/Domain.h"
#include <array>
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <vector>

class WINDSGeneralData;

namespace dtcc_qes::solver {

enum class SweepOrder { Lexicographic, RedBlack };
enum class StopRule { LegacyTolerance, FixedSweeps };
enum class Phase { Empty, Active, Finalized, Failed };
enum class Termination { None, LegacyTolerance, IterationLimit, FixedBudget };

constexpr SweepOrder default_order() { return SweepOrder::RedBlack; }

enum class OperatorStorage { Automatic, Explicit };
enum class CoefficientOwnership { Take };
struct Stencil { float e, f, g, h, m, n; };

// Immutable, owned coefficients. Construction from const geometry copies only
// the explicit fallback; production transfers and releases its setup arrays.
class PoissonOperator {
public:
  explicit PoissonOperator(const WINDSGeneralData &, OperatorStorage = OperatorStorage::Automatic);
  PoissonOperator(WINDSGeneralData &, CoefficientOwnership, OperatorStorage = OperatorStorage::Automatic);
  PoissonOperator(const PoissonOperator &) = delete;
  PoissonOperator &operator=(const PoissonOperator &) = delete;
  const qes::Domain domain;
  bool compact() const { return compact_; }
  std::size_t storage_bytes() const;
  std::size_t table_index(std::size_t c, int k) const { return std::size_t(k)*64 + masks_[c]; }
  const std::vector<Stencil> &tables() const { return tables_; }
  template<bool Compact> Stencil stencil(std::size_t c, int k) const {
    if constexpr (Compact) return tables_[table_index(c,k)];
    else return {explicit_[0][c],explicit_[1][c],explicit_[2][c],explicit_[3][c],explicit_[4][c],explicit_[5][c]};
  }
  Stencil stencil(std::size_t c, int k) const {
    return compact_ ? stencil<true>(c,k) : stencil<false>(c,k);
  }
  float coefficient(int axis, std::size_t c) const;
private:
  bool compact_ = false;
  std::vector<std::uint8_t> masks_;
  std::vector<Stencil> tables_;
  std::array<std::vector<float>,6> explicit_;
  void build(const WINDSGeneralData &, WINDSGeneralData *, OperatorStorage);
};

// The current post-parameterization flags belong to the condition, not the
// geometry operator. All borrowed inputs remain unchanged until finalization.
struct ConditionInputs {
  const qes::Domain &domain;
  const std::vector<float> &u0, &v0, &w0;
  const std::vector<int> &icellflag;
  explicit ConditionInputs(const WINDSGeneralData &);
};

struct FaceDestination {
  std::vector<float> &u, &v, &w;
  explicit FaceDestination(WINDSGeneralData &);
};

// Physical zero-based cell layers, [first, last). Empty intervals are allowed.
struct LayerRange { int first, last; };
struct CenteredDestination {
  std::vector<float> &velocity;
  std::vector<std::int32_t> &cell_flags;
};
struct Observation {
  LayerRange layers;
  int nx = 0, ny = 0;
  std::vector<float> velocity;
  std::vector<std::int32_t> cell_flags;
};

// Physical zero-based cells. Defaults retain the existing excluded lateral and
// highest-layer regions, with the last solved layer reported separately.
struct MassRegion {
  int i_first = 1, i_last = -1, j_first = 1, j_last = -1;
  int k_first = 0, k_last = -1;
};
struct MassDiagnostics {
  double interior_max = 0, interior_rms = 0, top_band_max = 0;
  std::size_t cells = 0, top_band_cells = 0;
  struct Flux {
    double net_cell_flux = 0, boundary_flux = 0, absolute_cell_flux = 0, throughflow = 0;
    std::size_t low_flow_cells = 0, resolved_cells = 0, unassessed_cells = 0;
    std::optional<double> relative_max, relative_rms;
  } interior_flux, top_band_flux;
};
struct FluxOptions {
  bool enabled = false;
  double reference_speed = 0;
  // Experimental, explicitly supplied; no calibrated default. Threshold is
  // fraction * Uref * half the sum of absolute effective face areas (m^3/s).
  std::optional<double> low_flow_fraction;
};
struct ResidualTrend {
  // Widened algebraic neighbors - RHS - diagonal*old_lambda at update time.
  // Partly updated iterate, native RHS units; never physical divergence s^-1.
  int iteration = 0;
  double maximum = 0, volume_weighted_rms = 0;
  std::size_t fluid_cells = 0;
};
struct SolveDiagnostics {
  int iterations = 0;
  double max_lagrange_multiplier_change = 0, tolerance = 0;
  bool converged = false;
};
struct WorkReport {
  int completed_sweeps;
  SolveDiagnostics diagnostics;
  Termination termination;
};
template<class Real> struct StudyState {
  std::vector<Real> multipliers, rhs;
};

template<class Real> class SolverState {
public:
  explicit SolverState(const PoissonOperator &, double tolerance = 1e-5,
                       SweepOrder = default_order(), float relaxation = 1.78f);
  SolverState(const SolverState &) = delete;
  SolverState &operator=(const SolverState &) = delete;

  void begin(ConditionInputs, int total_sweeps, StopRule = StopRule::LegacyTolerance);
  WorkReport advance(int work_sweeps, bool collect_residual_trend = false);
  Observation observe(LayerRange) const;
  void observe(LayerRange, CenteredDestination) const;
  MassDiagnostics diagnose(MassRegion = {}, FluxOptions = {}) const;
  const PoissonOperator &prepared_operator() const { return operator_; }
  std::uint64_t condition_epoch() const { require_iterate(); return condition_epoch_; }
  std::optional<ResidualTrend> residual_trend() const { require_iterate(); return last_trend_; }
  void finalize(FaceDestination, std::optional<CenteredDestination> = std::nullopt,
                MassDiagnostics *final_mass = nullptr);
  SolveDiagnostics diagnostics() const;
  Phase phase() const { return phase_; }
  SweepOrder order() const { return order_; }
  Termination termination() const;
  std::size_t workspace_bytes() const;
  StudyState<Real> copy_state_for_study() const;

private:
  // Preserve the legacy kernel names and arithmetic types inside the kernels.
  struct KernelFields {
    const std::vector<float> &u0, &v0, &w0;
    const std::vector<int> &icellflag;
  };
  const PoissonOperator &operator_;
  const qes::Domain &domain;
  const double tolerance_;
  const SweepOrder order_;
  const Real omega;
  const int alpha1 = 1, alpha2 = 1;
  std::vector<Real> R, lambda;
  std::vector<Real> factors_;
  std::optional<KernelFields> fields_;
  Phase phase_ = Phase::Empty;
  StopRule stop_rule_ = StopRule::LegacyTolerance;
  int iterations_ = 0, total_sweeps_ = 0;
  Real last_change_ = 0;
  std::uint64_t condition_epoch_ = 0;
  bool collect_residual_ = false;
  std::optional<ResidualTrend> last_trend_;
  struct TrendTotals {
    double maximum = 0, weighted_square = 0, volume = 0;
    std::size_t cells = 0;
    void merge(const TrendTotals &b);
  };
  void add_residual(TrendTotals &out,std::size_t c,int k,const Stencil &a,Real previous) const {
    if (fields_->icellflag[c] == 0 || fields_->icellflag[c] == 2) return;
    const double neighbours = double(a.e)*double(lambda[domain.cellAdd(c,1,0,0)])
      + double(a.f)*double(lambda[domain.cellAdd(c,-1,0,0)])
      + double(a.g)*double(lambda[domain.cellAdd(c,0,1,0)])
      + double(a.h)*double(lambda[domain.cellAdd(c,0,-1,0)])
      + double(a.m)*double(lambda[domain.cellAdd(c,0,0,1)])
      + double(a.n)*double(lambda[domain.cellAdd(c,0,0,-1)]);
    const double diagonal = double(a.e)+a.f+a.g+a.h+a.m+a.n;
    const double residual = (neighbours-double(R[c]))-diagonal*double(previous);
    const double volume = double(domain.dx())*domain.dy()*domain.dz_array[k];
    out.maximum = std::max(out.maximum,std::abs(residual));
    out.weighted_square += volume*residual*residual; out.volume += volume; ++out.cells;
  }
  void finish_residual(const TrendTotals &);
  void require_iterate() const;
  void build_rhs();
  Real sweep_lexicographic();
  Real sweep_red_black();
  float corrected_face(int component, int i, int j, int k) const;
  float face_value(int component, int i, int j, int k) const;
  bool solid(int i, int j, int k) const;
  template<bool Compact> Real factor(std::size_t c, int k, const Stencil &a) const {
    if constexpr (Compact) return factors_[operator_.table_index(c,k)];
    else return omega/(Real(a.e)+a.f+a.g+a.h+a.m+a.n);
  }
  template<bool Compact> void rhs32();
  template<bool Compact, bool Trend> Real lex32();
  template<bool Compact, bool Trend> Real rb32();
  template<bool Compact> void rhs64();
  template<bool Compact, bool Trend> Real ordered64();
};

template<> void SolverState<float>::build_rhs();
template<> float SolverState<float>::sweep_lexicographic();
template<> float SolverState<float>::sweep_red_black();
template<> float SolverState<float>::corrected_face(int, int, int, int) const;
template<> void SolverState<double>::build_rhs();
template<> double SolverState<double>::sweep_lexicographic();
template<> double SolverState<double>::sweep_red_black();
template<> float SolverState<double>::corrected_face(int, int, int, int) const;
extern template class SolverState<float>;
extern template class SolverState<double>;

// Embedding/test convenience: orchestration of the same phases, never another
// kernel. Production WindRunner calls the phases itself.
template<class Real> SolveDiagnostics solve_wind(SolverState<Real> &state,
    WINDSGeneralData &wind, int sweeps, StopRule rule = StopRule::LegacyTolerance) {
  state.begin(ConditionInputs(wind), sweeps, rule);
  state.advance(sweeps);
  state.finalize(FaceDestination(wind));
  return state.diagnostics();
}
}
