#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/array.h>
#include "build_info.h"
#include "wind_runner.h"
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
  nb::dict result;
  result["x"] = owned_array(data.x, nb::make_tuple(data.nx), "float32");
  result["y"] = owned_array(data.y, nb::make_tuple(data.ny), "float32");
  result["z"] = owned_array(data.z, nb::make_tuple(data.nz), "float32");
  result["velocity"] = owned_array(data.velocity, nb::make_tuple(data.nz, data.ny, data.nx, 3), "float32");
  result["cell_flags"] = owned_array(data.cell_flags, nb::make_tuple(data.nz, data.ny, data.nx), "int32");
  nb::dict diagnostics;
  diagnostics["iterations"] = data.iterations;
  diagnostics["max_lagrange_multiplier_change"] = data.max_lagrange_multiplier_change;
  diagnostics["tolerance"] = data.tolerance;
  diagnostics["converged"] = data.converged;
  result["diagnostics"] = diagnostics;
  result["building_count"] = data.building_count;
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
    .def_rw("sidewall_flag", &ModelSettings::sidewall_flag);
  nb::class_<WindCondition>(m, "WindCondition")
    .def(nb::init<>()).def_rw("speed", &WindCondition::speed)
    .def_rw("direction", &WindCondition::direction).def_rw("reference_height", &WindCondition::reference_height);
  nb::class_<SolverOptions>(m, "SolverOptions")
    .def(nb::init<>()).def_rw("tolerance", &SolverOptions::tolerance)
    .def_rw("max_iterations", &SolverOptions::max_iterations);
  nb::class_<WindRunner>(m, "WindRunner")
    .def(nb::init<>())
    .def("prepare", [](WindRunner &runner, const GridConfig &grid, const ModelSettings &model,
                       Vertices vertices, Integers offsets, Floats heights, Floats base_heights, Integers ids) {
      // Snapshot Python inputs while holding the GIL. Native work never borrows
      // mutable NumPy buffers or configuration objects from another Python thread.
      const GridConfig grid_value = grid;
      const ModelSettings model_value = model;
      const BuildingArrays buildings{copy_input(vertices), copy_input(offsets), copy_input(ids),
                                     copy_input(heights), copy_input(base_heights)};
      native_call([&](Messages &messages) {
        runner.prepare(grid_value, model_value, buildings, messages);
        return 0;
      });
    }, "grid"_a, "model"_a, nb::arg("vertices").noconvert(), nb::arg("offsets").noconvert(),
       nb::arg("heights").noconvert(), nb::arg("base_heights").noconvert(), nb::arg("ids").noconvert())
    .def("solve", [](WindRunner &runner, const WindCondition &condition, const SolverOptions &options) {
      const WindCondition wind = condition;
      const SolverOptions solver = options;
      return python_result(native_call([&](Messages &messages) { return runner.solve(wind, solver, messages); }));
    }, "condition"_a, "options"_a = SolverOptions{});
}
