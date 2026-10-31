#pragma once
#include <array>

namespace dtcc_qes {
const char *qes_version();
const char *qes_revision();
bool openmp_enabled();
const char *cpu_backend();
std::array<int, 3> core_grid_shape(int nx, int ny, int nz);
}
