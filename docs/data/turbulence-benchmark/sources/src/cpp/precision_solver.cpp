// The stencil, boundaries and CPU order follow QES Solver_CPU / Solver_CPU_RB
// (University of Utah / Minnesota Duluth contributors, GPL-3.0-or-later).
#include "precision_solver.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESLog.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace dtcc_qes {
PrecisionSolver::PrecisionSolver(const qes::Domain &domain, double tolerance)
  : domain_(domain), tolerance_(tolerance)
{
  if (!std::isfinite(tolerance) || tolerance < std::numeric_limits<double>::epsilon())
    throw qes::InputError("Solver tolerance must be finite and at least float64 epsilon");
  lambda_.resize(domain.numCellCentered());
  rhs_.resize(domain.numCellCentered());
}

PrecisionDiagnostics PrecisionSolver::solve(WINDSGeneralData *data, int iterations, bool fixed_sweeps)
{
  if (!data || iterations < 1)
    throw qes::InputError("A prepared wind field and a positive iteration limit are required");
  const auto &d = domain_;
  auto &a = *data;
  if (a.domain.getDomainCellNum() != d.getDomainCellNum() || a.domain.dx() != d.dx()
      || a.domain.dy() != d.dy() || a.domain.dz_array != d.dz_array)
    throw qes::InputError("Solver and wind-field domains differ");
  for (const auto *v : {&a.u0, &a.v0, &a.w0, &a.e, &a.f, &a.g, &a.h, &a.m, &a.n}) {
    const auto count = (v == &a.u0 || v == &a.v0 || v == &a.w0)
      ? d.numFaceCentered() : d.numCellCentered();
    if (v->size() != static_cast<std::size_t>(count)
        || !std::all_of(v->begin(), v->end(), [](float x) { return std::isfinite(x); }))
      throw qes::InputError("Solver arrays must have the expected length and finite values");
  }
  std::fill(lambda_.begin(), lambda_.end(), 0.0);
  std::fill(rhs_.begin(), rhs_.end(), 0.0);
  auto &lambda = lambda_;
  auto &rhs = rhs_;
  const double dx = d.dx(), dy = d.dy();
  // alpha1 = alpha2 = 1, as in both embedded QES CPU solvers. Widen every
  // operand before arithmetic, including the sum of adjacent layer heights.
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i) {
      const auto c = d.cell(i,j,k), f = d.face(i,j,k);
      rhs[c] = -2.0 * ((double(a.e[c])*a.u0[f+1] - double(a.f[c])*a.u0[f])*dx
        + (double(a.g[c])*a.v0[f+d.nx()] - double(a.h[c])*a.v0[f])*dy
        + double(a.m[c])*0.5*(double(d.dz_array[k])+d.dz_array[k+1])*a.w0[f+d.nx()*d.ny()]
        - double(a.n[c])*0.5*(double(d.dz_array[k])+d.dz_array[k-1])*a.w0[f]);
    }
  // Preserve the existing relaxation constant, widened from its actual float.
  constexpr double omega = double(1.78f);
  double max_error = 0;
  int iter = 0;
  while (iter < iterations && (iter == 0 || fixed_sweeps || max_error > tolerance_)) {
    max_error = 0;
    int nonfinite = 0;
#ifdef _OPENMP
#pragma omp parallel reduction(max : max_error) reduction(| : nonfinite)
#endif
    {
#ifdef _OPENMP
      constexpr int colours = 2;
#else
      constexpr int colours = 1;
#endif
      for (int colour = 0; colour < colours; ++colour) {
#ifdef _OPENMP
#pragma omp for
#endif
        for (int k = 1; k < d.nz()-2; ++k)
          for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
            if (colours == 2 && (i+j+k)%2 != colour) continue;
            const auto c = d.cell(i,j,k);
            const double diagonal = double(a.e[c])+a.f[c]+a.g[c]+a.h[c]+a.m[c]+a.n[c];
            const double neighbours = double(a.e[c])*lambda[d.cellAdd(c,1,0,0)]
              + double(a.f[c])*lambda[d.cellAdd(c,-1,0,0)]
              + double(a.g[c])*lambda[d.cellAdd(c,0,1,0)]
              + double(a.h[c])*lambda[d.cellAdd(c,0,-1,0)]
              + double(a.m[c])*lambda[d.cellAdd(c,0,0,1)]
              + double(a.n[c])*lambda[d.cellAdd(c,0,0,-1)];
            const double next = omega/diagonal*(neighbours-rhs[c]) + (1.0-omega)*lambda[c];
            const double change = std::abs(next-lambda[c]);
            nonfinite |= !std::isfinite(change);
            max_error = std::max(max_error, change);
            lambda[c] = next;
          }
      }
#ifdef _OPENMP
#pragma omp for
#endif
      for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i)
        lambda[d.cell(i,j,0)] = lambda[d.cell(i,j,1)];
    }
    if (nonfinite) throw qes::RuntimeError("Non-finite Lagrange multiplier change during solve");
    ++iter;
  }
  a.u = a.u0; a.v = a.v0; a.w = a.w0;
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 1; j < d.ny()-1; ++j) for (int i = 1; i < d.nx()-1; ++i) {
      const auto c = d.cell(i,j,k), f = d.face(i,j,k);
      a.u[f] = float(double(a.u0[f]) + 0.5*double(a.f[c])*dx*(lambda[c]-lambda[c-1]));
      a.v[f] = float(double(a.v0[f]) + 0.5*double(a.h[c])*dy*(lambda[c]-lambda[d.cellAdd(c,0,-1,0)]));
      a.w[f] = float(double(a.w0[f]) + 0.5*double(a.n[c])*double(d.dz_array[k])
                     *(lambda[c]-lambda[d.cellAdd(c,0,0,-1)]));
    }
  for (int k = 1; k < d.nz()-1; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i) {
      const auto c = d.cell(i,j,k), f = d.face(i,j,k);
      if (a.icellflag[c] == 0 || a.icellflag[c] == 2) {
        a.u[f] = a.u[f+1] = 0;
        a.v[f] = a.v[f+d.nx()] = 0;
        a.w[f] = a.w[f+d.nx()*d.ny()] = 0;
      }
    }
  for (const auto *v : {&a.u, &a.v, &a.w})
    if (!std::all_of(v->begin(), v->end(), [](float x) { return std::isfinite(x); }))
      throw qes::RuntimeError("Non-finite corrected velocity during solve");
  return {iter, max_error, tolerance_, max_error <= tolerance_};
}
}
