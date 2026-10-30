#include "LayerProfile.h"
#include "WINDSGeneralData.h"
#include <stdexcept>

void applyLayerProfile(const InflowCondition &p, WINDSGeneralData *w)
{
  const auto &d = w->domain;
  if (p.layer_u.size() != static_cast<std::size_t>(d.nz()-2) || p.layer_v.size() != p.layer_u.size())
    throw std::invalid_argument("Layer table must have one u/v value per physical layer");
  // Exactly the physical bands written by applyLogProfile. applyWindProfile
  // clears all arrays first, so lower ghost and upper face remain zero.
  for (int k = 1; k < d.nz()-1; ++k)
    for (int j = 0; j < d.ny(); ++j)
      for (int i = 0; i < d.nx(); ++i) {
        const auto index = d.face(i,j,k);
        w->u0[index] = p.layer_u[k-1];
        w->v0[index] = p.layer_v[k-1];
        w->w0[index] = 0;
      }
}
