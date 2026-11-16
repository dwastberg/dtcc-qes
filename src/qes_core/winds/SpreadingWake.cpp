#include "SpreadingWake.h"

#include <algorithm>
#include <cmath>

// The expressions keep the operand types and the order of the research
// prototype (experiments/fabel_wake/spread_wake.inc), so that the two agree to
// rounding: float extents and angles, double arithmetic.

SpreadingWake::SpreadingWake(const SpreadingWakeFootprint &footprint, const qes::Domain &domain, double spread)
  : domain_(domain), spread_(spread),
    x1_(footprint.x1), x2_(footprint.x2), y1_(footprint.y1), y2_(footprint.y2),
    centre_x_(footprint.centre_x), centre_y_(footprint.centre_y),
    cos_(std::cos(footprint.direction)), sin_(std::sin(footprint.direction)),
    base_(footprint.base), top_(footprint.top)
{
  auto [nx, ny, nz] = domain.getDomainCellNum();
  const double dx = domain.dx(), dy = domain.dy(), dxy = domain.dxy();
  sigma_min_ = 0.5 * dxy;
  if (!(y2_ > y1_) || !(spread_ >= 0)) return;
  active_ = true;

  // Edge offset: thickness of the roof and side separation bubble at the trailing
  // edge (the Röckle rooftop shape); zero once the bubble has reattached.
  {
    const double small = std::min(double(footprint.width), double(footprint.height));
    const double large = std::max(double(footprint.width), double(footprint.height));
    const double scale = std::pow(small, 2.0 / 3.0) * std::pow(large, 1.0 / 3.0);
    const double length = SpreadingWakeModel::bubble_length * scale;
    const double along = footprint.area / (y2_ - y1_);
    const double shape = 1.0 - std::pow((0.5 * length - along) / (0.5 * length), 2.0);
    if (along < length && shape > 0) bubble_ = SpreadingWakeModel::bubble * scale * std::sqrt(shape);
  }

  // Lee wall per cross-wind strip: the most downstream crossing of the strip's
  // centreline with a face edge. Upstream of it, inside [y1, y2], G is zero.
  strips_ = std::max(1, int(std::ceil((y2_ - y1_) / (0.5 * dxy))));
  strip_width_ = (y2_ - y1_) / strips_;
  lee_.assign(strips_, -1e30);
  const auto &xi = *footprint.xi, &yi = *footprint.yi;
  for (int t = 0; t < strips_; t++) {
    const double yt = y1_ + (t + 0.5) * strip_width_;
    for (std::size_t id = 0; id + 1 < xi.size(); id++) {
      if (!footprint.face[id]) continue;
      const double ya = yi[id], yb = yi[id + 1];
      if (ya == yb || (ya - yt) * (yb - yt) > 0) continue;
      lee_[t] = std::max(lee_[t], xi[id] + (yt - ya) / (yb - ya) * (double(xi[id + 1]) - xi[id]));
    }
  }

  // Reach: march downstream until the centreline value falls below the cut at
  // the ground and at mid-height; the taper starts where it first falls below
  // twice the cut.
  const double reach_max = std::hypot(nx * dx, ny * dy);
  const double mid_y = 0.5 * (y1_ + y2_);
  const double mid_z = std::min(0.5 * (base_ + top_), top_);
  for (reach_ = x2_ + dxy; reach_ < reach_max; reach_ += 2 * dxy) {
    const double sigma = std::max(spread_ * (reach_ - x1_), sigma_min_);
    const double at_mid = across(mid_y, sigma) * vertical(mid_z, sigma);
    const double at_ground = across(mid_y, sigma) * vertical(0.0, sigma);
    if (at_mid < SpreadingWakeModel::reach_cut && at_ground < SpreadingWakeModel::reach_cut) break;
    if (taper_from_ < 0 && at_mid < SpreadingWakeModel::taper_start && at_ground < SpreadingWakeModel::taper_start)
      taper_from_ = reach_;
  }

  // Evaluated region: the grid-aligned box around [x1, x_r] x [-half, half],
  // and the layers up to the top edge plus three sigma.
  const double sigma_end = std::max(spread_ * (reach_ - x1_), sigma_min_);
  const double half = std::max(-y1_, y2_) + 3.0 * sigma_end + bubble_;
  const double z_top = top_ + 3.0 * sigma_end + bubble_;
  double bx0 = 1e30, bx1 = -1e30, by0 = 1e30, by1 = -1e30;
  for (double xr : { double(x1_), reach_ })
    for (double yr : { -half, half }) {
      const double gx = xr * cos_ - yr * sin_ + centre_x_, gy = xr * sin_ + yr * cos_ + centre_y_;
      bx0 = std::min(bx0, gx); bx1 = std::max(bx1, gx); by0 = std::min(by0, gy); by1 = std::max(by1, gy);
    }
  i0_ = std::max(1, int(std::floor(bx0 / dx)));
  i1_ = std::min(nx - 2, int(std::ceil(bx1 / dx)));
  j0_ = std::max(1, int(std::floor(by0 / dy)));
  j1_ = std::min(ny - 2, int(std::ceil(by1 / dy)));
  k1_ = 1;
  while (k1_ < nz - 2 && domain.z[k1_] < z_top) k1_++;
}

