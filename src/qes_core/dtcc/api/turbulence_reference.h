#pragma once
// Coordinate/scalar-only planning contract; no QES or Python types.
#include <cstdint>
#include <string>
#include <vector>

namespace dtcc_qes {
struct TurbulenceReference {
  float mean_height = 0, maximum_height = 0;
  float reference_height = 0, roughness_length = 0, displacement_height = 0;
};
TurbulenceReference turbulence_reference(std::vector<float> heights, float roughness);
bool turbulence_margin(const std::vector<float> &physical_faces, double reference);
struct TurbulenceExtension {
  std::vector<float> faces;
  int added_layers = 0;
  std::string limit;
};
TurbulenceExtension turbulence_extension(const std::vector<float> &physical_faces, double reference,
                                        float last_thickness, int nx, int ny, std::int64_t max_cells);
}
