#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "model_inputs.h"
#include "divergence.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <iostream>
#ifdef _OPENMP
#include <omp.h>
#endif

using namespace dtcc_qes;

using namespace dtcc_qes::solver;

static void require(bool value, const char *message)
{
  if (!value) throw std::runtime_error(message);
}

template<typename Error = qes::InputError, typename Operation>
static void rejects(Operation operation)
{
  try { operation(); } catch (const Error &) { return; }
  throw std::runtime_error("Invalid vertical grid was accepted");
}

static void domain_checks()
{
  const std::vector<float> layers{0.5f, 0.75f, 1, 2};
  qes::Domain d(8, 7, 2, 3, layers);
  require(d.getDomainSize() == std::make_tuple(2.0f, 3.0f, 0.5f), "Domain spacing contract is wrong");
  require(d.z_face == std::vector<float>({-0.5f, 0, 0.5f, 1.25f, 2.25f, 4.25f}), "Stretched faces are wrong");
  require(d.z == std::vector<float>({-0.25f, 0.25f, 0.875f, 1.75f, 3.25f}), "Stretched centres are wrong");
  require(d.dz_array.front() == d.dz_array[1] && !d.verticallyUniform(), "Ghost or uniformity contract is wrong");
  qes::Domain old(8, 7, 4, 2, 2, 2), equal(8, 7, 2, 2, std::vector<float>(4, 2));
  require(old.z == equal.z && old.z_face == equal.z_face && old.dz_array == equal.dz_array,
          "Equal explicit layers changed uniform coordinates");
  for (const auto &invalid : std::vector<std::vector<float>>{{}, {1}, {0, 1}, {-1, 1},
       {1, std::numeric_limits<float>::quiet_NaN()}, {1, std::numeric_limits<float>::infinity()},
       {1e8f, 1, 1}, {1e-30f, 1e-30f}, {1e30f, 1e30f}})
    rejects([&] { qes::Domain bad(8, 7, 2, 2, invalid); });
  rejects([&] { qes::Domain bad(8, 7, 2, 2, std::vector<float>(10001, 1)); });
}