double SpreadingWake::across(double y, double sigma) const
{
  static const double r2 = std::sqrt(2.0);
  const double a = y1_ - bubble_, b = y2_ + bubble_;
  return 0.5 * (std::erf((y - a) / (r2 * sigma)) - std::erf((y - b) / (r2 * sigma)));
}

double SpreadingWake::vertical(double z, double sigma) const
{
  static const double r2 = std::sqrt(2.0);
  const double a = std::max(base_ - (base_ > 0 ? bubble_ : 0.0), 0.0), b = top_ + bubble_;
  // On the ground (a = 0) the image terms erf(z) and erf(-z) cancel exactly,
  // which halves the cost of the hottest expression (W1d).
  if (a == 0) return 0.5 * (std::erf((b + z) / (r2 * sigma)) + std::erf((b - z) / (r2 * sigma)));
  return 0.5 * (std::erf((z - a) / (r2 * sigma)) - std::erf((z - b) / (r2 * sigma))
                + std::erf((-z - a) / (r2 * sigma)) - std::erf((-z - b) / (r2 * sigma)));
}

double SpreadingWake::column(double gx, double gy, double &sigma) const
{
  const double px = gx - centre_x_, py = gy - centre_y_;
  const double xr = px * cos_ + py * sin_, yr = -px * sin_ + py * cos_;
  if (xr <= x1_ || xr > reach_) return 0.0;
  if (yr > y1_ && yr < y2_) {
    const int t = std::min(strips_ - 1, int((yr - y1_) / strip_width_));
    if (xr < lee_[t]) return 0.0;// upstream of the lee wall: the building, a notch or a courtyard
  }
  sigma = std::max(spread_ * (xr - x1_), sigma_min_);
  double fade = 1.0;
  if (taper_from_ > 0 && xr > taper_from_) {
    const double s = (reach_ - xr) / (reach_ - taper_from_);
    fade = s * s * (3.0 - 2.0 * s);
  }
  return fade * across(yr, sigma);
}

bool SpreadingWake::inRegion(int i, int j, int k) const
{
  return active_ && i >= i0_ && i <= i1_ && j >= j0_ && j <= j1_ && k >= 1 && k <= k1_;
}

float SpreadingWake::point(int component, int i, int j, int k) const
{
  if (!inRegion(i, j, k)) return 0.0f;
  const double dx = domain_.dx(), dy = domain_.dy();
  double sigma = 0;
  const double g = component == 0 ? column(i * dx, (j + 0.5) * dy, sigma) : column((i + 0.5) * dx, j * dy, sigma);
  if (g < SpreadingWakeModel::skip) return 0.0f;
  const double z = domain_.z[k];
  if (z > top_ + bubble_ + SpreadingWakeModel::layer_cut * sigma) return 0.0f;
  return float(std::min(g * vertical(z, sigma), 1.0));
}

void SpreadingWake::accumulate(double roof_speed2, std::vector<float> &deficit_u, std::vector<float> &deficit_v,
                               std::vector<float> &roof_speed2_u, bool root_sum_squares) const
{
  if (!active_) return;
  const double dx = domain_.dx(), dy = domain_.dy();
  // Deficits combine by the largest (wake code 3 as released) or, with the tall-building option, by the
  // root sum of squares, so that weak wakes that overlap add up. The roof-speed field keeps the largest.
  auto combine = [root_sum_squares](float before, float g) {
    return root_sum_squares ? std::min(1.0f, std::sqrt(before * before + g * g)) : std::max(before, g);
  };
#pragma omp parallel for schedule(dynamic, 4)
  for (int j = j0_; j <= j1_; j++) {
    for (int i = i0_; i <= i1_; i++) {
      double sigma_u = 0, sigma_v = 0;
      const double gu = column(i * dx, (j + 0.5) * dy, sigma_u);
      const double gv = column((i + 0.5) * dx, j * dy, sigma_v);
      if (gu < SpreadingWakeModel::skip && gv < SpreadingWakeModel::skip) continue;
      // Each column ends where Fz has fallen below 1e-9: z > z_c + 6 sigma(x).
      const double top_u = gu >= SpreadingWakeModel::skip ? top_ + bubble_ + SpreadingWakeModel::layer_cut * sigma_u : -1;
      const double top_v = gv >= SpreadingWakeModel::skip ? top_ + bubble_ + SpreadingWakeModel::layer_cut * sigma_v : -1;
      for (int k = 1; k <= k1_; k++) {
        const double z = domain_.z[k];
        if (z > top_u && z > top_v) break;
        const long f = domain_.face(i, j, k);
        if (z <= top_u) {
          const double g = std::min(gu * vertical(z, sigma_u), 1.0);
          deficit_u[f] = combine(deficit_u[f], float(g));
          roof_speed2_u[f] = std::max(roof_speed2_u[f], float(roof_speed2 * g));
        }
        if (z <= top_v)
          deficit_v[f] = combine(deficit_v[f], float(std::min(gv * vertical(z, sigma_v), 1.0)));
      }
    }
  }
}
