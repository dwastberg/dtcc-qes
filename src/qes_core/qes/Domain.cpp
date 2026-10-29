#include <algorithm>
#include <cmath>
#include <limits>
#include "util/QESException.h"

#include "Domain.h"

using namespace qes;

namespace {
int layerCount(const std::vector<float> &layers)
{
  if (layers.size() < 2 || layers.size() > 10000)
    throw InputError("Explicit vertical grid requires 2..10000 physical layers");
  return static_cast<int>(layers.size());
}

float minimumLayer(const std::vector<float> &layers)
{
  layerCount(layers);
  for (float h : layers)
    if (!std::isfinite(h) || h <= 0)
      throw InputError("Vertical layers must be positive and finite");
  return *std::min_element(layers.begin(), layers.end());
}
}

Domain::Domain(const int &nx, const int &ny, const int &nz, const float &dx, const float &dy, const float &dz)
{
  if (nx < 1 || ny < 1 || nz < 1
      || !std::isfinite(dx) || !std::isfinite(dy) || !std::isfinite(dz)
      || dx <= 0.0f || dy <= 0.0f || dz <= 0.0f)
    throw InputError("Grid dimensions and spacing must be positive and finite");
  const long double faces = (static_cast<long double>(nx) + 1)
    * (static_cast<long double>(ny) + 1) * (static_cast<long double>(nz) + 2);
  if (faces > std::numeric_limits<int>::max())
    throw InputError("Grid exceeds QES's supported index range");

  // Internally this information is converted to the staggered grid
  // representation, which adds 1 to nx and ny and 2 to nz (to
  // account for staggered grid and ghost cell).
  domainData.nx = nx + 1;
  domainData.ny = ny + 1;
  domainData.nz = nz + 2;

  domainData.dx = dx;
  domainData.dy = dy;
  domainData.dz = dz;
  domainData.dxy = std::min(domainData.dx, domainData.dy);

  // Legacy uniform path; the explicit-layer overload replaces this spacing.
  defineVerticalStretching(domainData.dz);
  defineVerticalGrid();
  validateVerticalGrid();
  defineHorizontalGrid();
}

Domain::Domain(int nx, int ny, float dx, float dy, const std::vector<float> &layers)
  : Domain(nx, ny, layerCount(layers), dx, dy, minimumLayer(layers))
{
  defineVerticalStretching(layers);
  defineVerticalGrid();
  validateVerticalGrid();
}

bool Domain::verticallyUniform() const
{
  return !dz_array.empty() && std::all_of(dz_array.begin(), dz_array.end(),
    [&](float h) { return h == dz_array.front(); });
}

Domain::Domain(const Vector3Int& domain, const Vector3Float& grid)
  : Domain(domain[0], domain[1], domain[2], grid[0], grid[1], grid[2])
{}


void Domain::defineVerticalStretching(const float &dz_value)
{
  // vertical grid (can be uniform or stretched)
  dz_array.resize(domainData.nz - 1, 0.0);
  // Uniform vertical grid
  for (float &k : dz_array) {
    k = dz_value;
  }
}

void Domain::defineVerticalStretching(const std::vector<float> &dz_value)
{
  if (dz_value.size() != static_cast<std::size_t>(domainData.nz - 2))
    throw InputError("Vertical layer count does not match the domain");
  // vertical grid (can be uniform or stretched)
  dz_array.resize(domainData.nz - 1, 0.0);
  // Stretched vertical grid
  for (auto k = 1; k < dz_array.size(); ++k) {
    dz_array[k] = dz_value[k - 1];// Read in custom dz values and set them to dz_array
  }
  dz_array[0] = dz_array[1];// Value for ghost cell below the surface

  float newDz = *std::min_element(dz_array.begin(), dz_array.end());// Set dz to minimum value of
  domainData.dz = newDz;
}

void Domain::validateVerticalGrid() const
{
  for (const auto *axis : {&z_face, &z})
    for (std::size_t k = 0; k < axis->size(); ++k)
      if (!std::isfinite((*axis)[k]) || (k && (*axis)[k] <= (*axis)[k - 1]))
        throw InputError("Vertical coordinates must remain finite and strictly increasing in float32");
  for (std::size_t k = 1; k < dz_array.size(); ++k) {
    // Include both neighbours used by the solved bands and the mirrored ground.
    for (std::size_t n : {k - 1, std::min(k + 1, dz_array.size() - 1)}) {
      const float scale = dz_array[k] * (0.5f * (dz_array[k] + dz_array[n]));
      if (!std::isfinite(scale) || scale <= 0 || !std::isfinite(1.0f / scale) || 1.0f / scale <= 0)
        throw InputError("Vertical layers cannot form positive finite float32 solver coefficients");
    }
  }
}

void Domain::defineVerticalGrid()
{
  // Location of face in z-dir
  z_face.resize(domainData.nz, 0.0);
  z_face[0] = -dz_array[0];
  z_face[1] = 0.0;
  for (auto k = 2; k < z_face.size(); ++k) {
    z_face[k] = z_face[k - 1] + dz_array[k - 1];
  }

  // Location of cell centers in z-dir
  z.resize(domainData.nz - 1, 0.0);
  z[0] = -0.5f * dz_array[0];
  for (auto k = 1; k < z.size(); ++k) {
    z[k] = 0.5f * (z_face[k] + z_face[k + 1]);
  }
}

void Domain::defineHorizontalGrid()
{
  // horizontal grid (x-direction)
  x.resize(domainData.nx - 1);
  for (auto i = 0; i < domainData.nx - 1; ++i) {
    x[i] = ((float)i + 0.5f) * domainData.dx;// Location of face centers in x-dir
  }

  // horizontal grid (y-direction)
  y.resize(domainData.ny - 1);
  for (auto j = 0; j < domainData.ny - 1; ++j) {
    y[j] = ((float)j + 0.5f) * domainData.dy;// Location of face centers in y-dir
  }
}
