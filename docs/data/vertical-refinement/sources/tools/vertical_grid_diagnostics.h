#pragma once

#include <iosfwd>
#include <vector>

class WINDSGeneralData;

// Study-only inspection of existing solver fields. No production solver hooks.
namespace study {
void write_solver_diagnostics(std::ostream &, const WINDSGeneralData &,
                              const std::vector<float> &lambda,
                              const std::vector<float> &previous_lambda,
                              const std::vector<float> &rhs);
void diagnostics_self_test();
void write_precision_probe(std::ostream &, const WINDSGeneralData &,
                           const std::vector<float> &lambda);
}
