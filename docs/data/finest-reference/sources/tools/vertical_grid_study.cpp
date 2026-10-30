// Synthetic sensitivity/cost study, not an experimental validation or public API.
#include "qes_inputs.h"
#include "divergence.h"
#include "precision_solver.h"
#include "log_sink.h"
#include "winds/WINDSGeneralData.h"
#include "winds/Solver_CPU.h"
#include "winds/SolverFactory.h"
#include "vertical_grid_diagnostics.h"
#ifdef _OPENMP
#include "winds/Solver_CPU_RB.h"
#include <omp.h>
#endif
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <sys/resource.h>

using namespace dtcc_qes;
using Clock = std::chrono::steady_clock;
using Vector = std::array<double, 3>;
#ifdef _OPENMP
using Backend = Solver_CPU_RB;
constexpr const char *backend = "openmp_red_black";
#else
using Backend = Solver_CPU;
constexpr const char *backend = "serial_lexicographic";
#endif

// Negative tolerance is ONLY a study control: force all requested sweeps even
// after float32 stagnation. Public constructors/stopping rules are unchanged.
class FixedSweeps : public Backend {
public:
  explicit FixedSweeps(const qes::Domain &d)
    : Backend(d, std::numeric_limits<float>::epsilon()) { tol = -1; }
  const auto &multipliers() const { return lambda; }
  const auto &previous_multipliers() const { return lambda_old; }
  const auto &rhs() const { return R; }
};

static void rectangle(BuildingArrays &b, double x, double y, double w, double l, double h)
{
  b.vertices.insert(b.vertices.end(), {x,y, x,y+l, x+w,y+l, x+w,y, x,y});
  b.offsets.push_back(b.vertices.size() / 2);
  b.ids.push_back(b.ids.size()); b.heights.push_back(h); b.base_heights.push_back(0);
}

static BuildingArrays geometry(const std::string &name)
{
  BuildingArrays b{{}, {0}, {}, {}, {}};
  if (name == "isolated") rectangle(b, 32, 32, 12, 16, 12);
  else if (name == "passage") {
    rectangle(b, 24, 24, 12, 32, 12);
    rectangle(b, 44, 24, 12, 32, 12); // 8 m / four-cell passage.
  } else if (name == "array" || name == "tower") {
    for (double y : {22., 42.}) for (double x : {22., 42.})
      rectangle(b, x, y, 12, 12, name == "tower" && x == 42 && y == 42 ? 24 : 8);
  } else throw std::invalid_argument("Unknown geometry");
  return b;
}

static std::vector<double> layers(const std::string &name)
{
  if (name != "stretched") {
    const double h = std::stod(name);
    if (h != 2 && h != 1 && h != 0.5 && h != 0.25)
      throw std::invalid_argument("Spacing must be 2, 1, 0.5, 0.25 or stretched");
    return std::vector<double>(static_cast<int>(64 / h), h);
  }
  // One hand-built, exactly representable 64 m grid. No automatic policy:
  // 0.5 m through 4 m, gradual transitions, 1 m in the building region,
  // then at most 2 m aloft. Adjacent growth <= 1.125; final cells fit the top.
  std::vector<double> h(8, 0.5);
  for (int i = 9; i <= 16; ++i) h.push_back(i / 16.0);
  h.insert(h.end(), 14, 1);
  for (int i = 9; i <= 16; ++i) h.push_back(i / 8.0);
  h.insert(h.end(), 12, 2);
  h.insert(h.end(), 2, 1.625);
  return h;
}

struct Plane {
  std::vector<Vector> velocity;
  std::vector<bool> valid;
  std::vector<std::array<int, 2>> flags;
};

