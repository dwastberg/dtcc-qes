#include "model_inputs.h"
#include "turbulence.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace dtcc_qes {
namespace {
float narrow(double value, const char *name)
{
  if (!std::isfinite(value) || std::abs(value) > std::numeric_limits<float>::max())
    throw std::invalid_argument(std::string(name) + " must be finite and representable as float32");
  return static_cast<float>(value);
}

float positive(double value, const char *name)
{
  const float result = narrow(value, name);
  if (result <= 0)
    throw std::invalid_argument(std::string(name) + " must be positive in float32");
  return result;
}

void flag(int value, int maximum, const char *name)
{
  if (value < 0 || value > maximum)
    throw std::invalid_argument(std::string("Unsupported ") + name);
}

double cross(const polyVert &a, const polyVert &b, const polyVert &c) {
  return (double(b.x_poly) - a.x_poly) * (double(c.y_poly) - a.y_poly) -
         (double(b.y_poly) - a.y_poly) * (double(c.x_poly) - a.x_poly);
}
bool on_segment(const polyVert &a, const polyVert &b, const polyVert &p) {
  return cross(a, b, p) == 0 && p.x_poly >= std::min(a.x_poly, b.x_poly) && p.x_poly <= std::max(a.x_poly, b.x_poly) &&
         p.y_poly >= std::min(a.y_poly, b.y_poly) && p.y_poly <= std::max(a.y_poly, b.y_poly);
}
bool intersects(const polyVert &a, const polyVert &b, const polyVert &c, const polyVert &d) {
  const auto ab_c = cross(a, b, c), ab_d = cross(a, b, d), cd_a = cross(c, d, a), cd_b = cross(c, d, b);
  return (((ab_c > 0 && ab_d < 0) || (ab_c < 0 && ab_d > 0)) && ((cd_a > 0 && cd_b < 0) || (cd_a < 0 && cd_b > 0))) ||
         on_segment(a, b, c) || on_segment(a, b, d) || on_segment(c, d, a) || on_segment(c, d, b);
}
bool in_ring(const std::vector<polyVert> &v, std::size_t begin, std::size_t end, const polyVert &p) {
  bool inside = false;
  for (auto i = begin; i + 1 < end; ++i) {
    const auto &a = v[i], &b = v[i + 1];
    if ((a.y_poly > p.y_poly) != (b.y_poly > p.y_poly) &&
        p.x_poly < a.x_poly + (double(p.y_poly) - a.y_poly) * (b.x_poly - a.x_poly) / (b.y_poly - a.y_poly))
      inside = !inside;
  }
  return inside;
}
void validate_rings(const std::vector<polyVert> &v, const std::vector<std::size_t> &offsets) {
  double net = 0;
  for (std::size_t r = 0; r + 1 < offsets.size(); ++r) {
    const auto begin = offsets[r], end = offsets[r + 1];
    if (end - begin < 4 || v[begin].x_poly != v[end - 1].x_poly || v[begin].y_poly != v[end - 1].y_poly)
      throw std::invalid_argument("Each building ring must be closed with at least four vertices");
    double area = 0;
    for (auto i = begin; i + 1 < end; ++i) {
      area += double(v[i].x_poly) * v[i + 1].y_poly - double(v[i].y_poly) * v[i + 1].x_poly;
      for (auto j = i + 1; j + 1 < end; ++j) {
        if (j == i + 1 || (i == begin && j == end - 2))
          continue;
        if (intersects(v[i], v[i + 1], v[j], v[j + 1]))
          throw std::invalid_argument("Building rings must be simple without self intersections");
      }
    }
    if ((r == 0 && area >= 0) || (r > 0 && area <= 0))
      throw std::invalid_argument(
          "Building outer ring must have positive area and clockwise winding; holes counter-clockwise");
    net += area;
    for (std::size_t other = 0; other < r; ++other) {
      for (auto i = begin; i + 1 < end; ++i)
        for (auto j = offsets[other]; j + 1 < offsets[other + 1]; ++j)
          if (intersects(v[i], v[i + 1], v[j], v[j + 1]))
            throw std::invalid_argument("Building rings may not touch or intersect");
      if (other > 0 &&
          (in_ring(v, offsets[other], offsets[other + 1], v[begin]) || in_ring(v, begin, end, v[offsets[other]])))
        throw std::invalid_argument("Building holes may not overlap or nest");
    }
    if (r > 0 && !in_ring(v, 0, offsets[1], v[begin]))
      throw std::invalid_argument("Building hole must be inside its outer ring");
  }
  if (net >= 0)
    throw std::invalid_argument("Building must have positive net area");
}

std::vector<float> narrow_layers(const GridConfig &grid) {
  if (grid.dz_layers.size() != static_cast<std::size_t>(grid.nz))
    throw std::invalid_argument("Vertical layer count must match nz");
  std::vector<float> layers;
  for (double h : grid.dz_layers) layers.push_back(positive(h, "Vertical layer thickness"));
  return layers;
}
}

