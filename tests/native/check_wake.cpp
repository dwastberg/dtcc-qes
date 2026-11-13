// Spreading far wake, wake code 3 (WAKE_UPDATE_V2.md, sections 3.1 and 5).
#include "building_fixtures.h"
#include "model_inputs.h"
#include "winds/WINDSGeneralData.h"
#include "winds/PolyBuilding.h"
#include "winds/SpreadingWake.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _OPENMP
#include <omp.h>
#endif

using namespace dtcc_qes;
using test_fixture::append;
static void require(bool value, const std::string &message)
{
  if (!value) throw std::runtime_error(message);
}

// ---------------------------------------------------------------------------
// Unit level: one footprint in a wind frame along +x, extents as polygonWake.
struct Frame
{
  std::vector<float> xi, yi;
  SpreadingWakeFootprint footprint;
};

static std::unique_ptr<Frame> frame(const std::vector<std::vector<std::array<double, 2>>> &rings, double height,
                                    double base, double cx, double cy, double direction = 0.0)
{
  auto f = std::make_unique<Frame>();
  auto &fp = f->footprint;
  const float dir = direction, c = std::cos(dir), s = std::sin(dir);
  float area = 0;
  for (const auto &ring : rings) {
    for (std::size_t n = 0; n < ring.size(); n++) {
      const float x = ring[n][0], y = ring[n][1];
      f->xi.push_back((x - float(cx)) * c + (y - float(cy)) * s);
      f->yi.push_back(-(x - float(cx)) * s + (y - float(cy)) * c);
      fp.face.push_back(n + 1 < ring.size());
      if (n + 1 < ring.size()) area += 0.5f * float(x * ring[n + 1][1] - y * ring[n + 1][0]);
    }
  }
  for (std::size_t id = 0; id + 1 < f->xi.size(); id++) {
    if (!fp.face[id]) continue;
    fp.x1 = std::min(fp.x1, f->xi[id]); fp.x2 = std::max(fp.x2, f->xi[id]);
    fp.y1 = std::min(fp.y1, f->yi[id]); fp.y2 = std::max(fp.y2, f->yi[id]);
  }
  fp.xi = &f->xi; fp.yi = &f->yi;
  fp.area = std::abs(area);
  fp.width = fp.area / (fp.x2 - fp.x1);
  fp.height = height; fp.base = base; fp.top = base + height;
  fp.direction = dir; fp.centre_x = cx; fp.centre_y = cy;
  return f;
}

static std::vector<std::array<double, 2>> box(double x0, double y0, double x1, double y1)
{
  return { { x0, y0 }, { x0, y1 }, { x1, y1 }, { x1, y0 }, { x0, y0 } };
}

struct Fields
{
  std::vector<float> du, dv, k;
  explicit Fields(const qes::Domain &d) : du(d.numFaceCentered()), dv(d.numFaceCentered()), k(d.numFaceCentered()) {}
};