// Same centring/operand precision as WindRunner, then linear interpolation of
// components, not speed. Only physical centres; zero-weight neighbours ignored.
static Plane sample(const WINDSGeneralData &data, double height, bool initial = false,
                    std::vector<int> ii = {}, std::vector<int> jj = {})
{
  const auto &d = data.domain;
  if (!std::isfinite(height) || height < 0 || height > d.z_face.back())
    throw std::invalid_argument("Sample height must be finite and inside the physical domain");
  const auto end = d.z.end();
  const auto upper = std::lower_bound(d.z.begin() + 1, end, height);
  int lo = -1, hi = -1;
  double weight = 0;
  if (upper != end && *upper == height) lo = hi = upper - d.z.begin();
  else if (upper != d.z.begin() + 1 && upper != end) {
    hi = upper - d.z.begin(); lo = hi - 1;
    weight = (height - d.z[lo]) / (d.z[hi] - d.z[lo]);
  }
  Plane p;
  const auto &u_faces = initial ? data.u0 : data.u;
  const auto &v_faces = initial ? data.v0 : data.v;
  const auto &w_faces = initial ? data.w0 : data.w;
  if (ii.empty()) for (int i = 1; i < d.nx() - 2; ++i) ii.push_back(i);
  if (jj.empty()) for (int j = 1; j < d.ny() - 2; ++j) jj.push_back(j);
  // Fixed common x/y points: all non-prescribed horizontal cell centres.
  for (int j : jj) for (int i : ii) {
    bool valid = lo >= 1;
    p.flags.push_back(lo >= 1 ? std::array<int, 2>{data.icellflag[d.cell(i,j,lo)], data.icellflag[d.cell(i,j,hi)]}
                              : std::array<int, 2>{-1, -1});
    if (valid) for (int k : {lo, hi}) {
      const int flag = data.icellflag[d.cell(i,j,k)];
      valid = valid && flag != 0 && flag != 2;
    }
    Vector v{};
    if (valid) {
      auto centred = [&](int k) -> Vector {
        const auto f = d.face(i,j,k);
        return {0.5f * (u_faces[f+1] + u_faces[f]),
                0.5f * (v_faces[f+d.nx()] + v_faces[f]),
                0.5f * (w_faces[f+d.nx()*d.ny()] + w_faces[f])};
      };
      const auto a = centred(lo), b = centred(hi);
      for (int c = 0; c < 3; ++c) {
        v[c] = a[c] + weight * (b[c] - a[c]);
        if (!std::isfinite(v[c])) throw std::runtime_error("Nonfinite sample");
      }
    }
    p.velocity.push_back(v); p.valid.push_back(valid);
  }
  return p;
}

static double elapsed(Clock::time_point start)
{ return std::chrono::duration<double>(Clock::now() - start).count(); }

// Study-only stdin protocol: resolution, layer/height/rectangle counts, then
// thicknesses, sampling heights and (x,y,width,length,height) rectangles. Python
// owns grid generation. Keep the original positional interface/archive intact.
static void read_configuration(GridConfig &grid, BuildingArrays &buildings,
                               std::vector<double> &heights)
{
  int nz = 0, nh = 0, nb = 0;
  if (!(std::cin >> grid.cell_size >> nz >> nh >> nb)
      || (grid.cell_size != 1 && grid.cell_size != 2)
      || nz < 2 || nz > 10000 || nh < 1 || nh > 10 || nb < 1 || nb > 100)
    throw std::invalid_argument("Invalid study configuration header");
  grid.nx = grid.ny = static_cast<int>(80 / grid.cell_size);
  grid.nz = nz;
  grid.dz_layers.resize(nz);
  heights.resize(nh);
  for (auto &h : grid.dz_layers)
    if (!(std::cin >> h) || !std::isfinite(h) || h <= 0)
      throw std::invalid_argument("Invalid study layer");
  for (auto &h : heights)
    if (!(std::cin >> h) || !std::isfinite(h) || h < 0)
      throw std::invalid_argument("Invalid study sampling height");
  buildings = BuildingArrays{{}, {0}, {}, {}, {}};
  for (int i = 0; i < nb; ++i) {
    double x, y, w, l, h;
    if (!(std::cin >> x >> y >> w >> l >> h)
        || !std::isfinite(x) || !std::isfinite(y) || !std::isfinite(w)
        || !std::isfinite(l) || !std::isfinite(h) || w <= 0 || l <= 0 || h <= 0)
      throw std::invalid_argument("Invalid study rectangle");
    rectangle(buildings, x, y, w, l, h);
  }
  std::string extra;
  if (std::cin >> extra) throw std::invalid_argument("Unexpected study configuration data");
}

