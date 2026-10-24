#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#include "util/QESLog.h"
#include "util/QESout.h"
#include "fixture.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool condition, const char *message)
{
  if (!condition) throw std::runtime_error(message);
}

template<typename Error, typename Operation>
static void rejects(Operation operation)
{
  try { operation(); }
  catch (const Error &error) {
    require(*error.what() != '\0', "An exception must explain the failure");
    return;
  }
  throw std::runtime_error("Expected native exception was not thrown");
}

// Inputs and buildings are owned here; WINDSInputData and allBuildingsV borrow
// them. Fresh objects prevent QES's halo mutations from crossing preparations.
struct Inputs
{
  std::unique_ptr<SimulationParameters> simulation = std::make_unique<SimulationParameters>();
  std::unique_ptr<MetParams> met = std::make_unique<MetParams>();
  std::unique_ptr<BuildingsParams> buildings = std::make_unique<BuildingsParams>();
  std::unique_ptr<Sensor> sensor = std::make_unique<Sensor>();
  std::unique_ptr<TimeSeries> series = std::make_unique<TimeSeries>();
  std::unique_ptr<PolyBuilding> building;
  WINDSInputData input;

  explicit Inputs(bool with_building = false)
  {
    simulation->domain = {fixture::nx, fixture::ny, fixture::nz};
    simulation->grid = {fixture::cell_size, fixture::cell_size, fixture::cell_size};
    simulation->tolerance = fixture::tolerance;
    simulation->maxIterations = fixture::max_iterations;
    series->time = std::string(fixture::timestamp);
    series->site_z0 = fixture::roughness;
    series->site_z_ref = {fixture::reference_height};
    series->site_U_ref = {fixture::speed};
    series->site_wind_dir = {fixture::direction};
    sensor->site_xcoord = fixture::sensor_x;
    sensor->site_ycoord = fixture::sensor_y;
    sensor->TS = {series.get()};
    met->sensors = {sensor.get()};
    buildings->wallRoughness = fixture::wall_roughness;
    buildings->rooftopFlag = fixture::rooftop_flag;
    buildings->upwindCavityFlag = fixture::upwind_cavity_flag;
    buildings->streetCanyonFlag = fixture::street_canyon_flag;
    buildings->streetIntersectionFlag = fixture::street_intersection_flag;
    buildings->wakeFlag = fixture::wake_flag;
    buildings->highRiseFlag = fixture::high_rise_flag;
    buildings->sidewallFlag = fixture::sidewall_flag;
    if (with_building) {
      std::vector<polyVert> vertices;
      for (const auto &v : fixture::vertices) vertices.emplace_back(v[0], v[1]);
      building = std::make_unique<PolyBuilding>(vertices, fixture::height, fixture::base_height, 0);
      buildings->buildings = {building.get()};
    }
    input.simParams = simulation.get();
    input.metParams = met.get();
    input.buildingsParams = buildings.get();
  }

  std::unique_ptr<WINDSGeneralData> prepare()
  {
    return std::make_unique<WINDSGeneralData>(&input,
      qes::Domain(simulation->domain, simulation->grid), CPU_Type);
  }
};

static SolveDiagnostics solve(Inputs &inputs, WINDSGeneralData &data, int limit)
{
  data.resetICellFlag();
  data.applyWindProfile(&inputs.input, 0, CPU_Type);
  data.applyParametrizations(&inputs.input);
  std::unique_ptr<Solver> solver(SolverFactory::create(CPU_Type, data.domain, fixture::tolerance));
  solver->resetLambda();
  return solver->solve(&data, limit);
}

static void success()
{
  for (int repeat = 0; repeat < 20; ++repeat) {
    Inputs inputs;
    auto data = inputs.prepare();
    const auto result = solve(inputs, *data, fixture::max_iterations);
    require(result.converged && result.iterations > 0, "Flat case did not converge");
    require(result.max_lagrange_multiplier_change <= result.tolerance, "Invalid convergence metric");
    for (int k = 1; k <= fixture::nz; ++k) {
      const auto id = data->domain.face(10, 10, k);
      const double expected = fixture::speed
        * std::log((data->domain.z[k] + fixture::roughness) / fixture::roughness)
        / std::log((fixture::reference_height + fixture::roughness) / fixture::roughness);
      require(std::abs(data->u[id] - expected) < 1e-5, "Flat logarithmic profile differs");
      require(std::abs(data->v[id]) < 1e-5 && std::abs(data->w[id]) < 1e-5, "Flat transverse wind is non-zero");
    }
  }
  for (int repeat = 0; repeat < 3; ++repeat) {
    Inputs inputs(true);
    {
      auto data = inputs.prepare();
      require(data->allBuildingsV.at(0) == inputs.building.get(), "Building must be borrowed");
      const auto result = solve(inputs, *data, fixture::max_iterations);
      require(result.converged && result.iterations > 0, "Building case did not converge");
      for (const auto *field : {&data->u, &data->v, &data->w})
        for (float value : *field) require(std::isfinite(value), "Velocity is non-finite");
    }
    require(inputs.building->polygonVertices.size() == 5, "Wind data deleted caller geometry");
  }
}