static void box_checks()
{
  // 20 m cube, wind along +x, centred in y; 2 m cells, 4 m layers. The domain
  // contains the whole evaluated region.
  qes::Domain domain(250, 170, 46, 2, 2, 4);
  auto f = frame({ box(40, 160, 60, 180) }, 20, 0, 50, 170);
  SpreadingWake wake(f->footprint, domain);
  require(wake.active(), "Box wake inactive");
  auto [nx, ny, nz] = domain.getDomainCellNum();
  int i0, i1, j0, j1, k1;
  wake.region(i0, i1, j0, j1, k1);
  require(j0 > 1 && j1 < ny - 2 && k1 < nz - 2 && i1 < nx - 2, "Test domain clips the evaluated region");
  // The grid-aligned region bounds can differ by one row between the two sides;
  // there only the truncated tail (below 0.002) may differ.
  const auto bound = [&](int j, int mirror) { return j == j0 || j == j1 || mirror == j0 || mirror == j1; };
  Fields out(domain);
  wake.accumulate(25.0, out.du, out.dv, out.k);
  for (int k = 1; k < nz - 1; k++)
    for (int j = 1; j < ny - 1; j++)
      for (int i = 1; i < nx - 1; i++) {
        const long n = domain.face(i, j, k);
        require(out.du[n] >= 0 && out.du[n] <= 1 && out.dv[n] >= 0 && out.dv[n] <= 1, "D outside [0, 1]");
        // Symmetric about y = 170: u faces at (j + 1/2) dy mirror to ny - 2 - j, v faces at j dy to ny - 1 - j.
        const int mu = ny - 2 - j, mv = ny - 1 - j;
        require(std::abs(out.du[n] - out.du[domain.face(i, mu, k)]) <= (bound(j, mu) ? 0.002f : 1e-5f), "D not symmetric in y (u)");
        if (mv > 0 && mv < ny - 1)
          require(std::abs(out.dv[n] - out.dv[domain.face(i, mv, k)]) <= (bound(j, mv) ? 0.002f : 1e-5f), "D not symmetric in y (v)");
        if (i * 2.0 <= 40.0) require(out.du[n] == 0, "D upstream of x1");
        if ((i + 0.5) * 2.0 <= 40.0) require(out.dv[n] == 0, "D upstream of x1 (v)");
        // point() is the value accumulate writes.
        require(wake.point(0, i, j, k) == out.du[n] && wake.point(1, i, j, k) == out.dv[n], "point differs from field");
        require(out.k[n] == float(25.0 * out.du[n]) || std::abs(out.k[n] - 25.0f * out.du[n]) <= 1e-5f * 25.0f,
                "U_H^2 G differs from D");
      }

  // Truncation: along the centreline (v faces at y = 170, ground layer) the
  // deficit decays monotonically from the lee wall; across the taper and the end
  // of the reach no step exceeds 0.01; small values on the region bounds.
  require(wake.taperFrom() > 0 && wake.taperFrom() < wake.reach(), "No end taper");
  const int jc = 85;
  for (int i = 30; i + 1 < nx - 1; i++) {
    const double x = (i + 0.5) * 2.0 - 50;// wind frame
    if (x <= 10) continue;// downstream of the lee wall
    const float a = out.dv[domain.face(i, jc, 1)], b = out.dv[domain.face(i + 1, jc, 1)];
    require(b <= a, "Centreline deficit increases at i=" + std::to_string(i));
    if (x >= wake.taperFrom() - 4.0)
      require(a - b <= 0.01f, "Truncation step above 0.01 at i=" + std::to_string(i));
  }
  require(out.dv[domain.face(int((50 + wake.reach()) / 2.0) + 2, jc, 1)] == 0, "Deficit beyond the reach");
  float edge = 0;
  for (int k = 1; k <= k1; k++)
    for (int i = i0; i <= i1; i++)
      for (int j : { j0, j1 }) edge = std::max({ edge, out.du[domain.face(i, j, k)], out.dv[domain.face(i, j, k)] });
  for (int j = j0; j <= j1; j++)
    for (int i = i0; i <= i1; i++) edge = std::max({ edge, out.du[domain.face(i, j, k1)], out.dv[domain.face(i, j, k1)] });
  require(edge < 0.002f, "Deficit on the region bounds: " + std::to_string(edge));
}

static void integral_check()
{
  // A 200 m tall slab: at mid-height Fz ~ 1, so the cross-wind integral of D is
  // that of Fy, which the spreading must conserve.
  qes::Domain domain(250, 150, 60, 2, 2, 5);
  auto f = frame({ box(40, 140, 60, 160) }, 200, 0, 50, 150);
  SpreadingWake wake(f->footprint, domain);
  int k = 1;
  while (domain.z[k] < 100) k++;
  double first = 0;
  for (double distance : { 30.0, 60.0, 90.0, 120.0 }) {
    const int i = int((40 + distance) / 2.0);
    double sum = 0;
    for (int j = 1; j < 150; j++) sum += wake.point(0, i, j, k) * 2.0;
    if (first == 0) first = sum;
    require(std::abs(sum / first - 1) < 0.01, "Cross-wind integral not conserved at " + std::to_string(distance) + " m");
  }
  const double expected = 20 + 2 * wake.edgeOffset();
  require(std::abs(first / expected - 1) < 0.01, "Cross-wind integral is not the shadow width");
}

