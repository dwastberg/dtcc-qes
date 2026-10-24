#include "qes_inputs.h"
#include "winds/SolverFactory.h"
#include "winds/Solver_CPU.h"
#include "winds/Solver_CPU_RB.h"
#include "fixture.h"
#include <array>
#include <cmath>
#include <stdexcept>
#include <string>
#include <omp.h>

using namespace dtcc_qes;

static void require(bool condition, const char *message)
{
  if (!condition) throw std::runtime_error(message);
}

struct Snapshot {
  std::array<std::vector<float>, 3> velocity;
  std::vector<int> flags;
  SolveDiagnostics diagnostics;
};

static Snapshot solve(float height, bool serial, int threads)
{
  omp_set_num_threads(threads);
  GridConfig grid;
  grid.nx = fixture::nx; grid.ny = fixture::ny; grid.nz = fixture::nz;
  grid.cell_size = fixture::cell_size;
  ModelSettings model;
  model.sensor_x = fixture::sensor_x; model.sensor_y = fixture::sensor_y;
  model.roughness_length = fixture::roughness;
  BuildingArrays geometry;
  for (const auto &vertex : fixture::vertices)
    geometry.vertices.insert(geometry.vertices.end(), {vertex[0], vertex[1]});
  geometry.offsets = {0, static_cast<std::int64_t>(geometry.vertices.size() / 2)};
  geometry.ids = {0}; geometry.heights = {height}; geometry.base_heights = {fixture::base_height};
  QESInputs inputs(grid, model, geometry);
  // The tall obstacle has stronger blockage; use a 1 m/s profile to keep its
  // float32 multiplier changes resolvable at the fixture's 1e-5 tolerance.
  const float speed = height > fixture::height ? 1.0f : fixture::speed;
  inputs.set_condition({speed, fixture::direction, fixture::reference_height});
  WINDSGeneralData data(&inputs.input, qes::Domain(inputs.simulation.domain, inputs.simulation.grid), CPU_Type);
  data.resetICellFlag();
  data.applyWindProfile(&inputs.input, 0, CPU_Type);
  data.applyParametrizations(&inputs.input);
  std::unique_ptr<Solver> solver;
  if (serial) {
    solver = std::make_unique<Solver_CPU>(data.domain, fixture::tolerance);
  } else {
    solver.reset(SolverFactory::create(CPU_Type, data.domain, fixture::tolerance));
    require(dynamic_cast<Solver_CPU_RB *>(solver.get()), "CPU factory did not select the OpenMP solver");
  }
  const auto diagnostics = solver->solve(&data, fixture::max_iterations);
  require(diagnostics.converged && diagnostics.iterations > 0, "Solver did not converge");
  // Every face adjoining a solid cell must be zero, including faces shared
  // across thread slabs. The tall building spans slabs at 2 and 4 threads.
  const auto &d = data.domain;
  for (int k = 1; k < d.nz() - 1; ++k)
    for (int j = 0; j < d.ny() - 1; ++j)
      for (int i = 0; i < d.nx() - 1; ++i) {
        const auto flag = data.icellflag[d.cell(i, j, k)];
        if (flag != 0 && flag != 2) continue;
        const auto face = d.face(i, j, k);
        require(data.u[face] == 0 && data.u[d.faceAdd(face, 1, 0, 0)] == 0
             && data.v[face] == 0 && data.v[d.faceAdd(face, 0, 1, 0)] == 0
             && data.w[face] == 0 && data.w[d.faceAdd(face, 0, 0, 1)] == 0,
                "Nonzero velocity at a solid face");
      }
  return {{data.u, data.v, data.w}, data.icellflag, diagnostics};
}

int main(int argc, char **argv)
{
  const int threads = argc > 1 ? std::stoi(argv[1]) : 2;
  omp_set_dynamic(0);
  omp_set_num_threads(threads);
  int actual_threads = 0;
#pragma omp parallel shared(actual_threads)
  {
#pragma omp single
    actual_threads = omp_get_num_threads();
  }
  require(actual_threads == threads, "OpenMP did not create the requested team");
  for (const float height : {fixture::height, 24.0f}) {
    const auto serial = solve(height, true, 1);
    const auto baseline = solve(height, false, 1);
    for (int repeat = 0; repeat < 3; ++repeat) {
      const auto parallel = solve(height, false, threads);
      require(parallel.flags == serial.flags, "OpenMP changed cell classifications");
      require(parallel.velocity == baseline.velocity, "Velocity depends on thread count or repeat");
      require(parallel.diagnostics.iterations == baseline.diagnostics.iterations
           && parallel.diagnostics.max_lagrange_multiplier_change == baseline.diagnostics.max_lagrange_multiplier_change,
              "Convergence depends on thread count or repeat");
      for (std::size_t component = 0; component < parallel.velocity.size(); ++component)
        for (std::size_t i = 0; i < parallel.velocity[component].size(); ++i) {
          const auto actual = parallel.velocity[component][i], expected = serial.velocity[component][i];
          require(std::isfinite(actual), "Non-finite OpenMP velocity");
          require(std::abs(actual - expected) <= 2e-5f + 1e-5f * std::abs(expected),
                  "OpenMP velocity differs from the serial baseline");
        }
    }
  }
}
