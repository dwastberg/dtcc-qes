// Tall-building zone (Parameterizations.tall_buildings; docs/tall-buildings.md).
//
// Around a building that is much taller than its neighbours the air near the ground is faster beside the
// building (corner streams) and reversed in front of it (standing vortex). The zone blends the initial field
// toward a target built from published speed ratios, after every other zone and before the projection.
// The ratios are scalar speeds, so a share of the target goes to the mean flow here and the rest is added
// as turbulence after the solve (wind_runner.cpp). Constants: TallBuildingModel (wake_model.h).
//
// - Eligibility: by the ratio of the roof height to the area-weighted mean roof height of the other
//   buildings nearby; a building without neighbours is not eligible, so isolated buildings are unchanged.
// - Reach: from the walls, cosine decay. Height: full weight near the ground, none above half the height.
// - Sector: the angle theta from the upwind direction about the centroid. The ratio runs from the vortex
//   value at 0 to the corner value at 90 degrees; the zone fades out between 90 and 150 degrees, so the
//   near wake is not touched. Faces a cavity wrote are skipped.
// - Direction: reversed on the upwind axis, tangential around the building beside it.
#include "WINDSGeneralData.h"
#include "PolyBuilding.h"
#include "../dtcc/api/wake_model.h"

#include <algorithm>
#include <cmath>
#include <vector>

namespace {
const double kPi = 3.14159265358979323846;
using dtcc_qes::TallBuildingModel;

double interpolate(const double *x, const double *y, int n, double at)
{
  if (at <= x[0]) return y[0];
  for (int i = 1; i < n; i++)
    if (at <= x[i]) return y[i - 1] + (y[i] - y[i - 1]) * (at - x[i - 1]) / (x[i] - x[i - 1]);
  return y[n - 1];
}

double smoothstep(double t)
{
  t = std::clamp(t, 0.0, 1.0);
  return t * t * (3.0 - 2.0 * t);
}

struct Footprint
{
  std::vector<double> x, y;// closed ring: last vertex repeats the first
  double area = 0, roof = 0, height = 0, base = 0, cx = 0, cy = 0;

  double distance(double px, double py) const// 0 inside
  {
    bool inside = false;
    double best = 1e30;
    for (std::size_t i = 0; i + 1 < x.size(); i++) {
      const double ax = x[i], ay = y[i], bx = x[i + 1], by = y[i + 1];
      if ((ay > py) != (by > py) && px < (bx - ax) * (py - ay) / (by - ay) + ax) inside = !inside;
      const double ex = bx - ax, ey = by - ay, len2 = ex * ex + ey * ey;
      const double t = len2 > 0 ? std::clamp(((px - ax) * ex + (py - ay) * ey) / len2, 0.0, 1.0) : 0.0;
      best = std::min(best, std::hypot(px - ax - t * ex, py - ay - t * ey));
    }
    return inside ? 0.0 : best;
  }
};
}// namespace