static void shadow_check()
{
  // c_s = 0: sigma stays dxy / 2, so D is the shadow indicator away from its edges.
  qes::Domain domain(250, 150, 40, 2, 2, 4);
  auto f = frame({ box(40, 140, 60, 160) }, 20, 0, 50, 150);
  SpreadingWake wake(f->footprint, domain, 0.0);
  const double half = 10 + wake.edgeOffset();
  for (int i = 32; i < 240; i++)
    for (int j = 1; j < 150; j++) {
      const double y = (j + 0.5) * 2.0 - 150;
      const float d = wake.point(0, i, j, 1);
      if (std::abs(y) < half - 4) require(d > 0.99f, "Shadow interior not 1");
      if (std::abs(y) > half + 4) require(d < 0.01f, "Shadow exterior not 0");
    }
}

static void crossing_check()
{
  // A 10 m cube beside a 40 m tower: the wakes merge downstream. The combined
  // U_H^2 G never steps more between adjacent faces than one building's own
  // field does (no jump where the larger wake changes owner).
  qes::Domain domain(300, 150, 30, 2, 2, 4);
  auto small = frame({ box(40, 120, 50, 130) }, 10, 0, 45, 125);
  auto tower = frame({ box(40, 140, 60, 160) }, 40, 0, 50, 150);
  SpreadingWake a(small->footprint, domain), b(tower->footprint, domain);
  Fields fa(domain), fb(domain), both(domain);
  const double ua = 25.0, ub = 64.0;// roof speeds 5 and 8 m/s
  a.accumulate(ua, fa.du, fa.dv, fa.k);
  b.accumulate(ub, fb.du, fb.dv, fb.k);
  a.accumulate(ua, both.du, both.dv, both.k);
  b.accumulate(ub, both.du, both.dv, both.k);
  auto [nx, ny, nz] = domain.getDomainCellNum();
  const double uref2 = 25.0, c = SpreadingWakeModel::turbulence;
  int crossing = 0;
  for (int k = 1; k < 4; k++)
    for (int j = 1; j < ny - 2; j++)
      for (int i = 1; i < nx - 2; i++) {
        const long n = domain.face(i, j, k);
        for (long m : { domain.face(i + 1, j, k), domain.face(i, j + 1, k) }) {
          const double step = std::abs(double(both.k[n]) - both.k[m]);
          const double own = std::max(std::abs(double(fa.k[n]) - fa.k[m]), std::abs(double(fb.k[n]) - fb.k[m]));
          require(step <= own + 1e-4, "Combined step exceeds both buildings' steps");
          // Where both wakes are present, beyond the tower's cavity (about x = 100 m):
          if (fa.du[n] > 0.05 && fb.du[n] > 0.05 && fa.du[m] > 0.05 && fb.du[m] > 0.05 && i * 2.0 > 100) {
            crossing++;
            require(c * step <= 0.02 * uref2, "k_w step above 0.02 U_ref^2 where the wakes cross");
          }
        }
      }
  require(crossing > 20, "Fixture has no crossing region: " + std::to_string(crossing));
}

