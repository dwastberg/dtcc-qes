#pragma once

#include <iosfwd>
#include <vector>
#include "solver/solver.h"

class WINDSGeneralData;
namespace dtcc_qes::solver { class PoissonOperator; }

// Study-only inspection of existing solver fields. No production solver hooks.
namespace study {
void write_solver_diagnostics(std::ostream &, const WINDSGeneralData &, const dtcc_qes::solver::PoissonOperator &,
                              const std::vector<float> &lambda,
                              const std::vector<float> &previous_lambda,
                              const std::vector<float> &rhs);
void diagnostics_self_test();
void write_precision_probe(std::ostream &, const WINDSGeneralData &, const dtcc_qes::solver::PoissonOperator &,
                           const std::vector<float> &lambda,
                           dtcc_qes::solver::SweepOrder order = dtcc_qes::solver::default_order());
}
