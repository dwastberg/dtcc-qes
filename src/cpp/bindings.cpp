#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include "build_info.h"
#include "wind_runner.h"
#include "control_bindings.h"
#include <chrono>
#include <cstring>
#include <exception>
#include <type_traits>
#include <utility>

namespace nb = nanobind;
using namespace nb::literals;
using namespace dtcc_qes;

namespace {
using Vertices = nb::ndarray<nb::numpy, const double, nb::shape<-1, 2>, nb::c_contig, nb::device::cpu>;
using Floats = nb::ndarray<nb::numpy, const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Integers = nb::ndarray<nb::numpy, const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

template<typename Array>
auto copy_input(const Array &array)
{
  using T = std::remove_const_t<typename Array::Scalar>;
  std::vector<T> values(array.size());
  if (!values.empty()) std::memcpy(values.data(), array.data(), values.size() * sizeof(T));
  return values;
}

template<typename Operation>
auto native_call(Operation operation)
{
  using Result = decltype(operation(std::declval<Messages &>()));
  Result result;
  Messages messages;
  std::exception_ptr failure;
  {
    // Release before waiting on the native mutex, and unlock that mutex before
    // reacquiring the GIL. The native handler only touches C++ memory.
    nb::gil_scoped_release release;
    try { result = operation(messages); }
    catch (...) { failure = std::current_exception(); }
  }
  try {
    nb::list buffered;
    for (const auto &message : messages)
      buffered.append(nb::make_tuple(message.level == LogMessage::Level::warning ? 30 : 10, message.text.c_str()));
    if (!buffered.empty())
      nb::module_::import_("dtcc_qes._logging").attr("_forward_native_messages")(buffered);
  } catch (nb::python_error &error) {
    if (!failure) throw;
    // A user logging handler must not obscure a native input/solver exception.
    error.restore();
    PyErr_Clear();
  }
  if (failure) std::rethrow_exception(failure);
  return result;
}

template<typename T>
nb::object owned_array(const std::vector<T> &values, nb::tuple shape, const char *dtype)
{
  nb::object result = nb::module_::import_("numpy").attr("empty")(shape, "dtype"_a = dtype);
  auto array = nb::cast<nb::ndarray<nb::numpy, T, nb::c_contig, nb::device::cpu>>(result);
  if (!values.empty()) std::memcpy(array.data(), values.data(), values.size() * sizeof(T));
  return result;
}

nb::dict python_result(const WindData &data)
{
  const auto transfer_started = std::chrono::steady_clock::now();
  nb::dict result;
  result["x"] = owned_array(data.x, nb::make_tuple(data.nx), "float32");
  result["y"] = owned_array(data.y, nb::make_tuple(data.ny), "float32");
  result["z"] = owned_array(data.z, nb::make_tuple(data.nz), "float32");
  result["z_faces"] = owned_array(data.z_faces, nb::make_tuple(data.nz + 1), "float32");
  result["velocity"] = owned_array(data.velocity, nb::make_tuple(data.nz, data.ny, data.nx, 3), "float32");
  result["cell_flags"] = owned_array(data.cell_flags, nb::make_tuple(data.nz, data.ny, data.nx), "int32");
  nb::dict diagnostics;
  diagnostics["iterations"] = data.iterations;
  diagnostics["max_lagrange_multiplier_change"] = data.max_lagrange_multiplier_change;
  diagnostics["tolerance"] = data.tolerance;
  diagnostics["converged"] = data.converged;
  diagnostics["precision"] = data.precision;
  const auto &div = data.divergence;
  diagnostics["max_divergence"] = div.cells ? nb::cast(div.interior_max) : nb::none();
  diagnostics["rms_divergence"] = div.cells ? nb::cast(div.interior_rms) : nb::none();
  diagnostics["top_band_max_divergence"] = div.top_band_cells ? nb::cast(div.top_band_max) : nb::none();
  diagnostics["divergence_cell_count"] = div.cells;
  diagnostics["top_band_cell_count"] = div.top_band_cells;
  result["diagnostics"] = diagnostics;
  result["building_count"] = data.building_count;
  result["turbulence"] = nb::none();
  if (data.turbulence) {
    const auto &t = *data.turbulence;
    const auto shape = nb::make_tuple(data.nz, data.ny, data.nx);
    nb::dict fields;
    fields["stress"] = owned_array(t.stress, nb::make_tuple(data.nz, data.ny, data.nx, 6), "float32");
    fields["tke"] = owned_array(t.tke, shape, "float32");
    fields["co_eps"] = owned_array(t.co_eps, shape, "float32");
    fields["mixing_length"] = owned_array(t.mixing_length, shape, "float32");
    fields["state"] = owned_array(t.state, shape, "uint8");
    fields["stress_valid"] = owned_array(t.stress_valid, shape, "uint8");
    fields["friction_velocity"] = t.friction_velocity;
    fields["reference_speed"] = t.reference_speed;
    fields["reference_height"] = t.reference_height;
    fields["roughness_length"] = t.roughness_length;
    fields["displacement_height"] = t.displacement_height;
    fields["upper_bound"] = t.upper_bound;
    fields["computed_cells"] = t.computed_cells;
    fields["capped_cells"] = t.capped_cells;
    fields["invalid_stress_cells"] = t.invalid_stress_cells;
    fields["rotation_fallback_columns"] = t.rotation_fallback_columns;
    result["turbulence"] = fields;
  }
  if (data.control) {
    auto control = control_binding::encode(*data.control);
    auto timings = nb::cast<nb::dict>(control["timings"]);
    timings["output_transfer_seconds"] = std::chrono::duration<double>(std::chrono::steady_clock::now()-transfer_started).count();
    result["control"] = control;
  }
  nb::module_::import_("dtcc_qes._logging").attr("_log_solve")(result);
  return result;
}
}

