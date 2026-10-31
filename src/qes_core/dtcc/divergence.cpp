#include "divergence.h"
#include "winds/WINDSGeneralData.h"
#include "solver/mass_diagnostics.h"

namespace dtcc_qes {
DivergenceStats divergence_stats(const WINDSGeneralData &data, const solver::PoissonOperator &op, bool initial)
{
  const auto &u = initial ? data.u0 : data.u;
  const auto &v = initial ? data.v0 : data.v;
  const auto &w = initial ? data.w0 : data.w;
  const auto stats = solver::mass_diagnostics(op,data.icellflag,
    [&](int component,int i,int j,int k) {
      const auto f = data.domain.face(i,j,k);
      return component == 0 ? u[f] : component == 1 ? v[f] : w[f];
    });
  return {stats.interior_max,stats.interior_rms,stats.top_band_max,stats.cells,stats.top_band_cells};
}
}
