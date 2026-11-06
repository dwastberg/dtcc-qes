#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include "build_info.h"
#include "wind_runner.h"
#include "preflight.h"
#include "turbulence_reference.h"
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

nb::dict resource_record() {
  const auto usage=resource_usage();
  nb::dict out;
  const char *names[]={"wind_grid","poisson_operator","solver_workspace"};
  for (std::size_t i=0;i<usage.categories.size();++i) {
    const auto &c=usage.categories[i]; nb::dict value;
    value["objects"]=c.objects; value["bytes"]=c.bytes;
    value["peak_objects"]=c.peak_objects; value["peak_bytes"]=c.peak_bytes;
    out[names[i]]=value;
  }
  out["scope"]="process live ownership; selected wind-grid vector capacities, Poisson storage and solver buffers; excludes geometry, coordinate arrays, separate turbulence storage, returned arrays and construction temporaries";
  return out;
}
nb::dict progress_record(const WindRunner &runner) {
  const auto p=runner.progress(); nb::dict out;
  out["operation_id"]=p.operation_id; out["revision"]=p.revision;
  out["operation"]=p.operation; out["phase"]=p.phase;
  out["last_completed_stage"]=p.last_completed_stage;
  out["completed_sweeps"]=p.completed_sweeps; out["last_checkpoint"]=p.last_checkpoint;
  out["elapsed_seconds"]=p.started_at?p.observed_at-p.started_at:0.;
  out["phase_seconds"]=p.phase_started_at?p.observed_at-p.phase_started_at:0.;
  out["finished"]=p.finished; out["resources"]=resource_record();
  return out;
}

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
  if (data.experiment) {
    const auto &e = *data.experiment;
    nb::dict out;
    out["canyon_model"]=canyon_model_name(e.canyon_model);
    out["canyon_schema"]=canyon_schema;
    out["canyon_roof_protection_revision"]=canyon_roof_protection_revision;
    out["canyon_voxel_roof_changes"]=e.canyon_voxel_roof_changes;
    out["canyon_spec_sha256"]=e.canyon_model==CanyonModel::JoinedV1 ? canyon_join_spec_sha256 : "";
    out["canyon_qualification"]="unqualified research; explicit legacy solver control";
    nb::dict fallback;
    for(std::size_t i=0;i<e.canyon_fallback_reasons.size();++i)
      fallback[nb::str(e.canyon_fallback_reasons[i].c_str())]=e.canyon_fallback_counts[i];
    out["canyon_fallback_reasons"]=fallback;
    out["canyon_initial_w"]=owned_array(e.canyon_initial_w,nb::make_tuple(e.canyon_initial_w.size()),"float32");
    out["canyon_roof_trace_columns"]=std::vector<std::string>{"kind","component","native_face","building_index","local_x","local_y","z","physical_roof","voxel_roof","before","after","grid_x","grid_y"};
    out["canyon_roof_trace"]=owned_array(e.canyon_roof_trace,nb::make_tuple(e.canyon_roof_trace.size()/13,13),"float64");
    out["canyon_core_u"]=e.canyon_core_u;
    out["canyon_core_v"]=e.canyon_core_v;
    out["canyon_core_w"]=e.canyon_core_w;
    out["canyon_roof_skipped"]=e.canyon_roof_skipped;
    out["canyon_changed_faces"]=e.canyon_changed_faces;
    out["canyon_roof_changes"]=e.canyon_roof_changes;
    out["canyon_audit_zones"]=e.canyon_audit_zones;
    out["canyon_W_changes"]=e.canyon_W_changes;
    out["canyon_qualified"]=e.canyon_qualified;
    out["canyon_fallback"]=e.canyon_fallback;
    out["canyon_writes"]=e.canyon_writes;
    out["stages"] = e.stages;
    out["actual_threads"] = e.actual_threads;
    out["mass"] = e.mass;
    out["stage_velocity"]=owned_array(e.stage_velocity,nb::make_tuple(e.stages.size(),e.sample_count,3),"float32");
    out["stage_flags"]=owned_array(e.stage_flags,nb::make_tuple(e.stages.size(),e.sample_count),"int32");
    result["experiment"]=out;
  }
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
    result["timings"] = timings;
  } else {
    auto timings=control_binding::encode(data.timings);
    timings["output_transfer_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-transfer_started).count();
    result["timings"]=timings;
  }
  nb::module_::import_("dtcc_qes._logging").attr("_log_solve")(result);
  return result;
}
nb::dict transfer_result(WindRunner &runner, const WindData &data) {
  runner.output_transfer(data.operation_id,false);
  try {
    auto value=python_result(data);
    runner.output_transfer(data.operation_id,true);
    return value;
  } catch (...) { runner.output_transfer(data.operation_id,false,true); throw; }
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
  m.attr("legacy_method_id") = legacy_method_id;
  m.attr("pedestrian_method_id") = pedestrian_method_id;
  m.def("_core_grid_shape", &dtcc_qes::core_grid_shape);
  m.def("_resource_usage", &resource_record);
  m.def("_reset_resource_peaks", &reset_resource_peaks);

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
  m.def("_turbulence_reference", [](std::vector<float> heights,float roughness) {
    const auto value=turbulence_reference(std::move(heights),roughness);
    nb::dict out;out["mean_height"]=value.mean_height;out["maximum_height"]=value.maximum_height;
    out["reference_height"]=value.reference_height;out["roughness_length"]=value.roughness_length;
    out["displacement_height"]=value.displacement_height;return out;
  });
  m.def("_turbulence_extension", [](std::vector<float> faces,double reference,float thickness,
                                    int nx,int ny,std::int64_t max_cells) {
    const auto value=turbulence_extension(faces,reference,thickness,nx,ny,max_cells);
    nb::dict out;out["faces"]=value.faces;out["added_layers"]=value.added_layers;
    out["limit"]=value.limit;out["has_margin"]=turbulence_margin(faces,reference);
    out["reference_index"]=std::lower_bound(faces.begin(),faces.end(),reference)-faces.begin()+1;
    out["maximum_index"]=faces.size()-3;return out;
  });
  m.def("_pedestrian_input_exclusions", &pedestrian_input_exclusions,
        "kind"_a,"options"_a,"turbulence"_a,"threads"_a=nb::none());
  m.def("_pedestrian_preflight", [](const GridConfig &grid,const ModelSettings &model,
      const WindCondition &condition,const SolverOptions &options,nb::dict control,
      Vertices vertices,Integers offsets,Floats heights,Floats base_heights,Integers ids,
      Floats dz_layers,const TurbulenceSettings *turbulence,Integers ring_offsets,std::optional<int> threads) {
    GridConfig g=grid;if(dz_layers.is_valid())g.dz_layers=copy_input(dz_layers);
    const ModelSettings m=model;const WindCondition c=condition;const SolverOptions o=options;
    const auto t=turbulence?*turbulence:TurbulenceSettings{};
    const BuildingArrays b{copy_input(vertices),copy_input(offsets),copy_input(ids),copy_input(heights),
      copy_input(base_heights),ring_offsets.is_valid()?copy_input(ring_offsets):std::vector<std::int64_t>{}};
    const auto spec=control_binding::parse(control);
    const auto value=native_call([&](Messages &) {return pedestrian_preflight(g,m,b,t,c,o,spec.monitor,threads);});
    nb::dict out;out["exclusions"]=value.exclusions;out["pending_runtime_checks"]=value.pending_runtime_checks;return out;
  },"grid"_a,"model"_a,"condition"_a,"options"_a,"control"_a,
     nb::arg("vertices").noconvert(),nb::arg("offsets").noconvert(),nb::arg("heights").noconvert(),
     nb::arg("base_heights").noconvert(),nb::arg("ids").noconvert(),nb::kw_only(),
     nb::arg("dz_layers").noconvert().none()=nb::none(),nb::arg("turbulence").none()=nb::none(),
     nb::arg("ring_offsets").noconvert().none()=nb::none(),"threads"_a=nb::none());
  nb::class_<WindRunner>(m, "WindRunner")
    .def(nb::init<>())
    .def_prop_ro("_progress", &progress_record)
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
    .def("_solve_experiment", [](WindRunner &runner, const WindCondition &condition, const SolverOptions &options,
                                bool diagnose_flux, std::vector<std::array<int,3>> cells,
                                const std::string &canyon_model, bool canyon_capture,
                                bool canyon_baseline_turbulence, bool canyon_trace_roof) {
      CanyonOptions canyon;
      canyon.canyon_model = canyon_model_parse(canyon_model);
      canyon.canyon_capture = canyon_capture;
      canyon.canyon_trace_roof = canyon_trace_roof;
      canyon.canyon_baseline_turbulence = canyon_baseline_turbulence;
      canyon.diagnose_flux = diagnose_flux;
      canyon.cells = std::move(cells);
      const WindCondition wind = condition;
      const SolverOptions solver = options;
      return transfer_result(runner, native_call([&](Messages &messages) {
        return runner.solve(wind, solver, messages, nullptr, {}, &canyon);
      }));
    }, "condition"_a, "options"_a=SolverOptions{}, nb::kw_only(), "diagnose_flux"_a=false,
       "cells"_a=std::vector<std::array<int,3>>{}, "canyon_model"_a="legacy", "canyon_capture"_a=false,
       "canyon_baseline_turbulence"_a=false, "canyon_trace_roof"_a=false)
#ifdef DTCC_QES_CANYON_TEST_HOOKS
    .def("_test_canyon_failure", [](WindRunner& runner,const WindCondition& condition,const SolverOptions& options) {
      CanyonOptions e;e.canyon_model=CanyonModel::JoinedV1;e.test_canyon_failure=true;
      native_call([&](Messages& messages) { return runner.solve(condition,options,messages,nullptr,{},&e); });
    },"condition"_a,"options"_a)
#endif
    .def("solve", [](WindRunner &runner, const WindCondition &condition, const SolverOptions &options,
                     nb::object control,nb::object test_steps) {
      const WindCondition wind = condition;
      const SolverOptions solver = options;
      const auto settings = control.is_none() ? std::optional<SolverControl>{} : control_binding::parse(nb::cast<nb::dict>(control));
      std::function<double()> clock;
      if(!test_steps.is_none()) {
        if(!settings)throw std::invalid_argument("Test clock requires solver controls");
        auto steps=std::make_shared<std::vector<double>>(nb::cast<std::vector<double>>(test_steps));
        if(steps->empty() || !std::is_sorted(steps->begin(),steps->end()) ||
            std::any_of(steps->begin(),steps->end(),[](double v){return !std::isfinite(v);}))
          throw std::invalid_argument("Test clock steps must be nonempty, finite and monotonic");
        auto index=std::make_shared<std::size_t>(0);
        clock=[steps,index] {return (*steps)[std::min((*index)++,steps->size()-1)];};
      }
      try {
        return transfer_result(runner,native_call([&](Messages &messages) { return runner.solve(wind, solver, messages,settings ? &*settings : nullptr,clock); }));
      } catch (const BudgetExhausted &failure) {
        auto cls=nb::module_::import_("dtcc_qes.solver_control").attr("BudgetExhaustedError");
        auto error=cls(control_binding::encode(failure.record));
        PyErr_SetObject(cls.ptr(),error.ptr());throw nb::python_error();
      } catch (const NumericalFailure &failure) {
        auto cls=nb::module_::import_("dtcc_qes.solver_control").attr("NumericalFailureError");
        auto error=cls(control_binding::encode(failure.record));
        PyErr_SetObject(cls.ptr(),error.ptr());throw nb::python_error();
      }
    }, "condition"_a, "options"_a = SolverOptions{},nb::kw_only(),"control"_a=nb::none(),"_test_clock_steps"_a=nb::none());
}