static void write_plane(std::ostream &out, const Plane &p)
{
  out << '[';
  for (std::size_t i = 0; i < p.valid.size(); ++i) {
    if (i) out << ',';
    if (!p.valid[i]) out << "null";
    else out << '[' << p.velocity[i][0] << ',' << p.velocity[i][1] << ',' << p.velocity[i][2] << ']';
  }
  out << ']';
}

struct HorizontalControl {
  double ox = 0, oy = 0, lx = 80, ly = 80;
  int disabled = 0;
};

static HorizontalControl read_horizontal(GridConfig &grid, BuildingArrays &buildings,
                                         std::vector<double> &heights)
{
  HorizontalControl control;
  int nz = 0, nh = 0, nb = 0;
  if (!(std::cin >> grid.cell_size >> control.ox >> control.oy >> control.lx >> control.ly
        >> nz >> nh >> nb >> control.disabled)
      || (grid.cell_size != .25 && grid.cell_size != .5 && grid.cell_size != 1 && grid.cell_size != 2)
      || !std::isfinite(control.ox) || !std::isfinite(control.oy)
      || !std::isfinite(control.lx) || !std::isfinite(control.ly)
      || control.lx <= 0 || control.ly <= 0 || control.lx > 320 || control.ly > 320
      || nz < 2 || nz > 10000 || nh < 1 || nh > 10 || nb < 1 || nb > 100
      || control.disabled < 0 || control.disabled > 31)
    throw std::invalid_argument("Invalid horizontal-control header");
  if (std::floor(control.lx/grid.cell_size) != control.lx/grid.cell_size
      || std::floor(control.ly/grid.cell_size) != control.ly/grid.cell_size)
    throw std::invalid_argument("Horizontal extents must contain whole cells");
  grid.nx = static_cast<int>(control.lx/grid.cell_size);
  grid.ny = static_cast<int>(control.ly/grid.cell_size);
  grid.nz = nz; grid.max_cells = 20000000;
  grid.dz_layers.resize(nz); heights.resize(nh);
  for (auto &h : grid.dz_layers)
    if (!(std::cin >> h) || !std::isfinite(h) || h <= 0) throw std::invalid_argument("Invalid horizontal layer");
  const auto faces = vertical_faces(grid);
  for (auto &h : heights)
    if (!(std::cin >> h) || !std::isfinite(h) || h < 0 || h > faces.back())
      throw std::invalid_argument("Invalid horizontal sampling height");
  buildings = BuildingArrays{{}, {0}, {}, {}, {}};
  for (int i = 0; i < nb; ++i) {
    double x, y, w, l, h;
    if (!(std::cin >> x >> y >> w >> l >> h) || !std::isfinite(x) || !std::isfinite(y)
        || !std::isfinite(w) || !std::isfinite(l) || !std::isfinite(h) || w <= 0 || l <= 0 || h <= 0)
      throw std::invalid_argument("Invalid horizontal rectangle");
    rectangle(buildings, x-control.ox, y-control.oy, w, l, h);
  }
  std::string extra;
  if (std::cin >> extra) throw std::invalid_argument("Unexpected horizontal configuration data");
  return control;
}

// Archive only native centres supporting the fixed 3,5,...,77 m lattice.
// This retains every interpolation corner without full fine-grid plane dumps.
static std::vector<int> support_indices(const std::vector<float> &axis, double origin)
{
  std::vector<int> indices;
  for (double point = 3; point <= 77; point += 2) {
    auto hi = std::lower_bound(axis.begin()+1, axis.end()-1, point-origin);
    if (hi == axis.end()-1 || (hi == axis.begin()+1 && *hi != point-origin))
      throw std::invalid_argument("Comparison points outside non-prescribed native centres");
    const int index = static_cast<int>(hi-axis.begin());
    if (*hi != point-origin) indices.push_back(index-1);
    indices.push_back(index);
  }
  std::sort(indices.begin(), indices.end());
  indices.erase(std::unique(indices.begin(), indices.end()), indices.end());
  return indices;
}