std::vector<float> vertical_faces(const GridConfig &grid)
{
  // Construct only coordinate vectors, never the much larger wind arrays. This
  // reuses the core's accumulation and validation for preparation and roof checks.
  const float spacing = positive(grid.cell_size, "Cell size");
  const auto domain = grid.dz_layers.empty()
    ? qes::Domain(grid.nx, grid.ny, grid.nz, spacing, spacing, spacing)
    : qes::Domain(grid.nx, grid.ny, spacing, spacing, narrow_layers(grid));
  return {domain.z_face.begin() + 1, domain.z_face.end()};
}

qes::Domain make_domain(const ModelInputs &inputs)
{
  if (!inputs.layers.empty())
    return qes::Domain(inputs.nx, inputs.ny, inputs.spacing, inputs.spacing, inputs.layers);
  return qes::Domain(inputs.nx, inputs.ny, inputs.nz, inputs.spacing, inputs.spacing, inputs.spacing);
}

float qes_tolerance(const SolverOptions &options)
{
  const float tolerance = positive(options.tolerance, "Solver tolerance");
  if (options.tolerance < std::numeric_limits<float>::epsilon())
    throw std::invalid_argument("Solver tolerance must be at least float32 epsilon");
  if (options.max_iterations < 1)
    throw std::invalid_argument("Maximum iterations must be positive");
  return tolerance;
}

double solver_tolerance(const SolverOptions &options)
{
  if (options.precision == "float32") return qes_tolerance(options);
  if (options.precision != "float64")
    throw std::invalid_argument("Solver precision must be 'float32' or 'float64'");
  if (!std::isfinite(options.tolerance) || options.tolerance < std::numeric_limits<double>::epsilon())
    throw std::invalid_argument("Solver tolerance must be finite and at least float64 epsilon");
  if (options.max_iterations < 1)
    throw std::invalid_argument("Maximum iterations must be positive");
  return options.tolerance;
}

