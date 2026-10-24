#include "wind_runner.h"
#include "util/QESLog.h"
#include "fixture.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <thread>

using namespace dtcc_qes;

static void require(bool condition, const char *message)
{
  if (!condition) throw std::runtime_error(message);
}

template<typename Error, typename Operation>
static void rejects(Operation operation)
{
  try { operation(); }
  catch (const Error &) { return; }
  throw std::runtime_error("Expected runner exception was not thrown");
}

static BuildingArrays building()
{
  BuildingArrays arrays;
  for (const auto &vertex : fixture::vertices)
    arrays.vertices.insert(arrays.vertices.end(), {vertex[0], vertex[1]});
  arrays.offsets = {0, static_cast<std::int64_t>(arrays.vertices.size() / 2)};
  arrays.ids = {0};
  arrays.heights = {fixture::height};
  arrays.base_heights = {fixture::base_height};
  return arrays;
}

int main()
{
  GridConfig grid;
  grid.nx = fixture::nx; grid.ny = fixture::ny; grid.nz = fixture::nz;
  grid.cell_size = fixture::cell_size;
  ModelSettings model;
  model.sensor_x = fixture::sensor_x; model.sensor_y = fixture::sensor_y;
  model.roughness_length = fixture::roughness;
  WindCondition condition;
  condition.speed = fixture::speed; condition.direction = fixture::direction;
  condition.reference_height = fixture::reference_height;
  SolverOptions options;
  options.tolerance = fixture::tolerance; options.max_iterations = fixture::max_iterations;
  const auto geometry = building();
  WindData retained;
  for (int repeat = 0; repeat < 12; ++repeat) {
    WindRunner runner;
    Messages messages;
    rejects<std::runtime_error>([&] { runner.solve(condition, options, messages); });
    runner.prepare(grid, model, geometry, messages);
    require(!messages.empty(), "QES diagnostics were not buffered");
    retained = runner.solve(condition, options, messages);
    require(retained.converged, "Runner building solve did not converge");
    require(retained.velocity.size() == std::size_t(grid.nx) * grid.ny * grid.nz * 3,
            "Runner returned ghost cells");
    auto bad = geometry;
    bad.offsets = {0, -1};
    rejects<std::invalid_argument>([&] { runner.prepare(grid, model, bad, messages); });
    bad.offsets = {0, 1, 5};
    bad.heights = {8, 8}; bad.base_heights = {0, 0}; bad.ids = {0, 1};
    rejects<std::invalid_argument>([&] { runner.prepare(grid, model, bad, messages); });
    bad = geometry; bad.vertices.pop_back();
    rejects<std::invalid_argument>([&] { runner.prepare(grid, model, bad, messages); });
    auto wind = condition; wind.reference_height = 1e-100;
    rejects<std::invalid_argument>([&] { runner.solve(wind, options, messages); });
    wind = condition; wind.reference_height = 1e-20;
    rejects<std::invalid_argument>([&] { runner.solve(wind, options, messages); });
    auto solver = options; solver.tolerance = 1e-12;
    rejects<std::invalid_argument>([&] { runner.solve(condition, solver, messages); });
    solver = options; solver.max_iterations = 1;
    require(!runner.solve(condition, solver, messages).converged, "Missing non-convergence status");
    require(runner.solve(condition, options, messages).velocity == retained.velocity,
            "Failed preparation or repeated solve changed prepared state");
    runner.prepare(grid, model, BuildingArrays{{}, {0}, {}, {}, {}}, messages);
    require(runner.solve(condition, options, messages).building_count == 0, "Repreparation retained buildings");
  }
  for (const auto value : retained.velocity)
    require(std::isfinite(value), "Returned data did not survive runner destruction");

  // Shared and separate runners both use the same process-wide mutex.
  WindRunner shared;
  Messages prepare_messages;
  shared.prepare(grid, model, geometry, prepare_messages);
  std::exception_ptr failures[4];
  std::thread workers[4];
  for (int i = 0; i < 4; ++i)
    workers[i] = std::thread([&, i] {
      try {
        Messages messages;
        WindRunner local;
        auto &runner = i % 2 ? local : shared;
        if (i % 2) runner.prepare(grid, model, geometry, messages);
        require(runner.solve(condition, options, messages).velocity == retained.velocity,
                "Concurrent run changed numerical output");
      } catch (...) { failures[i] = std::current_exception(); }
    });
  for (auto &worker : workers) worker.join();
  for (const auto &failure : failures) if (failure) std::rethrow_exception(failure);

  Messages messages;
  {
    const std::lock_guard<std::mutex> lock(native_mutex());
    const BufferedLogSink sink(messages);
    qes::log::info() << "native info";
    qes::log::debug() << "native debug";
    qes::log::warning() << "native warning";
    qes::log::error() << "native error";
  }
  qes::log::warning() << "must be discarded after sink restoration";
  require(messages.size() == 3, "Buffered sink duplicated errors or failed to restore");
  require(messages[0].level == LogMessage::Level::debug
          && messages[2].level == LogMessage::Level::warning, "Buffered message levels differ");
}