void WINDSGeneralData::applyTallBuildings(const std::vector<float> &inflow_u, const std::vector<float> &inflow_v)
{
  const double ratio_low = TallBuildingModel::ratio_low, ratio_high = TallBuildingModel::ratio_high;
  const double reach_factor = TallBuildingModel::reach, full_height = TallBuildingModel::full_height, top_height = TallBuildingModel::top_height;
  const double gamma = TallBuildingModel::mean_share;
  auto [nx, ny, nz] = domain.getDomainCellNum();
  const double dx = domain.dx(), dy = domain.dy();
  std::vector<Footprint> prints;
  for (auto *building : allBuildingsV) {
    Footprint p;
    for (const auto &v : building->polygonVertices) {
      p.x.push_back(v.x_poly);
      p.y.push_back(v.y_poly);
    }
    if (p.x.size() < 4) continue;
    for (std::size_t i = 0; i + 1 < p.x.size(); i++) p.area += 0.5 * (p.x[i] * p.y[i + 1] - p.x[i + 1] * p.y[i]);
    p.area = std::abs(p.area);
    p.base = building->base_height;
    p.height = building->H;
    p.roof = p.base + p.height;
    p.cx = building->building_cent_x;
    p.cy = building->building_cent_y;
    prints.push_back(std::move(p));
  }
  const bool has_wake = !wakeDeficitU.empty();
  tallBuildingWeight.assign(u0.size(), 0.0f);
  for (std::size_t n = 0; n < prints.size(); n++) {
    const Footprint &tower = prints[n];
    const double H = tower.roof;
    if (tower.base > 0 || H <= 0) continue;
    double weighted = 0, total = 0;
    for (std::size_t m = 0; m < prints.size(); m++) {
      if (m == n) continue;
      const Footprint &other = prints[m];
      double gap = 1e30;
      for (std::size_t i = 0; i + 1 < other.x.size(); i++) gap = std::min(gap, tower.distance(other.x[i], other.y[i]));
      for (std::size_t i = 0; i + 1 < tower.x.size(); i++) gap = std::min(gap, other.distance(tower.x[i], tower.y[i]));
      if (gap > TallBuildingModel::neighbourhood * H) continue;
      weighted += other.area * other.roof;
      total += other.area;
    }
    if (total <= 0) continue;// isolated: inactive
    const double eligibility = smoothstep((H / (weighted / total) - ratio_low) / (ratio_high - ratio_low));
    if (eligibility <= 0) continue;
    const double corner = interpolate(TallBuildingModel::corner_height, TallBuildingModel::corner_ratio, TallBuildingModel::corner_count, H);
    const double vortex = interpolate(TallBuildingModel::vortex_height, TallBuildingModel::vortex_ratio, TallBuildingModel::vortex_count, H);
    const double reach = reach_factor * H;
    // incident direction: the inflow at the reference height
    int k_ref = 1;
    for (int k = 1; k < nz - 1; k++)
      if (std::abs(domain.z[k] - TallBuildingModel::reference_height * H) < std::abs(domain.z[k_ref] - TallBuildingModel::reference_height * H)) k_ref = k;
    const double ref = std::hypot(inflow_u[k_ref], inflow_v[k_ref]);
    if (!(ref > 0)) continue;
    const double fx = inflow_u[k_ref] / ref, fy = inflow_v[k_ref] / ref;
    double x0 = 1e30, x1 = -1e30, y0 = 1e30, y1 = -1e30;
    for (std::size_t i = 0; i < tower.x.size(); i++) {
      x0 = std::min(x0, tower.x[i]); x1 = std::max(x1, tower.x[i]);
      y0 = std::min(y0, tower.y[i]); y1 = std::max(y1, tower.y[i]);
    }
    const int i0 = std::max(1, int((x0 - reach) / dx)), i1 = std::min(nx - 2, int((x1 + reach) / dx) + 1);
    const int j0 = std::max(1, int((y0 - reach) / dy)), j1 = std::min(ny - 2, int((y1 + reach) / dy) + 1);
    // weight and target unit vector at a point; returns the horizontal weight (0 outside the zone)
    auto zone = [&](double px, double py, double &ratio, double &tx, double &ty) {
      const double d = tower.distance(px, py);
      if (d <= 0 || d >= reach) return 0.0;
      const double rx = px - tower.cx, ry = py - tower.cy, r = std::hypot(rx, ry);
      if (!(r > 0)) return 0.0;
      const double along = rx * fx + ry * fy, cross = rx * fy - ry * fx;
      const double theta = std::atan2(std::abs(cross), -along);// 0 upwind, pi downwind
      double angular = 1.0;
      if (theta > 0.5 * kPi) {
        const double s = (theta - 0.5 * kPi) / (kPi / 3.0);
        if (s >= 1.0) return 0.0;
        angular = std::pow(std::cos(0.5 * kPi * s), 2.0);
      }
      const double sine = std::sin(std::min(theta, 0.5 * kPi));
      ratio = vortex + (corner - vortex) * sine * sine;
      // tangent around the building with a downstream component; reversed flow on the upwind axis
      double px_t = -ry / r, py_t = rx / r;
      if (px_t * fx + py_t * fy < 0) { px_t = -px_t; py_t = -py_t; }
      const double blend = smoothstep(theta / (0.25 * kPi));
      tx = blend * px_t - (1.0 - blend) * fx;
      ty = blend * py_t - (1.0 - blend) * fy;
      const double norm = std::hypot(tx, ty);
      if (!(norm > 0)) return 0.0;
      tx /= norm;
      ty /= norm;
      return 0.5 * (1.0 + std::cos(kPi * d / reach)) * angular;
    };
    auto solid = [&](int i, int j, int k) {
      const auto flag = icellflag[domain.cell(i, j, k)];
      return flag == 0 || flag == 2;
    };
    for (int k = 1; k < nz - 1; k++) {
      const double z = domain.z[k];
      if (z >= top_height * H) break;
      const double vertical = z <= full_height * H ? 1.0 : smoothstep((top_height * H - z) / ((top_height - full_height) * H));
      const double speed = std::hypot(inflow_u[k], inflow_v[k]);
      for (int j = j0; j <= j1; j++)
        for (int i = i0; i <= i1; i++) {
          const long f = domain.face(i, j, k);
          double ratio = 0, tx = 0, ty = 0;
          if (!solid(i, j, k) && !solid(i - 1, j, k) && !(has_wake && (wakeCavity[f] & 1))) {
            const double w = eligibility * vertical * zone(i * dx, (j + 0.5) * dy, ratio, tx, ty);
            if (w > 0) {
              u0[f] += float(w * (gamma * ratio * speed * tx - u0[f]));
              tallBuildingWeight[f] = std::max(tallBuildingWeight[f], float(w));
              if (has_wake) wakeDeficitU[f] *= float(1.0 - w);
            }
          }
          if (!solid(i, j, k) && !solid(i, j - 1, k) && !(has_wake && (wakeCavity[f] & 2))) {
            const double w = eligibility * vertical * zone((i + 0.5) * dx, j * dy, ratio, tx, ty);
            if (w > 0) {
              v0[f] += float(w * (gamma * ratio * speed * ty - v0[f]));
              if (has_wake) wakeDeficitV[f] *= float(1.0 - w);
            }
          }
        }
    }
  }
  wall->setVelocityZero(this);
}