ModelInputs::ModelInputs(const GridConfig &grid, const ModelSettings &model, const BuildingArrays &arrays,
                         const TurbulenceSettings &settings)
{
  configure_turbulence(turbulence, settings);
  turbulence_enabled = settings.enabled;
  if (grid.nx < 3 || grid.ny < 3 || grid.nz < 2
      || grid.nx > 10000 || grid.ny > 10000 || grid.nz > 10000)
    throw std::invalid_argument("Grid requires 3..10000 cells in x/y and 2..10000 in z");
  const auto cells = std::int64_t(grid.nx) * grid.ny * grid.nz;
  const auto faces = std::int64_t(grid.nx + 1) * (grid.ny + 1) * (grid.nz + 2);
  if (grid.max_cells < 1 || cells > grid.max_cells || faces > std::numeric_limits<int>::max())
    throw std::invalid_argument("Grid exceeds the cell limit or QES index range");
  spacing = positive(grid.cell_size, "Cell size");
  if (!std::isfinite(spacing * spacing) || spacing * spacing == 0
      || !std::isfinite(1.0f / (spacing * spacing)))
    throw std::invalid_argument("Cell size cannot form finite float32 solver coefficients");
  nx = grid.nx;
  ny = grid.ny;
  nz = grid.nz;
  const auto faces_z = vertical_faces(grid);
  if (!grid.dz_layers.empty()) {
    layers = narrow_layers(grid);
    // Explicit layers select QES's nonuniform derivatives even when equal.
    turbulence.verticalStretching = 1;
  }
  // Defaults until set_condition: a neutral log profile from one sensor.
  inflow.site_z0 = positive(model.roughness_length, "Roughness length");
  inflow.site_one_overL = 0;
  inflow.site_z_ref = 10.0f;
  inflow.site_U_ref = 5.0f;
  inflow.site_wind_dir = 270.0f;
  inflow.site_xcoord = narrow(model.sensor_x, "Sensor x");
  inflow.site_ycoord = narrow(model.sensor_y, "Sensor y");
  if (inflow.site_xcoord < 0 || inflow.site_xcoord >= grid.nx * spacing
      || inflow.site_ycoord < 0 || inflow.site_ycoord >= grid.ny * spacing)
    throw std::invalid_argument("Sensor must be inside the horizontal domain");
  turbulence.site_z0 = inflow.site_z0;
  parameterizations.wallRoughness = positive(model.wall_roughness, "Wall roughness");
  flag(model.rooftop_flag, 2, "rooftop flag");
  flag(model.upwind_cavity_flag, 3, "upwind cavity flag");
  flag(model.street_canyon_flag, 1, "street canyon flag");
  flag(model.street_intersection_flag, 1, "street intersection flag");
  flag(model.wake_flag, 2, "wake flag");
  flag(model.high_rise_flag, 1, "high rise flag");
  flag(model.sidewall_flag, 1, "sidewall flag");
  // street_intersection_flag is validated but, as in QES, has no model.
  parameterizations.rooftopFlag = model.rooftop_flag;
  parameterizations.upwindCavityFlag = model.upwind_cavity_flag;
  parameterizations.streetCanyonFlag = model.street_canyon_flag;
  parameterizations.wakeFlag = model.wake_flag;
  parameterizations.highRiseFlag = model.high_rise_flag;
  parameterizations.sidewallFlag = model.sidewall_flag;
  parameterizations.exposedFaces = model.exposed_faces;
  parameterizations.canonicalFaces = !arrays.ring_offsets.empty();

  parameterizations.validateWakeDependencies();

  const auto count = arrays.heights.size();
  if (arrays.vertices.size() % 2 || arrays.offsets.size() != count + 1
      || arrays.base_heights.size() != count || arrays.ids.size() != count)
    throw std::invalid_argument("Building array lengths are inconsistent");
  const auto vertex_count = arrays.vertices.size() / 2;
  if (arrays.offsets.front() != 0 || arrays.offsets.back() < 0
      || static_cast<std::uint64_t>(arrays.offsets.back()) != vertex_count)
    throw std::invalid_argument("Offsets must span the complete vertex array, starting at zero");
  if (count > static_cast<std::size_t>(std::numeric_limits<int>::max()))
    throw std::invalid_argument("Too many buildings");
  const auto &ring_offsets = arrays.ring_offsets.empty() ? arrays.offsets : arrays.ring_offsets;
  if (ring_offsets.empty() || ring_offsets.front()!=0 || ring_offsets.back()!=static_cast<std::int64_t>(vertex_count))
    throw std::invalid_argument("Ring offsets must span all vertices starting at zero");
  for (std::size_t i=1; i<ring_offsets.size(); ++i)
    if (ring_offsets[i]<0 || ring_offsets[i]>static_cast<std::int64_t>(vertex_count)
        || ring_offsets[i]<=ring_offsets[i-1] || ring_offsets[i]-ring_offsets[i-1]<4)
      throw std::invalid_argument("Ring offsets must increase by at least four vertices");
  for (auto offset: arrays.offsets)
    if (!std::binary_search(ring_offsets.begin(),ring_offsets.end(),offset))
      throw std::invalid_argument("Building offsets must align with ring boundaries");
  std::unordered_set<std::int64_t> ids;
  // Use QES's actual float32 accumulation for the roof guard, rather than a
  // double-precision estimate of the top cell centre.
  const float top_centre = 0.5f * (faces_z[grid.nz - 1] + faces_z[grid.nz]);
  for (std::size_t b = 0; b < count; ++b) {
    const auto begin = arrays.offsets[b], end = arrays.offsets[b + 1];
    if (begin < 0 || end < begin || static_cast<std::uint64_t>(end) > vertex_count || end - begin < 4)
      throw std::invalid_argument("Offsets must be increasing and each closed ring needs at least four vertices");
    if (arrays.ids[b] < 0 || arrays.ids[b] > std::numeric_limits<int>::max() || !ids.insert(arrays.ids[b]).second)
      throw std::invalid_argument("Building IDs must be unique nonnegative int32 values");
    const float height = positive(arrays.heights[b], "Building height");
    const float base = narrow(arrays.base_heights[b], "Building base");
    if (arrays.base_heights[b] != 0)
      throw std::invalid_argument("Flat-ground buildings must have zero base height");
    // QES's vertical building scan requires a physical cell centre above roofs.
    if (height >= top_centre)
      throw std::invalid_argument("Building needs clearance below the top physical cell centre");
    std::vector<std::size_t> local_offsets;
    for (auto offset: ring_offsets) if (offset>=begin && offset<=end)
      local_offsets.push_back(static_cast<std::size_t>(offset-begin));
    std::vector<polyVert> ring;
    ring.reserve(static_cast<std::size_t>(end - begin));
    for (auto v = begin; v < end; ++v) {
      const float x = narrow(arrays.vertices[2 * v], "Vertex x");
      const float y = narrow(arrays.vertices[2 * v + 1], "Vertex y");
      // Leave cells around the footprint for QES's stencil and centroid reads.
      if (x < 2 * spacing || y < 2 * spacing || x >= (grid.nx - 2) * spacing || y >= (grid.ny - 2) * spacing)
        throw std::invalid_argument("Building footprint needs at least two cells of domain clearance");
      if (!ring.empty() && !std::binary_search(ring_offsets.begin(),ring_offsets.end(),v)
          && x == ring.back().x_poly && y == ring.back().y_poly)
        throw std::invalid_argument("Footprint has an edge that collapses in float32");
      ring.emplace_back(x, y);
    }
    validate_rings(ring, local_offsets);
    // IDs are validated for the caller; the model numbers buildings by position.
    buildings.push_back({std::move(ring), height, base, std::move(local_offsets)});
  }
}

