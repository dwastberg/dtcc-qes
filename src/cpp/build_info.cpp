#include "build_info.h"
#include "qes/Domain.h"
#include <stdexcept>

namespace dtcc_qes {
const char *qes_version() { return QES_VERSION_INFO; }
const char *qes_revision() { return DTCC_QES_QES_REVISION; }
bool openmp_enabled()
{
#ifdef _OPENMP
  return true;
#else
  return false;
#endif
}
const char *cpu_backend() { return openmp_enabled() ? "OpenMP CPU" : "serial CPU"; }

std::array<int, 3> core_grid_shape(int nx, int ny, int nz)
{
  // Private build smoke check; the owning wind runner is a later step.
  if (nx < 1 || ny < 1 || nz < 1 || nx > 10000 || ny > 10000 || nz > 10000)
    throw std::invalid_argument("Grid dimensions must be between 1 and 10000");
  qes::Domain domain(nx, ny, nz, 1.0f, 1.0f, 1.0f);
  const auto [x, y, z] = domain.getBaseDomainCellNum();
  return {x, y, z};
}
}
