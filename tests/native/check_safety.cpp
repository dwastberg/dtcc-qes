#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESLog.h"
#include "fixture.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace dtcc_qes::solver;

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

// Inputs are plain values; the wind model builds and owns its buildings.
struct Inputs
{
  std::vector<BuildingFootprint> buildings;
  BuildingParameterizations parameterizations;
  InflowCondition inflow;

  explicit Inputs(bool with_building = false)
  {
    inflow.site_z0 = fixture::roughness;
    inflow.site_z_ref = fixture::reference_height;
    inflow.site_U_ref = fixture::speed;
    inflow.site_wind_dir = fixture::direction;
    inflow.site_xcoord = fixture::sensor_x;
    inflow.site_ycoord = fixture::sensor_y;
    parameterizations.wallRoughness = fixture::wall_roughness;
    parameterizations.rooftopFlag = fixture::rooftop_flag;
    parameterizations.upwindCavityFlag = fixture::upwind_cavity_flag;
    parameterizations.streetCanyonFlag = fixture::street_canyon_flag;
    parameterizations.wakeFlag = fixture::wake_flag;
    parameterizations.highRiseFlag = fixture::high_rise_flag;
    parameterizations.sidewallFlag = fixture::sidewall_flag;
    if (with_building) {
      BuildingFootprint building;
      for (const auto &v : fixture::vertices) building.vertices.emplace_back(v[0], v[1]);
      building.height = fixture::height;
      building.base_height = fixture::base_height;
      buildings = {building};
    }
  }

  std::unique_ptr<WINDSGeneralData> prepare()
  {
    return std::make_unique<WINDSGeneralData>(
      qes::Domain(fixture::nx, fixture::ny, fixture::nz, fixture::cell_size, fixture::cell_size, fixture::cell_size),
      buildings, parameterizations, inflow.site_z0);
  }
};

static SolveDiagnostics solve(Inputs &inputs, WINDSGeneralData &data, int limit)
{
  data.resetICellFlag();
  data.applyWindProfile(inputs.inflow);
  data.applyParametrizations();
  const PoissonOperator op(data);
  SolverState<float> solver(op, fixture::tolerance);
  return solve_wind(solver, data, limit);
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
      require(data->allBuildingsV.size() == 1 && data->allBuildingsV.at(0)->polygonVertices.size() == 5,
              "The wind model must own one building per footprint");
      const auto result = solve(inputs, *data, fixture::max_iterations);
      require(result.converged && result.iterations > 0, "Building case did not converge");
      for (const auto *field : {&data->u, &data->v, &data->w})
        for (float value : *field) require(std::isfinite(value), "Velocity is non-finite");
    }
    require(inputs.buildings.at(0).vertices.size() == 5, "Wind data changed caller geometry");
  }
}

static void failures()
{
  for (int dependent = 0; dependent < 3; ++dependent) {
    Inputs inputs(true);
    inputs.parameterizations.wakeFlag = 0;
    inputs.parameterizations.rooftopFlag = dependent == 0;
    inputs.parameterizations.streetCanyonFlag = dependent == 1;
    inputs.parameterizations.sidewallFlag = dependent == 2;
    rejects<std::invalid_argument>([&] { inputs.prepare(); });
  }
  {
    Inputs inputs(true);
    auto data = inputs.prepare();
    data->parameterizations.wakeFlag = 0;
    rejects<std::invalid_argument>([&] { data->applyParametrizations(); });
  }
  const float nan = std::numeric_limits<float>::quiet_NaN();
  rejects<qes::InputError>([] { qes::Domain d(0, 2, 3, 2, 2, 2); });
  rejects<qes::InputError>([] { qes::Domain d(100000, 100000, 100000, 2, 2, 2); });
  rejects<qes::InputError>([&] { qes::Domain d(4, 3, 2, nan, 2, 2); });
  for (int repeat = 0; repeat < 20; ++repeat) {
    Inputs inputs;
    inputs.inflow.site_z0 = 0;
    rejects<qes::InputError>([&] { inputs.prepare(); });
    inputs.inflow.site_z0 = fixture::roughness;
    auto data = inputs.prepare();
    // The inflow is validated for every profile it produces.
    inputs.inflow.site_z_ref = 0;
    rejects<qes::InputError>([&] { data->applyWindProfile(inputs.inflow); });
    inputs.inflow.site_z_ref = fixture::reference_height;
    inputs.inflow.site_U_ref = nan;
    rejects<qes::InputError>([&] { data->applyWindProfile(inputs.inflow); });
    inputs.inflow.site_U_ref = -1;
    rejects<qes::InputError>([&] { data->applyWindProfile(inputs.inflow); });
    inputs.inflow.site_U_ref = fixture::speed;
    inputs.inflow.site_one_overL = nan;
    rejects<qes::InputError>([&] { data->applyWindProfile(inputs.inflow); });
    inputs.inflow.site_one_overL = 0;
    inputs.inflow.site_xcoord = -1;
    rejects<qes::InputError>([&] { data->applyWindProfile(inputs.inflow); });
    inputs.inflow.site_xcoord = fixture::sensor_x;
    data->applyWindProfile(inputs.inflow);
    {
      const PoissonOperator op(*data);
      rejects<qes::InputError>([&] { SolverState<float> s(op,fixture::tolerance,static_cast<SweepOrder>(99)); });
      rejects<qes::InputError>([&] { SolverState<float> s(op,1e-12f); });
      SolverState<float> solver(op,fixture::tolerance);
      rejects<qes::InputError>([&] { solve_wind(solver,*data,0); });
      data->u0[0] = nan;
      rejects<qes::InputError>([&] { solve_wind(solver,*data,2); });
    }
    data->applyWindProfile(inputs.inflow);
    const auto cell = data->domain.cell(2,2,2);
    for (auto *values : {&data->e,&data->f,&data->g,&data->h,&data->m,&data->n}) (*values)[cell] = 0.0f;
    const PoissonOperator invalid_diagonal(*data);
    SolverState<float> bad(invalid_diagonal,fixture::tolerance);
    rejects<qes::RuntimeError>([&] { solve_wind(bad,*data,2); });
  }
  // Failure after the arrays are allocated must also release the partial model.
  Inputs bad_building(true);
  bad_building.buildings.at(0).vertices.clear();
  rejects<qes::InputError>([&] { bad_building.prepare(); });
}

static void nonconvergence()
{
  Inputs inputs(true);
  auto data = inputs.prepare();
  const auto result = solve(inputs, *data, 1);
  require(!result.converged && result.iterations == 1, "Iteration-limit status is wrong");
  require(result.max_lagrange_multiplier_change > result.tolerance, "Non-convergence metric is wrong");
  // A permissive tolerance must not report the unmeasured initial sentinel.
  const PoissonOperator op(*data);
  SolverState<float> loose(op,2.0f);
  const auto measured = solve_wind(loose,*data,fixture::max_iterations);
  require(measured.iterations > 0, "Convergence must be measured at least once");
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
    warning() << "warning";
    error() << "error";
    require(levels == std::vector<Level>({Level::debug, Level::info, Level::warning, Level::error}),
      "Diagnostic levels were lost");
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