void ModelInputs::set_condition(const WindCondition &condition)
{
  // Validate and narrow the complete condition before replacing active inputs.
  InflowCondition candidate = inflow;
  candidate.profile_kind = condition.profile_kind;
  candidate.layer_u.clear(); candidate.layer_v.clear();
  candidate.site_U_ref = narrow(condition.speed, "Wind speed");
  candidate.site_wind_dir = narrow(condition.direction, "Wind direction");
  candidate.site_z_ref = positive(condition.reference_height, "Reference height");
  if (condition.speed < 0 || condition.direction < 0 || condition.direction >= 360)
    throw std::invalid_argument("Wind speed must be nonnegative and direction must be in [0, 360)");
  if (condition.profile_kind == ProfileKind::Log) {
    if (!condition.layer_u.empty() || !condition.layer_v.empty())
      throw std::invalid_argument("Log conditions cannot contain a layer table");
    const float ratio = (candidate.site_z_ref + candidate.site_z0) / candidate.site_z0;
    if (!std::isfinite(ratio) || ratio <= 1)
      throw std::invalid_argument("Reference height and roughness cannot form a finite float32 log profile");
  } else if (condition.profile_kind == ProfileKind::LayerTable) {
    if (condition.layer_u.size() != static_cast<std::size_t>(nz) || condition.layer_v.size() != condition.layer_u.size())
      throw std::invalid_argument("Layer table must have one u/v value per physical layer");
    candidate.layer_u.reserve(nz); candidate.layer_v.reserve(nz);
    for (int k = 0; k < nz; ++k) {
      const float u = narrow(condition.layer_u[k], "Layer u"), v = narrow(condition.layer_v[k], "Layer v");
      const float speed = narrow(std::hypot(double(u), double(v)), "Layer speed");
      narrow(1.2 * speed, "Layer velocity limit");
      candidate.layer_u.push_back(u); candidate.layer_v.push_back(v);
    }
  } else {
    throw std::invalid_argument("Unsupported profile kind");
  }
  inflow = std::move(candidate);
}
}
