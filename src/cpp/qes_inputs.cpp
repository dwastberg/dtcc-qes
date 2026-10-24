#include "qes_inputs.h"
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

QESInputs::QESInputs(const GridConfig &grid, const ModelSettings &model, const BuildingArrays &arrays)
{
  if (grid.nx < 3 || grid.ny < 3 || grid.nz < 2
      || grid.nx > 10000 || grid.ny > 10000 || grid.nz > 10000)
    throw std::invalid_argument("Grid requires 3..10000 cells in x/y and 2..10000 in z");
  const auto cells = std::int64_t(grid.nx) * grid.ny * grid.nz;
  const auto faces = std::int64_t(grid.nx + 1) * (grid.ny + 1) * (grid.nz + 2);
  if (grid.max_cells < 1 || cells > grid.max_cells || faces > std::numeric_limits<int>::max())
    throw std::invalid_argument("Grid exceeds the cell limit or QES index range");
  const float spacing = positive(grid.cell_size, "Cell size");
  if (!std::isfinite(spacing * spacing) || spacing * spacing == 0
      || !std::isfinite(1.0f / (spacing * spacing)))
    throw std::invalid_argument("Cell size cannot form finite float32 solver coefficients");
  simulation.domain = {grid.nx, grid.ny, grid.nz};
  simulation.grid = {spacing, spacing, spacing};
  // All other simulation members use the explicit, I/O-free defaults: flat,
  // no halos, uniform spacing, stair-step mesh and logLawFlag=0.
  simulation.totalTimeIncrements = 1;
  series.time = std::string("2020-01-01T00:00:00");
  series.site_z0 = positive(model.roughness_length, "Roughness length");
  series.site_blayer_flag = 1;
  series.site_one_overL = 0;
  series.site_z_ref = {10.0f};
  series.site_U_ref = {5.0f};
  series.site_wind_dir = {270.0f};
  sensor.site_coord_flag = 1;
  sensor.site_xcoord = narrow(model.sensor_x, "Sensor x");
  sensor.site_ycoord = narrow(model.sensor_y, "Sensor y");
  if (sensor.site_xcoord < 0 || sensor.site_xcoord >= grid.nx * spacing
      || sensor.site_ycoord < 0 || sensor.site_ycoord >= grid.ny * spacing)
    throw std::invalid_argument("Sensor must be inside the horizontal domain");
  sensor.TS = {&series};
  met.sensors = {&sensor};
  met.z0_domain_flag = 0;
  buildings.wallRoughness = positive(model.wall_roughness, "Wall roughness");
  flag(model.rooftop_flag, 2, "rooftop flag");
  flag(model.upwind_cavity_flag, 3, "upwind cavity flag");
  flag(model.street_canyon_flag, 1, "street canyon flag");
  flag(model.street_intersection_flag, 1, "street intersection flag");
  flag(model.wake_flag, 2, "wake flag");
  flag(model.high_rise_flag, 1, "high rise flag");
  flag(model.sidewall_flag, 1, "sidewall flag");
  buildings.rooftopFlag = model.rooftop_flag;
  buildings.upwindCavityFlag = model.upwind_cavity_flag;
  buildings.streetCanyonFlag = model.street_canyon_flag;
  buildings.streetIntersectionFlag = model.street_intersection_flag;
  buildings.wakeFlag = model.wake_flag;
  buildings.highRiseFlag = model.high_rise_flag;
  buildings.sidewallFlag = model.sidewall_flag;

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
  std::unordered_set<std::int64_t> ids;
  // Use QES's actual float32 accumulation for the roof guard, rather than a
  // double-precision estimate of the top cell centre.
  float top_face = 0, previous_face = 0;
  for (int k = 0; k < grid.nz; ++k) {
    previous_face = top_face;
    top_face += spacing;
  }
  const float top_centre = 0.5f * (previous_face + top_face);
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
    std::vector<polyVert> ring;
    ring.reserve(static_cast<std::size_t>(end - begin));
    for (auto v = begin; v < end; ++v) {
      const float x = narrow(arrays.vertices[2 * v], "Vertex x");
      const float y = narrow(arrays.vertices[2 * v + 1], "Vertex y");
      // Leave cells around the footprint for QES's stencil and centroid reads.
      if (x < 2 * spacing || y < 2 * spacing || x >= (grid.nx - 2) * spacing || y >= (grid.ny - 2) * spacing)
        throw std::invalid_argument("Building footprint needs at least two cells of domain clearance");
      if (!ring.empty() && x == ring.back().x_poly && y == ring.back().y_poly)
        throw std::invalid_argument("Footprint has an edge that collapses in float32");
      ring.emplace_back(x, y);
    }
    if (ring.front().x_poly != ring.back().x_poly || ring.front().y_poly != ring.back().y_poly)
      throw std::invalid_argument("Building footprint must be closed");
    double area = 0;
    for (std::size_t v = 1; v < ring.size(); ++v)
      area += double(ring[v - 1].x_poly) * ring[v].y_poly - double(ring[v].x_poly) * ring[v - 1].y_poly;
    if (area >= 0)
      throw std::invalid_argument("Building footprint must have positive area and clockwise winding");
    polygons.push_back(std::make_unique<PolyBuilding>(ring, height, base, static_cast<int>(arrays.ids[b])));
    buildings.buildings.push_back(polygons.back().get());
  }
  buildings.numBuildings = static_cast<int>(count);
  input.simParams = &simulation;
  input.metParams = &met;
  input.buildingsParams = &buildings;
}

void QESInputs::set_condition(const WindCondition &condition)
{
  const float speed = narrow(condition.speed, "Wind speed");
  const float direction = narrow(condition.direction, "Wind direction");
  const float height = positive(condition.reference_height, "Reference height");
  if (condition.speed < 0 || condition.direction < 0 || condition.direction >= 360)
    throw std::invalid_argument("Wind speed must be nonnegative and direction must be in [0, 360)");
  const float ratio = (height + series.site_z0) / series.site_z0;
  if (!std::isfinite(ratio) || ratio <= 1)
    throw std::invalid_argument("Reference height and roughness cannot form a finite float32 log profile");
  series.site_U_ref[0] = speed;
  series.site_wind_dir[0] = direction;
  series.site_z_ref[0] = height;
}
}