NB_MODULE(_qes, m)
{
#ifdef DTCC_QES_DISTRIBUTABLE_BUILD
  nanobind::set_leak_warnings(false);
#endif
  m.doc() = "Private, serialized in-memory QES wind runner";
  m.attr("qes_version") = dtcc_qes::qes_version();
  m.attr("qes_revision") = dtcc_qes::qes_revision();
  m.attr("io_enabled") = false;
  m.attr("openmp_enabled") = dtcc_qes::openmp_enabled();
  m.attr("cpu_backend") = dtcc_qes::cpu_backend();
  m.attr("cpu_sweep_order") = dtcc_qes::cpu_sweep_order();
  m.attr("fp_contract") = dtcc_qes::fp_contract();
  m.attr("solver_policy_revision") = dtcc_qes::solver_policy_revision();
  m.attr("solver_policy_build_supported") = dtcc_qes::solver_policy_build_supported();
  m.attr("compiler_id") = DTCC_QES_COMPILER_ID;
  m.attr("compiler_version") = DTCC_QES_COMPILER_VERSION;
  m.attr("build_type") = DTCC_QES_BUILD_TYPE;
  m.def("_core_grid_shape", &dtcc_qes::core_grid_shape);

  nb::class_<GridConfig>(m, "GridConfig")
    .def(nb::init<>())
    .def_rw("nx", &GridConfig::nx).def_rw("ny", &GridConfig::ny).def_rw("nz", &GridConfig::nz)
    .def_rw("cell_size", &GridConfig::cell_size).def_rw("max_cells", &GridConfig::max_cells);
  nb::class_<ModelSettings>(m, "ModelSettings")
    .def(nb::init<>())
    .def_rw("roughness_length", &ModelSettings::roughness_length)
    .def_rw("sensor_x", &ModelSettings::sensor_x).def_rw("sensor_y", &ModelSettings::sensor_y)
    .def_rw("wall_roughness", &ModelSettings::wall_roughness)
    .def_rw("rooftop_flag", &ModelSettings::rooftop_flag)
    .def_rw("upwind_cavity_flag", &ModelSettings::upwind_cavity_flag)
    .def_rw("street_canyon_flag", &ModelSettings::street_canyon_flag)
    .def_rw("street_intersection_flag", &ModelSettings::street_intersection_flag)
    .def_rw("wake_flag", &ModelSettings::wake_flag)
    .def_rw("high_rise_flag", &ModelSettings::high_rise_flag)
    .def_rw("sidewall_flag", &ModelSettings::sidewall_flag)
    .def_rw("exposed_faces", &ModelSettings::exposed_faces);
  nb::enum_<ProfileKind>(m, "ProfileKind")
    .value("log", ProfileKind::Log).value("layer_table", ProfileKind::LayerTable);
  nb::class_<WindCondition>(m, "WindCondition")
    .def(nb::init<>()).def_rw("speed", &WindCondition::speed)
    .def_rw("direction", &WindCondition::direction).def_rw("reference_height", &WindCondition::reference_height)
    .def_rw("profile_kind", &WindCondition::profile_kind)
    .def_rw("layer_u", &WindCondition::layer_u).def_rw("layer_v", &WindCondition::layer_v);
  nb::class_<SolverOptions>(m, "SolverOptions")
    .def(nb::init<>()).def_rw("tolerance", &SolverOptions::tolerance)
    .def_rw("max_iterations", &SolverOptions::max_iterations)
    .def_rw("precision", &SolverOptions::precision);
  nb::class_<TurbulenceSettings>(m, "TurbulenceSettings")
    .def(nb::init<>()).def_rw("enabled", &TurbulenceSettings::enabled)
    .def_rw("mixing_length_method", &TurbulenceSettings::mixing_length_method);
  nb::class_<WindRunner>(m, "WindRunner")
    .def(nb::init<>())
    .def("prepare", [](WindRunner &runner, const GridConfig &grid, const ModelSettings &model,
                       Vertices vertices, Integers offsets, Floats heights, Floats base_heights, Integers ids,
                       Floats dz_layers, const TurbulenceSettings *turbulence, Integers ring_offsets) {
      // Snapshot Python inputs while holding the GIL. Native work never borrows
      // mutable NumPy buffers or configuration objects from another Python thread.
      GridConfig grid_value = grid;
      if (dz_layers.is_valid()) grid_value.dz_layers = copy_input(dz_layers);
      const ModelSettings model_value = model;
      const TurbulenceSettings turbulence_value = turbulence ? *turbulence : TurbulenceSettings{};
      const BuildingArrays buildings{copy_input(vertices), copy_input(offsets), copy_input(ids),
                                     copy_input(heights), copy_input(base_heights),
                                     ring_offsets.is_valid() ? copy_input(ring_offsets) : std::vector<std::int64_t>{}};
      native_call([&](Messages &messages) {
        runner.prepare(grid_value, model_value, buildings, turbulence_value, messages);
        return 0;
      });
    }, "grid"_a, "model"_a, nb::arg("vertices").noconvert(), nb::arg("offsets").noconvert(),
       nb::arg("heights").noconvert(), nb::arg("base_heights").noconvert(), nb::arg("ids").noconvert(),
       nb::kw_only(), nb::arg("dz_layers").noconvert().none() = nb::none(),
       nb::arg("turbulence").none() = nb::none(),
       nb::arg("ring_offsets").noconvert().none() = nb::none())
    .def("solve", [](WindRunner &runner, const WindCondition &condition, const SolverOptions &options,nb::object control) {
      const WindCondition wind = condition;
      const SolverOptions solver = options;
      const auto settings = control.is_none() ? std::optional<SolverControl>{} : control_binding::parse(nb::cast<nb::dict>(control));
      try {
        return python_result(native_call([&](Messages &messages) { return runner.solve(wind, solver, messages,settings ? &*settings : nullptr); }));
      } catch (const BudgetExhausted &failure) {
        auto cls=nb::module_::import_("dtcc_qes.solver_control").attr("BudgetExhaustedError");
        auto error=cls(control_binding::encode(failure.record));
        PyErr_SetObject(cls.ptr(),error.ptr());throw nb::python_error();
      } catch (const NumericalFailure &failure) {
        auto cls=nb::module_::import_("dtcc_qes.solver_control").attr("NumericalFailureError");
        auto error=cls(control_binding::encode(failure.record));
        PyErr_SetObject(cls.ptr(),error.ptr());throw nb::python_error();
      }
    }, "condition"_a, "options"_a = SolverOptions{},nb::kw_only(),"control"_a=nb::none());
}