static void write_planes(std::ostream &out, const WINDSGeneralData &data,
                         const std::vector<double> &heights, const std::vector<int> &ii,
                         const std::vector<int> &jj, bool initial)
{
  out << '[';
  for (std::size_t n = 0; n < heights.size(); ++n) {
    const auto p = sample(data, heights[n], initial, ii, jj);
    out << (n ? "," : "") << "{\"height\":" << heights[n] << ",\"velocity\":";
    write_plane(out, p);
    out << ",\"flags\":[";
    for (std::size_t i = 0; i < p.flags.size(); ++i)
      out << (i ? "," : "") << '[' << p.flags[i][0] << ',' << p.flags[i][1] << ']';
    out << "]}";
  }
  out << ']';
}

static void sampler_self_test()
{
  GridConfig grid;
  grid.nx = grid.ny = 8;
  grid.dz_layers = {0.5, 0.75, 1, 2, 3}; grid.nz = grid.dz_layers.size();
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  QESInputs inputs(grid, model, BuildingArrays{{}, {0}, {}, {}, {}});
  WINDSGeneralData data(&inputs.input, make_domain(inputs), CPU_Type);
  const auto &d = data.domain;
  std::fill(data.icellflag.begin(), data.icellflag.end(), 1);
  // A manufactured affine vector field must survive staggering and vertical
  // interpolation exactly. This also tests the w face/centre distinction.
  for (int k = 1; k <= grid.nz + 1; ++k)
    for (int j = 0; j < d.ny(); ++j) for (int i = 0; i < d.nx(); ++i) {
      const auto f = d.face(i,j,k);
      data.w[f] = 3 - 0.5f * d.z_face[k];
      if (k <= grid.nz) {
        data.u[f] = 2 + d.z[k]; data.v[f] = -1 + 2 * d.z[k];
      }
    }
  auto require = [](bool ok) { if (!ok) throw std::runtime_error("Study sampler self-test failed"); };
  auto p = sample(data, 1.5);
  require(p.valid.size() == 36);
  for (std::size_t i = 0; i < p.valid.size(); ++i) {
    require(p.valid[i]);
    for (int c = 0; c < 3; ++c)
      require(std::abs(p.velocity[i][c] - Vector{3.5, 2, 2.25}[c]) < 1e-12);
  }
  require(sample(data, d.z.back()).valid[0]);
  data.icellflag[d.cell(1,1,2)] = 0;
  require(sample(data, d.z[1]).valid[0]); // Zero-weight solid neighbour ignored.
  require(!sample(data, 0.5).valid[0]);
  data.icellflag[d.cell(1,1,2)] = 2;
  require(!sample(data, 0.5).valid[0]);
  require(!sample(data, 0).valid[0]);
  require(!sample(data, d.z_face.back()).valid[0]);
  for (double height : {-1., std::numeric_limits<double>::quiet_NaN(), 100.}) {
    bool rejected = false;
    try { sample(data, height); } catch (const std::invalid_argument &) { rejected = true; }
    require(rejected);
  }
}

