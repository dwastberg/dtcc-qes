#include "qes_inputs.h"
#include "log_sink.h"
#include "stress_validity.h"
#include "winds/TURBGeneralData.h"
#include "winds/SolverFactory.h"
#include "util/QESFeatures.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <memory>
#include <limits>
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

  explicit Case(int nz = 20, double roughness = 0.1, bool building = false,
                std::vector<double> layers = {})
  {
    grid.nz = nz;
    if (!layers.empty()) {
      grid.nz = static_cast<int>(layers.size());
      grid.dz_layers = std::move(layers);
    }
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

using Stress = std::array<float, 6>;

Stress stress_at(const TURBGeneralData &turb, long cell)
{
  return {turb.txx[cell], turb.txy[cell], turb.txz[cell],
          turb.tyy[cell], turb.tyz[cell], turb.tzz[cell]};
}

void close(double actual, double expected, const char *message,
           double rtol = 1e-5, double atol = 1e-7)
{
  if (!std::isfinite(actual) || std::abs(actual - expected) > atol + rtol * std::abs(expected))
    throw std::runtime_error(std::string(message) + ": actual=" + std::to_string(actual)
                             + ", expected=" + std::to_string(expected));
}

void velocity_profile(WINDSGeneralData &data, double degrees, double scale = 1)
{
  const double angle = degrees * std::acos(-1.0) / 180;
  const auto &d = data.domain;
  for (int k = 0; k < d.nz(); ++k)
    for (int j = 0; j < d.ny(); ++j)
      for (int i = 0; i < d.nx(); ++i) {
        const double speed = scale * (10 + 0.1 * d.z[std::min(k, d.nz() - 2)]);
        data.u[d.face(i, j, k)] = speed * std::cos(angle);
        data.v[d.face(i, j, k)] = speed * std::sin(angle);
        data.w[d.face(i, j, k)] = 0;
      }
}

std::array<double, 6> shear_oracle(double length, double degrees, double gradient = 0.1)
{
  // Independent covariance construction from streamwise/crosswind/vertical
  // unit vectors and the analytic flat-shear variances and shear stress.
  const double angle = degrees * std::acos(-1.0) / 180;
  const std::array<double, 3> n{std::cos(angle), std::sin(angle), 0};
  const std::array<double, 3> m{-n[1], n[0], 0}, z{0, 0, 1};
  const double lu = length * gradient;
  const double a = std::pow(2.5 * lu, 2), b = std::pow(2.0 * lu, 2);
  const double c = std::pow(1.3 * lu, 2), uw = -length * length * gradient * std::abs(gradient);
  const std::array<std::array<int, 2>, 6> components{{{0,0}, {0,1}, {0,2}, {1,1}, {1,2}, {2,2}}};
  std::array<double, 6> result;
  for (std::size_t component = 0; component < components.size(); ++component) {
    const auto [i, j] = components[component];
    result[component] = a * n[i] * n[j] + b * m[i] * m[j] + c * z[i] * z[j]
      + uw * (n[i] * z[j] + z[i] * n[j]);
  }
  return result;
}

void rotation()
{
  Case fixture;
  auto turb = fixture.construct();
  for (double degrees : {0., 45., 30., 90., 180., 225., 210., 270.}) {
    velocity_profile(*fixture.data, degrees);
    const auto before_u = fixture.data->u, before_v = fixture.data->v, before_w = fixture.data->w;
    turb->run();
    require(before_u == fixture.data->u && before_v == fixture.data->v && before_w == fixture.data->w,
            "Turbulence changed the solved wind");
    const auto &d = fixture.data->domain;
    const double angle = degrees * std::acos(-1.0) / 180;
    const auto sample = d.cell(10, 10, 5); // z = 9 m, sigma = 0.9 m/s.
    const auto tau = stress_at(*turb, sample);
    const double projected = std::cos(angle) * std::cos(angle) * tau[0]
      + 2 * std::cos(angle) * std::sin(angle) * tau[1]
      + std::sin(angle) * std::sin(angle) * tau[3];
    std::cout << "flow heading=" << degrees << " sigma=" << std::sqrt(projected)
              << " expected=0.9 m/s\n";
    close(std::sqrt(projected), 0.9, "Flat shear lost streamwise variance under rotation");
    for (int k = 2; k < fixture.grid.nz; ++k) {
      const auto cell = d.cell(10, 10, k);
      const auto actual = stress_at(*turb, cell);
      const auto expected = shear_oracle(turb->Lm[cell], degrees);
      const double cap = turb->getUpperBound() * turb->getFrictionVelocity() * turb->getFrictionVelocity();
      for (std::size_t component = 0; component < actual.size(); ++component) {
        require(std::abs(expected[component]) < cap, "Rotation oracle must use uncapped stress");
        close(actual[component], expected[component], "Full shear tensor disagrees with analytic oracle");
      }
    }
    for (int cell : turb->icellfluid) {
      for (float value : stress_at(*turb, cell))
        require(std::isfinite(value), "Manufactured flow produced nonfinite stress");
      require(std::isfinite(turb->tke[cell]) && std::isfinite(turb->CoEps[cell]),
              "Manufactured flow produced nonfinite turbulence quantities");
    }
  }
}

struct DirectTurbulence : TURBGeneralData {
  using TURBGeneralData::TURBGeneralData;
  void compute_shear()
  {
    for (int cell : icellfluid) Gxz[cell] = 0.1f;
    getTurbulentViscosity();
    stressTensor();
  }
};

void direction_oracle(const TURBGeneralData &turb, long cell, double heading)
{
  auto expected = shear_oracle(turb.Lm[cell], heading);
  // Here the prescribed gradient stays along +x while only the anisotropy's
  // direction changes. The shear components must survive the round trip.
  expected[2] = -double(turb.Lm[cell]) * turb.Lm[cell] * 0.01;
  expected[4] = 0;
  const auto actual = stress_at(turb, cell);
  for (std::size_t component = 0; component < actual.size(); ++component)
    close(actual[component], expected[component], "Direction fallback chose the wrong wind basis");
}

void rotation_fallback()
{
  Case fixture;
  std::fill(fixture.data->u.begin(), fixture.data->u.end(), 10);
  DirectTurbulence turb(&fixture.inputs->input, fixture.data.get());
  auto &data = *fixture.data;
  const auto &d = data.domain;
  const int i = 10, j = 10;
  const int reference = static_cast<int>(std::lower_bound(d.z_face.begin(), d.z_face.end(), 15.f)
                                          - d.z_face.begin());
  const auto cell = d.cell(i, j, 5), reference_cell = d.cell(i, j, reference);
  const auto reference_face = d.face(i, j, reference);
  const auto point = [&](int k, double heading) {
    const double angle = heading * std::acos(-1.0) / 180;
    data.u[d.face(i, j, k)] = 10 * std::cos(angle);
    data.v[d.face(i, j, k)] = 10 * std::sin(angle);
  };
  point(reference, 45);
  turb.compute_shear();
  direction_oracle(turb, cell, 45);
  require(turb.getRotationFallbackColumns() == 0, "Valid reference used a fallback");

  point(reference - 1, 90); // Velocity centre 15 m: nearest alternative.
  point(reference + 1, 30); // Velocity centre 19 m.
  for (int flag : {0, 2}) {
    data.icellflag[reference_cell] = flag;
    turb.compute_shear();
    direction_oracle(turb, cell, 90);
    require(turb.getRotationFallbackColumns() == 1,
            "Fallback diagnostic must count a column only once");
  }
  for (int k : {reference - 1, reference - 2}) {
    data.u[d.face(i, j, k)] = 0;
    data.v[d.face(i, j, k)] = 0;
  }
  point(reference - 3, 90); // 11 m and 19 m are equally distant from 15 m.
  turb.compute_shear();
  direction_oracle(turb, cell, 30);
  require(turb.getRotationFallbackColumns() == 1, "Fallback count accumulated across calls");
  point(reference - 1, 90);
  data.terrain[d.cell2d(i, j)] = 1;
  turb.compute_shear();
  direction_oracle(turb, cell, 90);
  data.terrain[d.cell2d(i, j)] = 0;
  data.icellflag[reference_cell] = 1;
  for (const float unusable : {0.f, std::numeric_limits<float>::quiet_NaN()}) {
    data.u[reference_face] = unusable;
    data.v[reference_face] = 0;
    turb.compute_shear();
    direction_oracle(turb, cell, 90);
    require(turb.getRotationFallbackColumns() == 1, "Unusable reference was not diagnosed");
  }
  for (int k = 1; k <= d.nz() - 2; ++k) {
    data.u[d.face(i, j, k)] = 0;
    data.v[d.face(i, j, k)] = 0;
  }
  turb.compute_shear();
  direction_oracle(turb, cell, 0);
  require(turb.getRotationFallbackColumns() == 1, "Directionless column was not diagnosed");
  point(reference, 45);
  turb.compute_shear();
  direction_oracle(turb, cell, 45);
  require(turb.getRotationFallbackColumns() == 0, "Fallback counter did not reset");

  Case stretched(15, 0.1, false, {1,1,1,1,1,1,1,1,1,1,3.8,0.2,6,10,10});
  std::fill(stretched.data->u.begin(), stretched.data->u.end(), 10);
  DirectTurbulence nonuniform(&stretched.inputs->input, stretched.data.get());
  const auto &sd = stretched.data->domain;
  const int sr = static_cast<int>(std::lower_bound(sd.z_face.begin(), sd.z_face.end(), 15.f)
                                   - sd.z_face.begin());
  stretched.data->icellflag[sd.cell(i, j, sr)] = 0;
  // The adjacent lower cell is at 17 m; the next lower centre at 13.9 m
  // is closer to 15 m. Face-distance or index-distance searches miss it.
  stretched.data->u[sd.face(i, j, sr - 2)] = 0;
  stretched.data->v[sd.face(i, j, sr - 2)] = 10;
  nonuniform.compute_shear();
  direction_oracle(nonuniform, sd.cell(i, j, 5), 90);
  require(nonuniform.getRotationFallbackColumns() == 1,
          "Nonuniform fallback must compare physical heights, not layer indices");

  Case top_face(8, 0.05, false, {2,2,2,2,2,2,2,1}); // Domain top exactly 15 m.
  velocity_profile(*top_face.data, 45);
  auto at_top = top_face.construct();
  at_top->run();
  require(at_top->getRotationFallbackColumns() == 38 * 28,
          "Top reference face must use a valid physical level without reading its cell flag");
  for (int id : at_top->icellfluid)
    for (float value : stress_at(*at_top, id))
      require(std::isfinite(value), "Top-face fallback produced nonfinite stress");
}

void calm()
{
  Case fixture;
  auto turb = fixture.construct();
  const auto lengths = turb->Lm;
  turb->run();
  require(turb->getRotationFallbackColumns() == 38 * 28,
          "Calm wind must diagnose every directionless computed column");
  for (int cell : turb->icellfluid) {
    const auto raw = stress_at(*turb, cell);
    require(std::all_of(raw.begin(), raw.end(), [](float value) { return value == 0; }),
            "Calm wind stress is not finite zero");
    require(turb->tke[cell] == 0 && turb->CoEps[cell] == 0 && turb->Lm[cell] > 0,
            "Calm turbulence must retain geometric mixing length");
    require(stress_validity(raw).valid && std::isnan(streamwise_variance(raw, {0,0,0})),
            "Zero tensor validity and undefined wind direction were conflated");
  }
  require(turb->Lm == lengths, "Stress calculation changed mixing lengths");
  velocity_profile(*fixture.data, 45);
  turb->run();
  require(turb->getRotationFallbackColumns() == 0, "New wind solve inherited calm fallback count");
}

void validity()
{
  const float eps = std::numeric_limits<float>::epsilon();
  struct Example { Stress raw; bool valid; double minimum, radius; };
  const std::array<Example, 8> examples{{
    {{0,0,0,0,0,0}, true, 0, 0},
    {{4,0,0,2,0,1}, true, 1, 4},
    {{3,1,1,3,1,3}, true, 2, 5},
    {{1,1,0,1,0,0}, true, 0, 2},
    {{-eps,0,0,1,0,2}, true, -eps, 2},
    {{1,1+eps,0,1,0,1}, true, -eps, 2+double(eps)},
    {{1,2,0,1,0,1}, false, -1, 3},
    {{-1,0,0,1,0,2}, false, -1, 2}
  }};
  for (const auto &example : examples)
    for (float scale : {1e-20f, 1.f, 1e20f}) {
      Stress raw = example.raw;
      for (float &value : raw) value *= scale;
      const auto before = raw;
      const auto result = stress_validity(raw);
      require(result.valid == example.valid, "Scale-relative stress validity is incorrect");
      const double roundoff = 8 * eps * example.radius * scale;
      close(result.minimum_eigenvalue, example.minimum * scale, "Minimum eigenvalue is incorrect", 1e-6, roundoff);
      close(result.spectral_radius, example.radius * scale, "Spectral radius is incorrect", 1e-6, roundoff);
      close(result.tolerance, 32 * double(eps) * result.spectral_radius,
            "Validity tolerance is not relative to tensor magnitude", 1e-14, 0);
      require(raw == before, "Validity check changed raw stress");
      if (!example.valid) {
        require(std::isnan(streamwise_variance(raw, {1,0,0}))
                  && std::isnan(streamwise_variance(raw, {1,-1,0})),
                "Indefinite tensor produced a finite projected statistic");
      }
    }
  close(streamwise_variance({4,0,0,2,0,1}, {1,1,0}), 3, "Projection is incorrect");
  for (const double speed_scale : {1e-200, 1e200})
    close(streamwise_variance({4,0,0,2,0,1}, {speed_scale,speed_scale,0}),
          3, "Direction normalization overflowed or underflowed");
  require(streamwise_variance({-eps,0,0,1,0,2}, {1,0,0}) == 0,
          "Roundoff-sized negative projection was not rounded to zero");
  for (const auto &v : std::array<std::array<double,3>,3>{{{0,0,0},
        {std::numeric_limits<double>::infinity(),0,0},
        {0,std::numeric_limits<double>::quiet_NaN(),0}}})
    require(std::isnan(streamwise_variance({1,0,0,1,0,1}, v)),
            "Undefined wind direction produced a projected statistic");
  for (float bad : {std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()})
    for (std::size_t component = 0; component < 6; ++component) {
      Stress raw{1,0,0,1,0,1};
      raw[component] = bad;
      require(!stress_validity(raw).valid && std::isnan(streamwise_variance(raw, {1,0,0})),
              "Nonfinite tensor was accepted");
    }
}

void building_validity()
{
  Case fixture(20, 0.1, true);
  auto turb = fixture.construct();
  auto &data = *fixture.data;
  fixture.inputs->set_condition({5,270,10});
  data.resetICellFlag();
  data.applyWindProfile(&fixture.inputs->input, 0, CPU_Type);
  data.applyParametrizations(&fixture.inputs->input);
  std::unique_ptr<Solver> solver(SolverFactory::create(CPU_Type, data.domain, 1e-5f));
  solver->resetLambda();
  require(solver->solve(&data, 20000).converged, "Building validity case did not converge");
  turb->run();
  std::vector<Stress> original;
  std::vector<bool> valid;
  std::size_t invalid = 0, negative_projection = 0;
  for (int cell : turb->icellfluid) {
    const auto raw = stress_at(*turb, cell);
    for (float value : raw) require(std::isfinite(value), "Building stress is nonfinite");
    const auto status = stress_validity(raw);
    const auto [i,j,k] = data.domain.getCellIdx(cell);
    const auto &d = data.domain;
    const std::array<double,3> velocity{
      0.5 * (data.u[d.face(i,j,k)] + data.u[d.face(i+1,j,k)]),
      0.5 * (data.v[d.face(i,j,k)] + data.v[d.face(i,j+1,k)]),
      0.5 * (data.w[d.face(i,j,k)] + data.w[d.face(i,j,k+1)])};
    const double projected = streamwise_variance(raw, velocity);
    if (!status.valid) {
      ++invalid;
      require(std::isnan(projected), "Invalid raw building stress produced a finite statistic");
    }
    const auto [u,v,w] = velocity;
    if (raw[0]*u*u + raw[3]*v*v + raw[5]*w*w
          + 2*(raw[1]*u*v + raw[2]*u*w + raw[4]*v*w) < 0) ++negative_projection;
    require(raw == stress_at(*turb, cell), "Validity projection rewrote QES stress");
    original.push_back(raw);
    valid.push_back(status.valid);
  }
  std::cout << "building computed=" << original.size() << " invalid=" << invalid
            << " negative_projected=" << negative_projection << '\n';
  // Scaling a frozen solved wind tests homogeneity without changing the
  // linear solver's absolute stopping tolerance between wind solves.
  for (auto *field : {&data.u, &data.v, &data.w})
    for (float &value : *field) value *= 2;
  turb->run();
  std::size_t index = 0;
  for (int cell : turb->icellfluid) {
    const auto raw = stress_at(*turb, cell);
    for (std::size_t component = 0; component < 6; ++component)
      close(raw[component], 4 * original[index][component], "Stress lost quadratic speed scaling", 1e-4);
    require(stress_validity(raw).valid == valid[index], "Speed rescaling changed stress validity");
    ++index;
  }
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
  } else if (mode == "rotation") {
    rotation();
  } else if (mode == "rotation_fallback") {
    rotation_fallback();
  } else if (mode == "calm") {
    calm();
  } else if (mode == "validity") {
    validity();
  } else if (mode == "building_validity") {
    building_validity();
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