static void footprint_checks()
{
  qes::Domain domain(100, 100, 20, 1, 1, 2);
  // L-shape with the notch open upstream: upstream bar x 20-40, y 20-30;
  // downstream bar x 40-50, y 20-50. The notch x 20-40, y 30-50 lies upstream
  // of the lee wall (x = 50) in its strips.
  auto l = frame({ { { 20, 20 }, { 20, 30 }, { 40, 30 }, { 40, 50 }, { 50, 50 }, { 50, 20 }, { 20, 20 } } }, 15, 0, 35, 35);
  SpreadingWake lw(l->footprint, domain);
  bool downstream = false;
  for (int k = 1; k < 10; k++)
    for (int j = 31; j < 49; j++)
      for (int i = 21; i < 40; i++) require(lw.point(0, i, j, k) == 0 && lw.point(1, i, j, k) == 0, "Deficit in the L notch");
  for (int j = 31; j < 49; j++) downstream |= lw.point(0, 55, j, 1) > 0.5f;
  require(downstream, "No deficit behind the L");
  // Courtyard: hole x 30-40, y 30-40 in a 30 m square.
  auto court = frame({ box(20, 20, 50, 50), { { 30, 30 }, { 40, 30 }, { 40, 40 }, { 30, 40 }, { 30, 30 } } }, 12, 0, 35, 35);
  SpreadingWake cw(court->footprint, domain);
  for (int k = 1; k < 10; k++)
    for (int j = 31; j < 40; j++)
      for (int i = 31; i < 40; i++) require(cw.point(0, i, j, k) == 0 && cw.point(1, i, j, k) == 0, "Deficit in the courtyard");
  // Raised building: the lower edge is max(base - delta, 0); the upper edge the physical roof plus delta.
  // A thin slab across the wind keeps an edge offset (L < 0.9 R).
  auto raised = frame({ box(20, 20, 24, 40) }, 10, 10, 22, 30);
  SpreadingWake rw(raised->footprint, domain);
  require(rw.edgeOffset() > 0, "No edge offset for a thin slab");
  require(rw.lowerEdge() == std::max(10 - rw.edgeOffset(), 0.0), "Raised lower edge");
  require(rw.upperEdge() == 20 + rw.edgeOffset(), "Raised upper edge");
  auto grounded = frame({ box(20, 20, 24, 40) }, 10, 0, 22, 30);
  require(SpreadingWake(grounded->footprint, domain).lowerEdge() == 0, "Grounded lower edge");
  // Below a raised building near its lee wall the deficit is small.
  require(rw.point(0, 28, 30, 1) < 0.05f && rw.point(0, 28, 30, 7) > 0.5f, "Raised wake not lifted");
}

static void point_field_check()
{
  // Ten buildings, oblique wind: max_c point_c equals the accumulated field on every face.
  qes::Domain domain(120, 100, 25, 2, 2, 2);
  std::vector<std::unique_ptr<Frame>> frames;
  std::vector<SpreadingWake> wakes;
  wakes.reserve(10);
  const double direction = 0.3;
  for (int n = 0; n < 10; n++) {
    const double x = 20 + 18 * (n % 5), y = 25 + 40 * (n / 5) + 3 * n, w = 6 + n % 3 * 3, h = 6 + 3 * n;
    frames.push_back(frame({ box(x, y, x + w, y + w * 0.8) }, h, 0, x + w / 2, y + w * 0.4, direction));
    wakes.emplace_back(frames.back()->footprint, domain);
  }
  Fields out(domain);
  for (std::size_t n = 0; n < wakes.size(); n++) wakes[n].accumulate(10.0 + n, out.du, out.dv, out.k);
  auto [nx, ny, nz] = domain.getDomainCellNum();
  for (int k = 0; k < nz; k++)
    for (int j = 0; j < ny; j++)
      for (int i = 0; i < nx; i++) {
        float du = 0, dv = 0;
        for (const auto &w : wakes) du = std::max(du, w.point(0, i, j, k)), dv = std::max(dv, w.point(1, i, j, k));
        const long n = domain.face(i, j, k);
        require(du == out.du[n] && dv == out.dv[n], "Point evaluation differs from the field");
      }
}

// ---------------------------------------------------------------------------
// Pipeline level: applyParametrizations with wake code 3.
static std::unique_ptr<WINDSGeneralData> initial(const GridConfig &grid, ModelSettings settings,
                                                 const BuildingArrays &arrays, double direction,
                                                 std::vector<float> *u_after_wake = nullptr,
                                                 std::vector<float> *v_after_wake = nullptr)
{
  ModelInputs input(grid, settings, arrays);
  WindCondition condition;
  condition.direction = direction;
  input.set_condition(condition);
  auto data = std::make_unique<WINDSGeneralData>(make_domain(input), input.buildings, input.parameterizations, .1);
  data->applyWindProfile(input.inflow);
  auto *raw = data.get();
  data->applyParametrizations([&](const char *stage) {
    if (std::string(stage) == "wake" && u_after_wake) *u_after_wake = raw->u0, *v_after_wake = raw->v0;
  });
  return data;
}