int main(int argc, char **argv)
try {
  if (argc == 2 && std::string(argv[1]) == "--self-test") {
    const std::lock_guard<std::mutex> lock(native_mutex());
    Messages messages;
    const BufferedLogSink sink(messages);
    sampler_self_test();
    return 0;
  }
  if (argc == 2 && std::string(argv[1]) == "--diagnostics-self-test") {
    const std::lock_guard<std::mutex> lock(native_mutex());
    Messages messages;
    const BufferedLogSink sink(messages);
    study::diagnostics_self_test();
    return 0;
  }
  bool diagnose = false, double_precision = false, single_checkpoint = false;
  std::int64_t allocation_ceiling = 0;
  for (int arg = 5; arg < argc; ++arg) {
    const std::string flag = argv[arg];
    if (flag == "--diagnose") diagnose = true;
    else if (flag == "--float64") double_precision = true;
    else if (flag == "--checkpoint") single_checkpoint = true;
    else if (flag == "--max-cells" && arg + 1 < argc) {
      const std::string value = argv[++arg];
      std::size_t consumed = 0;
      allocation_ceiling = std::stoll(value, &consumed);
      if (consumed != value.size() || allocation_ceiling < 1)
        throw std::invalid_argument("Allocation ceiling must be a positive integer");
    }
    else throw std::invalid_argument("Unknown study option");
  }
  if (argc < 5 || (diagnose && double_precision))
    throw std::invalid_argument("Usage: vertical_grid_study geometry spacing direction N [--diagnose | --float64] [--checkpoint] [--max-cells COUNT]");
  const std::string name = argv[1], spacing = argv[2];
  const double direction = std::stod(argv[3]);
  const int n = std::stoi(argv[4]);
  const bool horizontal = spacing == "--horizontal";
  if (single_checkpoint && (!horizontal || !double_precision || diagnose || n < 1))
    throw std::invalid_argument("Single checkpoints require horizontal float64 fixed sweeps with positive N");
  if (n < (horizontal ? 0 : 1) || n > 100000) throw std::invalid_argument("N outside study range");
#ifdef _OPENMP
  omp_set_dynamic(0); omp_set_num_threads(2);
#endif
  const std::lock_guard<std::mutex> lock(native_mutex());
  Messages messages;
  const BufferedLogSink sink(messages);
  const auto start = Clock::now();
  GridConfig grid;
  grid.nx = grid.ny = 40;
  BuildingArrays b;
  HorizontalControl control;
  std::vector<double> heights{1.5};
  if (horizontal) control = read_horizontal(grid, b, heights);
  else if (spacing == "--layers") read_configuration(grid, b, heights);
  else {
    grid.dz_layers = layers(spacing); grid.nz = grid.dz_layers.size();
    b = geometry(name);
  }
  if (allocation_ceiling) grid.max_cells = allocation_ceiling;
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  if (horizontal) {
    model.sensor_x -= control.ox; model.sensor_y -= control.oy;
    if (control.disabled & 1) model.rooftop_flag = 0;
    if (control.disabled & 2) model.upwind_cavity_flag = 0;
    if (control.disabled & 4) model.street_canyon_flag = 0;
    if (control.disabled & 8) model.wake_flag = 0;
    if (control.disabled & 16) model.sidewall_flag = 0;
  }
  QESInputs inputs(grid, model, b);
  inputs.set_condition({5, direction, 10});
  WINDSGeneralData data(&inputs.input, make_domain(inputs), CPU_Type);
  data.applyWindProfile(&inputs.input, 0, CPU_Type);
  std::vector<int> ii, jj;
  std::ostringstream profile;
  if (horizontal) {
    ii = support_indices(data.domain.x, control.ox); jj = support_indices(data.domain.y, control.oy);
    profile << std::setprecision(10);
    write_planes(profile, data, heights, ii, jj, true);
  }
  data.applyParametrizations(&inputs.input);
  std::unique_ptr<FixedSweeps> solver;
  std::unique_ptr<PrecisionSolver> precision_solver;
  if (n) {
    if (double_precision) precision_solver = std::make_unique<PrecisionSolver>(data.domain, 1e-12);
    else solver = std::make_unique<FixedSweeps>(data.domain);
  }
  const double prep = elapsed(start);
  const double hmax = *std::max_element(b.heights.begin(), b.heights.end());
  std::ostringstream out;
  out << std::setprecision(10) << "{\"geometry\":\"" << name << "\",\"grid\":\"" << spacing
      << "\",\"direction\":" << direction << ",\"backend\":\"" << backend
      << "\",\"threads\":"
#ifdef _OPENMP
      << 2
#else
      << 1
#endif
      << ",\"compiler\":\"" << __VERSION__ << "\",\"layers\":" << grid.nz
      << ",\"cells\":" << std::int64_t(grid.nx) * grid.ny * grid.nz << ",\"hmax\":" << hmax
      << ",\"prep_seconds\":" << prep << ",\"resolution\":" << grid.cell_size
      << ",\"precision\":\"" << (double_precision ? "float64" : "float32")
      << "\",\"start\":\"zero\",\"solver_workspace_bytes\":"
      << (precision_solver ? precision_solver->workspace_bytes()
                          : n ? 3*sizeof(float)*data.domain.numCellCentered() : 0)
      << ",\"sample_x\":[";
  if (ii.empty()) for (int i = 1; i < data.domain.nx() - 2; ++i) ii.push_back(i);
  if (jj.empty()) for (int j = 1; j < data.domain.ny() - 2; ++j) jj.push_back(j);
  for (std::size_t i = 0; i < ii.size(); ++i)
    out << (i ? "," : "") << data.domain.x[ii[i]]+control.ox;
  out << "],\"sample_y\":[";
  for (std::size_t j = 0; j < jj.size(); ++j)
    out << (j ? "," : "") << data.domain.y[jj[j]]+control.oy;
  out << "],\"z_faces\":[";
  for (int k = 1; k < data.domain.z_face.size(); ++k)
    out << (k > 1 ? "," : "") << data.domain.z_face[k];
  out << "],\"roof_errors\":[";
  for (std::size_t i = 0; i < b.heights.size(); ++i) {
    int k = 1;
    while (k <= grid.nz && data.domain.z[k] <= b.heights[i]) ++k;
    out << (i ? "," : "") << data.domain.z_face[k] - b.heights[i];
  }
  out << ']';
  if (horizontal) {
    out << ",\"horizontal_bounds\":[" << control.ox << ',' << control.oy << ','
        << control.ox+control.lx << ',' << control.oy+control.ly << "],\"disabled_mask\":" << control.disabled
        << ",\"profile_planes\":" << profile.str() << ",\"initial_planes\":";
    write_planes(out, data, heights, ii, jj, true);
  }
  out << ",\"checkpoints\":[";
  if (n)
  for (int multiplier : single_checkpoint ? std::vector<int>{1} : std::vector<int>{1, 2, 4}) {
    auto t = Clock::now();
    PrecisionDiagnostics diag;
    if (precision_solver) diag = precision_solver->solve(&data, n * multiplier, true);
    else {
      solver->resetLambda(); // Every checkpoint restarts from the same initial field.
      const auto legacy = static_cast<Solver &>(*solver).solve(&data, n * multiplier);
      diag = {legacy.iterations, legacy.max_lagrange_multiplier_change, legacy.tolerance, legacy.converged};
    }
    const double solve_seconds = elapsed(t);
    if (diag.iterations != n * multiplier) throw std::runtime_error("Incomplete sweep budget");
    t = Clock::now();
    const auto residual = divergence_stats(data);
    const double residual_seconds = elapsed(t);
    if (!residual.cells) throw std::runtime_error("No assessed interior cells");
    t = Clock::now();
    std::vector<Plane> planes;
    for (double height : heights) planes.push_back(sample(data, height, false, ii, jj));
    const double sampling_seconds = elapsed(t);
    out << (multiplier > 1 ? "," : "") << "{\"iterations\":" << diag.iterations
        << ",\"solve_seconds\":" << solve_seconds << ",\"sampling_seconds\":" << sampling_seconds
        << ",\"residual_seconds\":" << residual_seconds
        << ",\"max_multiplier_change\":" << diag.max_lagrange_multiplier_change
        << ",\"max_divergence\":" << residual.interior_max
        << ",\"rms_divergence\":" << residual.interior_rms
        << ",\"top_band_max_divergence\":" << residual.top_band_max
        << ",\"assessed_cells\":" << residual.cells << ",\"top_band_cells\":" << residual.top_band_cells
        << ",\"velocity\":";
    write_plane(out, planes.front());
    out << ",\"planes\":[";
    for (std::size_t i = 0; i < heights.size(); ++i) {
      out << (i ? "," : "") << "{\"height\":" << heights[i] << ",\"velocity\":";
      write_plane(out, planes[i]);
      if (horizontal) {
        out << ",\"flags\":[";
        for (std::size_t q = 0; q < planes[i].flags.size(); ++q)
          out << (q ? "," : "") << '[' << planes[i].flags[q][0] << ',' << planes[i].flags[q][1] << ']';
        out << ']';
      }
      out << '}';
    }
    out << ']';
    if (diagnose) {
      out << ",\"solver_diagnostics\":";
      study::write_solver_diagnostics(out, data, solver->multipliers(),
                                      solver->previous_multipliers(), solver->rhs());
      if (multiplier == 4) {
        out << ",\"precision_probe\":";
        study::write_precision_probe(out, data, solver->multipliers());
      }
    }
    out << '}';
  }
  struct rusage usage{};
  if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("getrusage failed");
  out << "],\"peak_rss_bytes\":" << usage.ru_maxrss
#ifndef __APPLE__
      * 1024L
#endif
      << ",\"message_count\":" << messages.size() << '}';
  std::cout << out.str() << '\n';
  return 0;
} catch (const std::exception &error) {
  std::cerr << error.what() << '\n'; return 1;
}