static void failures()
{
  const float nan = std::numeric_limits<float>::quiet_NaN();
  rejects<qes::InputError>([] { qes::Domain d(0, 2, 3, 2, 2, 2); });
  rejects<qes::InputError>([] { qes::Domain d(100000, 100000, 100000, 2, 2, 2); });
  rejects<qes::InputError>([&] { qes::Domain d(4, 3, 2, nan, 2, 2); });
  rejects<qes::RuntimeError>([] { QESout::error("Deliberate native error"); });
  rejects<qes::UnsupportedFeature>([] { WINDSInputData input("missing.xml"); });
  for (int repeat = 0; repeat < 20; ++repeat) {
    Inputs inputs;
    inputs.met->sensors.clear();
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.met->sensors = {nullptr};
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.met->sensors = {inputs.sensor.get()};
    inputs.sensor->TS.clear();
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.sensor->TS = {inputs.series.get()};
    inputs.series->site_z_ref.clear();
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.series->site_z_ref = {fixture::reference_height};
    inputs.series->site_U_ref = {nan};
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.series->site_U_ref = {fixture::speed};
    inputs.sensor->site_xcoord = -1;
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.sensor->site_xcoord = fixture::sensor_x;
    auto data = inputs.prepare();
    rejects<qes::InputError>([&] { data->applyWindProfile(&inputs.input, -1, CPU_Type); });
    rejects<qes::InputError>([&] { std::unique_ptr<Solver> s(SolverFactory::create(99, data->domain, fixture::tolerance)); });
    rejects<qes::InputError>([&] { std::unique_ptr<Solver> s(SolverFactory::create(1, data->domain, 1e-12f)); });
    data->applyWindProfile(&inputs.input, 0, CPU_Type);
    std::unique_ptr<Solver> solver(SolverFactory::create(1, data->domain, fixture::tolerance));
    rejects<qes::InputError>([&] { solver->solve(data.get(), 0); });
    data->u0[0] = nan;
    rejects<qes::InputError>([&] { solver->solve(data.get(), 2); });
    data->applyWindProfile(&inputs.input, 0, CPU_Type);
    const auto cell = data->domain.cell(2, 2, 2);
    for (auto *values : {&data->e, &data->f, &data->g, &data->h, &data->m, &data->n})
      (*values)[cell] = 0.0f;
    rejects<qes::RuntimeError>([&] { solver->solve(data.get(), 2); });
  }
  // Failure after the wind profiler is allocated must also release it.
  Inputs bad_building(true);
  bad_building.building->polygonVertices.clear();
  rejects<qes::InputError>([&] { bad_building.prepare(); });
}

static void nonconvergence()
{
  Inputs inputs(true);
  auto data = inputs.prepare();
  const auto result = solve(inputs, *data, 1);
  require(!result.converged && result.iterations == 1, "Iteration-limit status is wrong");
  require(result.max_lagrange_multiplier_change > result.tolerance, "Non-convergence metric is wrong");
}

static void check_messages()
{
  using namespace qes::log;
  std::vector<Level> levels;
  {
    ScopedHandler handler([&](Level level, const std::string &message) {
      require(!message.empty(), "Empty diagnostic");
      levels.push_back(level);
    });
    debug() << "debug";
    info() << "info";
    QESout::warning("warning");
    error() << "error";
    require(levels == std::vector<Level>({Level::debug, Level::info, Level::warning, Level::error}),
      "Diagnostic levels were lost");
    rejects<qes::RuntimeError>([] { QESout::error("Exception, not a log record"); });
    require(levels.size() == 4, "Native error was reported twice");
    { ScopedHandler bad([](Level, const std::string &) { throw std::runtime_error("Bad callback"); });
      info() << "Callback exceptions must not escape destruction"; }
    info() << "Handler restored";
    require(levels.size() == 5, "Handler was not restored");
  }
  info() << "Default handler discards this";
}

int main(int argc, char **argv)
{
  try {
    const std::string mode = argc > 1 ? argv[1] : "all";
    if (mode == "all" || mode == "success") success();
    if (mode == "all" || mode == "failures") failures();
    if (mode == "all" || mode == "nonconvergence") nonconvergence();
    if (mode == "all" || mode == "messages") check_messages();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << std::endl;
    return 1;
  }
}
