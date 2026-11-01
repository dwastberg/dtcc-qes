#include "api/turbulence_reference.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace dtcc_qes {
TurbulenceReference turbulence_reference(std::vector<float> heights, float roughness)
{
  TurbulenceReference out;
  if (!std::isfinite(roughness) || roughness <= 0)
    throw std::invalid_argument("Turbulence roughness must be positive finite float32");
  for (float h : heights) if (!std::isfinite(h) || h <= 0)
    throw std::invalid_argument("Turbulence building heights must be positive finite float32 values");
  if (!heights.empty()) {
    // Same ascending float32 accumulation and double-literal products as QES.
    std::sort(heights.begin(), heights.end());
    for (float h : heights) out.mean_height += h;
    out.mean_height /= float(heights.size());
    out.maximum_height = heights.back();
    out.roughness_length = 0.1 * out.mean_height;
    out.displacement_height = 0.7 * out.mean_height;
    out.reference_height = 3.0 * out.mean_height;
  } else {
    out.roughness_length = roughness;
    out.reference_height = 100.0 * roughness;
  }
  if (!std::isfinite(out.reference_height) || out.reference_height <= 0)
    throw std::invalid_argument("Turbulence reference height must be positive and finite in float32");
  return out;
}

bool turbulence_margin(const std::vector<float> &faces, double reference)
{
  // Physical nz+1 faces start at zero. QES has one additional ground ghost:
  // physical[nz-3] is ghosted domain.z_face[nz-2].
  return faces.size() >= 4 && faces[faces.size()-4] >= reference && faces.back() >= 15;
}

TurbulenceExtension turbulence_extension(const std::vector<float> &faces, double reference,
                                        float thickness, int nx, int ny, std::int64_t max_cells)
{
  if (faces.size()<3 || faces.size()>10001 || faces.front()!=0 || nx<1 || ny<1 || nx>10000 || ny>10000 || max_cells<1)
    throw std::invalid_argument("Turbulence faces must be finite increasing float32 heights starting at zero");
  for (std::size_t i=0;i<faces.size();++i)
    if (!std::isfinite(faces[i]) || (i && faces[i]<=faces[i-1]))
      throw std::invalid_argument("Turbulence faces must be finite increasing float32 heights starting at zero");
  if (!std::isfinite(reference) || reference<=0)
    throw std::invalid_argument("Turbulence reference height must be positive and finite");
  if (!std::isfinite(thickness) || thickness<=0)
    throw std::invalid_argument("Turbulence tail thickness must be positive and finite in float32");
  TurbulenceExtension out{faces,0,{}};
  while (!turbulence_margin(out.faces,reference)) {
    const auto layers=out.faces.size()-1;
    if (layers>=10000) {out.limit="10000-layer limit";break;}
    if (std::int64_t(nx)*ny*std::int64_t(layers+1)>max_cells) {out.limit="max_cells limit";break;}
    if (std::int64_t(nx+1)*(ny+1)*std::int64_t(layers+3)>std::numeric_limits<int>::max()) {
      out.limit="native index limit";break;
    }
    const float top=out.faces.back()+thickness;
    if (!std::isfinite(top) || top<=out.faces.back()) {out.limit="float32 coordinate progress limit";break;}
    const float previous=.5f*(out.faces[out.faces.size()-2]+out.faces.back());
    const float centre=.5f*(out.faces.back()+top);
    if (!std::isfinite(centre) || centre<=previous) {out.limit="float32 cell-centre progress limit";break;}
    out.faces.push_back(top);++out.added_layers;
  }
  return out;
}
}
