#include "qes_inputs.h"
#include "log_sink.h"
#include "winds/TURBGeneralData.h"
#include "winds/SolverFactory.h"
#include "util/QESFeatures.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>

using namespace dtcc_qes;

namespace {
void require(bool value, const char *message)
{
  if (!value) throw std::runtime_error(message);
}

template<class Operation>
void rejects(Operation operation, const std::string &message_fragment)
{
  try {
    operation();
  } catch (const std::invalid_argument &error) {
    require(std::string(error.what()).find(message_fragment) != std::string::npos,
            "Input error did not explain the invalid turbulence configuration");
    return;
  }
  throw std::runtime_error("Invalid turbulence configuration was accepted");
}

struct Case {
  GridConfig grid;
  ModelSettings model;
  TURBParams params;
  std::unique_ptr<QESInputs> inputs;
  std::unique_ptr<WINDSGeneralData> data;

  explicit Case(int nz = 20, double roughness = 0.1, bool building = false)
  {
    grid.nz = nz;
    model.roughness_length = roughness;
    BuildingArrays geometry{{}, {0}, {}, {}, {}};
    if (building)
      geometry = {{30,25, 30,35, 40,35, 40,25, 30,25}, {0,5}, {0}, {8}, {0}};
    inputs = std::make_unique<QESInputs>(grid, model, geometry);
    inputs->input.turbParams = &params;
    data = std::make_unique<WINDSGeneralData>(&inputs->input, make_domain(*inputs), CPU_Type);
  }

  std::unique_ptr<TURBGeneralData> construct()
  {
    return std::make_unique<TURBGeneralData>(&inputs->input, data.get());
  }
};

struct CountingMixing : LocalMixing {
  int &destroyed;
  explicit CountingMixing(int &count) : destroyed(count) {}
  ~CountingMixing() override { ++destroyed; }
  void defineMixingLength(const WINDSInputData *, WINDSGeneralData *) override {}
};

struct CountingWall : TURBWall {
  int &destroyed;
  explicit CountingWall(int &count) : destroyed(count) {}
  ~CountingWall() override { ++destroyed; }
  void setWallsVelocityDeriv(WINDSGeneralData *, TURBGeneralData *) override {}
  void setWallsStressDeriv(WINDSGeneralData *, TURBGeneralData *,
                          const std::vector<float> &, const std::vector<float> &,
                          const std::vector<float> &) override {}
  void set_loglaw_stairstep(WINDSGeneralData *, TURBGeneralData *) override {}
};

void ownership()
{
  static_assert(std::has_virtual_destructor_v<LocalMixing>);
  static_assert(std::has_virtual_destructor_v<TURBWall>);
  int walls_destroyed = 0, mixing_destroyed = 0;
  {
    std::unique_ptr<TURBWall> wall = std::make_unique<CountingWall>(walls_destroyed);
    Case fixture;
    auto turb = fixture.construct();
    turb->localMixing = std::make_unique<CountingMixing>(mixing_destroyed);
  }
  require(walls_destroyed == 1 && mixing_destroyed == 1,
          "Deleting owned turbulence helpers skipped derived destruction");
}

void references()
{
  for (const bool with_building : {false, true}) {
    Case fixture(20, 0.1, with_building);
    std::fill(fixture.data->u.begin(), fixture.data->u.end(), 3.0f);
    std::fill(fixture.data->v.begin(), fixture.data->v.end(), 4.0f);
    auto turb = fixture.construct();
    const TURBGeneralData &view = *turb;
    const float roughness = with_building ? 0.8f : 0.1f;
    const float displacement = with_building ? 5.6f : 0.0f;
    const float height = with_building ? 24.0f : 10.0f;
    require(view.getReferenceHeight() == height && view.getReferenceSpeed() == 5.0f,
            "Turbulence reference height/speed accessor is incorrect");
    require(view.getRoughnessLength() == roughness
              && view.getDisplacementHeight() == displacement,
            "Turbulence morphometric accessor is incorrect");
    require(view.getUpperBound() == 20.0f, "Turbulence cap accessor is incorrect");
    const double expected = 0.4 * 5.0 / std::log((height - displacement) / roughness);
    require(std::abs(view.getFrictionVelocity() - expected) < 1e-6,
            "Turbulence friction velocity accessor is incorrect");
  }
}

void lifecycle()
{
  Case fixture;
  for (int repeat = 0; repeat < 32; ++repeat) {
    auto turb = fixture.construct();
    require(!turb->icellfluid.empty(), "Turbulence setup omitted all fluid cells");
  }
  // The reference-plane failure happens after helper construction. Member
  // ownership must also unwind correctly when the complete object never exists.
  fixture.inputs->series.site_z0 = 0.5f;
  for (int repeat = 0; repeat < 32; ++repeat)
    rejects([&] { fixture.construct(); }, "reference height");
  fixture.inputs->series.site_z0 = 0.1f;
  require(!fixture.construct()->icellfluid.empty(), "Failed construction damaged the wind geometry");
  // The existing geometry-only constructor also destroys an empty helper set.
  TURBGeneralData geometry_only(fixture.data.get());
}

void run(const std::string &mode)
{
  if (mode == "low_top") {
    Case fixture(6, 0.05);
    rejects([&] { fixture.construct(); }, "domain top");
  } else if (mode == "ref_in_top_cell") {
    Case fixture(10, 0.19);
    rejects([&] { fixture.construct(); }, "reference height");
  } else if (mode == "ref_above_top") {
    Case fixture(10, 0.3);
    rejects([&] { fixture.construct(); }, "reference height");
  } else if (mode == "reference_boundary") {
    Case fixture(10, 0.18);
    auto turb = fixture.construct();
    require(std::isfinite(turb->getFrictionVelocity()),
            "Last safe reference layer should be accepted by the core guard");
  } else if (mode == "methods") {
    Case fixture;
    for (int method : {-1, 2, 5}) {
      fixture.params.methodLocalMixing = method;
      rejects([&] { fixture.construct(); }, "mixing");
    }
#ifndef HAS_OPTIX
    fixture.params.methodLocalMixing = 3;
    rejects([&] { fixture.construct(); }, "mixing");
#endif
#if !QES_ENABLE_IO
    fixture.params.methodLocalMixing = 4;
    rejects([&] { fixture.construct(); }, "mixing");
#endif
    fixture.params.methodLocalMixing = 0;
    require(!fixture.construct()->icellfluid.empty(), "Rejected method damaged later setup");
  } else if (mode == "ownership") {
    ownership();
  } else if (mode == "references") {
    references();
  } else if (mode == "lifecycle") {
    lifecycle();
  } else {
    throw std::invalid_argument("Unknown turbulence test mode");
  }
}
}

int main(int argc, char **argv)
{
  try {
    const std::lock_guard<std::mutex> lock(native_mutex());
    Messages messages;
    BufferedLogSink sink(messages);
    require(argc == 2, "A turbulence test mode is required");
    run(argv[1]);
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
