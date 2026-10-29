#include "Domain.h"
#include "util/UnsupportedFeature.h"

qes::Domain::Domain(const std::string &)
{
  throw UnsupportedFeature("NetCDF domains require QES_ENABLE_IO=ON");
}