static void guard_checks()
{
  GridConfig g;
  g.nx = g.ny = 8; g.nz = 4; g.dz_layers = {0.5, 0.75, 1, 2};
  ModelSettings model;
  model.sensor_x = model.sensor_y = 1;
  ModelInputs inputs(g, model, BuildingArrays{{}, {0}, {}, {}, {}});
  const auto d = make_domain(inputs);
  require(vertical_faces(g) == std::vector<float>(d.z_face.begin() + 1, d.z_face.end()),
          "Preparation and Domain coordinates disagree");
  // The Domain is the only description of the layers the core receives; the
  // bridge's float32 copy must match it, and explicit layers must select the
  // nonuniform turbulence derivatives even when the thicknesses are equal.
  require(inputs.layers.size() == static_cast<std::size_t>(d.nz() - 2)
            && std::equal(inputs.layers.begin(), inputs.layers.end(), d.dz_array.begin() + 1),
          "Bridge layers and Domain disagree");
  require(inputs.turbulence.verticalStretching == 1, "Explicit layers must select stretched derivatives");
  auto data = std::make_unique<WINDSGeneralData>(d, inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data->applyWindProfile(inputs.inflow);
  data->applyParametrizations();
  WINDSGeneralData wrong_geometry(qes::Domain(8,8,4,2,2,2));
  const PoissonOperator wrong_operator(wrong_geometry);
  SolverState<float> wrong(wrong_operator);
  rejects([&] { solve_wind(wrong,*data,1); });
  g.dz_layers = {1, 2};
  rejects<std::invalid_argument>([&] { ModelInputs bad(g, model, BuildingArrays{{}, {0}, {}, {}, {}}); });
}

static std::vector<float> injection(const std::vector<double> &layers, bool serial)
{
  GridConfig g;
  g.nx = g.ny = 24; g.nz = static_cast<int>(layers.size()); g.dz_layers = layers;
  ModelSettings model;
  model.sensor_x = model.sensor_y = 5;
  ModelInputs inputs(g, model, BuildingArrays{{}, {0}, {}, {}, {}});
  inputs.set_condition({0, 270, 10});
  WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  data.w0[data.domain.face(12, 12, 6)] = 0.1f;
  const PoissonOperator op(data);
  SolverState<float> solver(op, 2e-7f, serial ? SweepOrder::Lexicographic : default_order());
  solve_wind(solver, data, 20000);
  require(divergence_stats(data, op).interior_max < 1e-6, "Explicit grid failed the vertical injection bound");
  return data.w;
}

static void building_checks()
{
  GridConfig g;
  g.nx = g.ny = 24;
  g.dz_layers = {0.5, 0.5, 1, 2, 2, 2, 2}; // Top 10 m: shell may extend above the domain.
  g.nz = static_cast<int>(g.dz_layers.size());
  ModelSettings model;
  model.sensor_x = model.sensor_y = 1;
  model.rooftop_flag = 2; // Exercise the vortex branch's bounded shell search.
  for (double height : {7.99, 8.0, 8.25, 8.5}) {
    BuildingArrays b{{16,16, 16,30, 30,30, 30,16, 16,16}, {0,5}, {0}, {height}, {0}};
    ModelInputs inputs(g, model, b);
    for (double direction : {0.0, 45.0, 90.0, 270.0}) {
      inputs.set_condition({5, direction, 10});
      WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
      data.applyWindProfile(inputs.inflow);
      data.applyParametrizations();
      const auto &d = data.domain;
      for (int k = 1; k <= g.nz; ++k) {
        const bool expected = d.z[k] <= static_cast<float>(height);
        require((data.icellflag[d.cell(10, 10, k)] == 0) == expected,
                "Building occupancy does not follow actual vertical centres");
      }
      for (const auto *field : {&data.u0, &data.v0, &data.w0})
        require(std::all_of(field->begin(), field->end(), [](float v) { return std::isfinite(v); }),
                "Building parameterization produced nonfinite values on stretched layers");
    }
  }
}

static void stretched_canyon(bool report)
{
  GridConfig g;
  g.nx = 60; g.ny = 40;
  g.dz_layers.insert(g.dz_layers.end(), 8, 0.5);
  g.dz_layers.insert(g.dz_layers.end(), 12, 1.0);
  g.dz_layers.insert(g.dz_layers.end(), 17, 2.0);
  g.nz = static_cast<int>(g.dz_layers.size());
  BuildingArrays b{{}, {0}, {}, {}, {}};
  for (const auto x : {30.0, 52.0}) {
    b.vertices.insert(b.vertices.end(), {x,20, x,60, x+10,60, x+10,20, x,20});
    b.offsets.push_back(b.vertices.size() / 2);
    b.ids.push_back(b.ids.size()); b.heights.push_back(15); b.base_heights.push_back(0);
  }
  ModelSettings model;
  model.sensor_x = model.sensor_y = 5;
  ModelInputs inputs(g, model, b);
  inputs.set_condition({5, 270, 10});
  WINDSGeneralData data(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  const PoissonOperator op(data);
  SolverState<float> solver(op, std::numeric_limits<float>::epsilon());
  const auto diagnostics = solve_wind(solver, data, 2000);
  const auto stats = divergence_stats(data, op);
  require(stats.interior_max * 3 < 1e-3 && stats.interior_rms * 3 < 1e-4,
          "Stretched canyon fails the conservative residual bounds");
  if (report)
    std::cout << "stretched_canyon layers=" << g.nz << " max=" << stats.interior_max
              << " rms=" << stats.interior_rms << " top=" << stats.top_band_max
              << " iterations=" << diagnostics.iterations << "\n";
}

int main(int argc, char **)
{
  domain_checks();
  guard_checks();
  building_checks();
  std::vector<double> layers{0.5, 0.5, 0.5, 0.5, 0.6, 0.7, 0.8, 0.95,
                            1.1, 1.25, 1.45, 1.65, 1.9, 2.2, 2.5, 2.9};
  const auto serial = injection(layers, true);
#ifdef _OPENMP
  std::vector<float> baseline;
  for (int threads : {1, 2, 4}) {
    omp_set_dynamic(0);
    omp_set_num_threads(threads);
    const auto current = injection(layers, false);
    if (baseline.empty()) baseline = current;
    require(current == baseline, "Stretched velocities depend on thread count");
    for (std::size_t i = 0; i < current.size(); ++i)
      require(std::abs(current[i] - serial[i]) < 2e-5, "Stretched backends disagree");
  }
#endif
  stretched_canyon(argc > 1);
}