static void pipeline_checks()
{
  GridConfig grid;
  grid.nx = 100; grid.ny = 80; grid.nz = 24; grid.cell_size = 2;
  ModelSettings settings;
  settings.sensor_x = 5; settings.sensor_y = 5; settings.wake_flag = 3;
  BuildingArrays forward{ {}, { 0 }, {}, {}, {} }, reverse{ {}, { 0 }, {}, {}, {} };
  const std::vector<std::array<double, 4>> blocks{ { 20, 40, 30, 50 }, { 20, 60, 30, 70 }, { 80, 50, 90, 60 }, { 140, 30, 150, 40 } };
  for (const auto &b : blocks)
    append(forward, { b[0], b[1], b[0], b[3], b[2], b[3], b[2], b[1], b[0], b[1] }, 12);
  for (auto b = blocks.rbegin(); b != blocks.rend(); ++b)
    append(reverse, { (*b)[0], (*b)[1], (*b)[0], (*b)[3], (*b)[2], (*b)[3], (*b)[2], (*b)[1], (*b)[0], (*b)[1] }, 12);
  std::vector<float> u1, v1, u2, v2;
  auto a = initial(grid, settings, forward, 268, &u1, &v1);
  auto b = initial(grid, settings, reverse, 268, &u2, &v2);
  require(a->wakeDeficitU == b->wakeDeficitU && a->wakeDeficitV == b->wakeDeficitV, "D depends on building order");
  require(a->wakeRoofSpeed2U == b->wakeRoofSpeed2U, "k_w depends on building order");
  require(u1 == u2 && v1 == v2, "Wake stage velocities depend on building order");
  float maximum = 0;
  for (auto d : a->wakeDeficitU) maximum = std::max(maximum, d);
  require(maximum > 0.5f && maximum <= 1, "Deficit range");
  int far_wake = 0;
  for (auto flag : a->icellflag) far_wake += flag == 5;
  require(far_wake == 0, "Far-wake flags with wake code 3");

  // Codes 1 and 2 leave the wake arrays empty.
  for (int code : { 1, 2 }) {
    auto other = settings;
    other.wake_flag = code;
    require(initial(grid, other, forward, 268)->wakeDeficitU.empty(), "Wake arrays for code " + std::to_string(code));
  }

  // The rooftop vortex and the high-rise cavity change the cavity only.
  BuildingArrays towers{ {}, { 0 }, {}, {}, {} };
  append(towers, { 30, 30, 30, 50, 50, 50, 50, 30, 30, 30 }, 15);
  append(towers, { 90, 40, 90, 50, 100, 50, 100, 40, 90, 40 }, 40);
  const auto plain = initial(grid, settings, towers, 270);
  for (int variant = 0; variant < 2; variant++) {
    auto other = settings;
    (variant ? other.high_rise_flag : other.rooftop_flag) = variant ? 1 : 2;
    const auto changed = initial(grid, other, towers, 270);
    require(changed->wakeDeficitU == plain->wakeDeficitU && changed->wakeDeficitV == plain->wakeDeficitV,
            variant ? "High-rise model changed D" : "Rooftop vortex changed D");
    require(changed->wakeRoofSpeed2U == plain->wakeRoofSpeed2U, "Cavity model changed k_w");
  }

#ifdef _OPENMP
  const int threads = omp_get_max_threads();
  omp_set_num_threads(1);
  std::vector<float> us, vs;
  const auto serial = initial(grid, settings, forward, 268, &us, &vs);
  omp_set_num_threads(8);
  std::vector<float> ut, vt;
  const auto team = initial(grid, settings, forward, 268, &ut, &vt);
  omp_set_num_threads(threads);
  require(serial->wakeDeficitU == team->wakeDeficitU && serial->wakeDeficitV == team->wakeDeficitV
          && serial->wakeRoofSpeed2U == team->wakeRoofSpeed2U && us == ut && vs == vt,
          "Wake fields depend on the thread count");
#endif
}

int main()
{
  box_checks();
  integral_check();
  shadow_check();
  crossing_check();
  footprint_checks();
  point_field_check();
  pipeline_checks();
}
