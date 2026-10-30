#pragma once

#include "qes/Domain.h"
#include <vector>

class WINDSGeneralData;

namespace dtcc_qes {
struct PrecisionDiagnostics {
  int iterations;
  double max_lagrange_multiplier_change, tolerance;
  bool converged;
};

// Optional CPU solver. Geometry, coefficients and completed faces stay float32.
// Separate storage avoids allocating the legacy solver's three float buffers.
class PrecisionSolver {
public:
  PrecisionSolver(const qes::Domain &, double tolerance);
  // Every call starts from zero. Fixed sweeps are an internal study control;
  // the public runner always uses the multiplier-change stopping rule.
  PrecisionDiagnostics solve(WINDSGeneralData *, int iterations, bool fixed_sweeps = false);
  std::size_t workspace_bytes() const { return (lambda_.size() + rhs_.size()) * sizeof(double); }

private:
  qes::Domain domain_;
  double tolerance_;
  std::vector<double> lambda_, rhs_;
};
}
