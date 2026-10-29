#include "qes/Domain.h"
#include "winds/WINDSGeneralData.h"
#include <tuple>

// Linked with every core object (whole archive) and compiled with the I/O
// library headers trapped, so the in-memory core can neither include nor
// reference them. The core has no file-backed constructors left to reject.
int main()
{
  qes::Domain domain(4, 3, 2, 2.0f, 2.0f, 2.0f);
  if (domain.getBaseDomainCellNum() != std::make_tuple(4, 3, 2))
    return 1;
  WINDSGeneralData data(qes::Domain(8, 8, 4, 2.0f, 2.0f, 2.0f), {}, BuildingParameterizations{}, 0.1f);
  return data.allBuildingsV.empty() ? 0 : 1;
}
