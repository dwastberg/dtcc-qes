#pragma once
#include "control_types.h"
#include <nanobind/stl/vector.h>
#include <nanobind/stl/optional.h>
#include <cmath>
#include <algorithm>

namespace control_binding {
namespace nb = nanobind;
using namespace dtcc_qes;
inline void keys(nb::dict d,std::initializer_list<const char *> allowed) {
  for (auto item : d) {
    const auto name=nb::cast<std::string>(item.first);
    if (std::none_of(allowed.begin(),allowed.end(),[&](const char *a) {return name==a;}))
      throw std::invalid_argument("Unknown solver control field: "+name);
  }
}
template<class T> void read(nb::dict d,const char *name,T &out) {if(d.contains(name)) out=nb::cast<T>(d[name]);}
inline SolverControl parse(nb::dict d) {
  keys(d,{"mode","policy","max_solve_seconds","checkpoint_interval","residual_interval","monitor"});
  SolverControl c;read(d,"mode",c.mode);read(d,"max_solve_seconds",c.max_solve_seconds);
  read(d,"checkpoint_interval",c.checkpoint_interval);read(d,"residual_interval",c.residual_interval);
  if(d.contains("policy") && !d["policy"].is_none())read(d,"policy",c.policy);
  if (!d.contains("monitor")) throw std::invalid_argument("Solver controls require an explicit monitor");
  auto m=nb::cast<nb::dict>(d["monitor"]);
  keys(m,{"region","heights","receptors","frame","origin","crs","short_window","long_window","history_limit",
          "memory_limit_bytes","global_mass","mass_regions","low_flow_fraction"});
  if(!m.contains("region")) throw std::invalid_argument("Monitor requires an explicit region");
  const auto r=nb::cast<std::array<double,4>>(m["region"]);c.monitor.region={r[0],r[1],r[2],r[3]};
  auto &s=c.monitor;std::string frame="local";read(m,"frame",frame);
  if(frame!="local" && frame!="world") throw std::invalid_argument("Unknown monitor frame");
  s.frame=frame=="local" ? MonitorFrame::Local : MonitorFrame::World;
  read(m,"heights",s.heights);read(m,"origin",s.origin);read(m,"crs",s.crs);
  read(m,"short_window",s.short_window);read(m,"long_window",s.long_window);read(m,"history_limit",s.history_limit);
  read(m,"memory_limit_bytes",s.memory_limit_bytes);read(m,"global_mass",s.global_mass);read(m,"low_flow_fraction",s.low_flow_fraction);
  if(m.contains("receptors")) for(auto value : nb::cast<nb::list>(m["receptors"])) {
    auto q=nb::cast<nb::dict>(value);keys(q,{"id","x","y","height_agl","required"});MonitorReceptor r;
    r.id=nb::cast<std::string>(q["id"]);r.location={nb::cast<double>(q["x"]),nb::cast<double>(q["y"]),nb::cast<double>(q["height_agl"])};
    read(q,"required",r.required);s.receptors.push_back(r);
  }
  if(m.contains("mass_regions")) for(auto value : nb::cast<nb::list>(m["mass_regions"])) {
    auto q=nb::cast<nb::dict>(value);keys(q,{"name","i_first","i_last","j_first","j_last","k_first","k_last"});MonitorCellRegion r;
    read(q,"name",r.name);read(q,"i_first",r.i_first);read(q,"i_last",r.i_last);read(q,"j_first",r.j_first);
    read(q,"j_last",r.j_last);read(q,"k_first",r.k_first);read(q,"k_last",r.k_last);s.mass_regions.push_back(r);
  }
  return c;
}
template<class T> nb::object scalar(const T &v) {return nb::cast(v);}
inline nb::object scalar(double v) {return std::isfinite(v) ? nb::cast(v) : nb::none();}
inline nb::dict encode(const MonitorLocation &v);
inline nb::dict encode(const MonitorNorm &v);
inline nb::dict encode(const MonitorRatios &v);
inline nb::dict encode(const MonitorSample &v);
inline nb::dict encode(const MonitorPeak &v);
inline nb::dict encode(const MonitorHotspot &v);
inline nb::dict encode(const MonitorWindow &v);
inline nb::dict encode(const MonitorHeightRecord &v);
inline nb::dict encode(const MonitorReceptorRecord &v);
inline nb::dict encode(const MonitorFlux &v);
inline nb::dict encode(const DivergenceStats &v);
inline nb::dict encode(const MonitorMassRecord &v);
inline nb::dict encode(const MonitorResidualTrend &v);
inline nb::dict encode(const MonitorCheckpoint &v);
inline nb::dict encode(const ControlRegion &v);
inline nb::dict encode(const PolicyPrediction &v);
inline nb::dict encode(const PolicyEvidence &v);
template<class T> nb::list records(const T &values) {nb::list out;for(const auto &v:values)out.append(encode(v));return out;}
#define F(name) d[#name]=scalar(v.name)
#define E(name) d[#name]=encode(v.name)
inline nb::dict encode(const MonitorLocation &v) {nb::dict d;F(x);F(y);F(height_agl);return d;}
inline nb::dict encode(const MonitorNorm &v) {nb::dict d;F(p95);F(maximum);return d;}
inline nb::dict encode(const MonitorRatios &v) {nb::dict d;F(vector_p95);F(vector_max);F(speed_p95);F(speed_max);return d;}
inline nb::dict encode(const MonitorSample &v) {nb::dict d;F(valid);nb::list a;for(double x:v.velocity)a.append(scalar(x));d["velocity"]=a;return d;}
inline nb::dict encode(const MonitorPeak &v) {nb::dict d;F(valid);F(point);E(location);F(speed);F(speed_factor);return d;}
inline nb::dict encode(const MonitorHotspot &v) {nb::dict d;F(present);F(point);E(location);E(before);E(current);F(vector_change);F(speed_change);return d;}
inline nb::dict encode(const MonitorWindow &v) {
  nb::dict d;F(available);F(from_iteration);F(to_iteration);F(common_valid);F(validity_changes);
  E(vector_change);E(speed_change);E(vector_over_uref);E(speed_factor_change);E(ratios);d["hotspots"]=records(v.hotspots);return d;
}
inline nb::dict encode(const MonitorHeightRecord &v) {nb::dict d;F(height_agl);F(points);F(valid);E(peak);E(short_change);E(long_change);return d;}
inline nb::dict encode(const MonitorReceptorRecord &v) {nb::dict d;F(receptor);F(required);E(location);E(sample);F(speed);F(speed_factor);E(short_change);E(long_change);return d;}
inline nb::dict encode(const MonitorFlux &v) {
  nb::dict d;F(net_cell_flux);F(boundary_flux);F(absolute_cell_flux);F(throughflow);F(low_flow_cells);F(resolved_cells);F(unassessed_cells);F(relative_max);F(relative_rms);return d;
}
inline nb::dict encode(const DivergenceStats &v) {nb::dict d;F(interior_max);F(interior_rms);F(top_band_max);F(cells);F(top_band_cells);return d;}
inline nb::dict encode(const MonitorMassRecord &v) {nb::dict d;F(region);E(divergence);E(interior);E(top_band);return d;}
inline nb::dict encode(const MonitorResidualTrend &v) {nb::dict d;F(iteration);F(maximum);F(volume_weighted_rms);F(fluid_cells);return d;}
inline nb::dict encode(const MonitorCheckpoint &v) {
  nb::dict d;F(iteration);F(initial);F(required_receptors_valid);F(elapsed_seconds);
  d["heights"]=records(v.heights);d["receptors"]=records(v.receptors);d["mass"]=records(v.mass);
  d["residual_trend"]=v.residual_trend ? nb::object(encode(*v.residual_trend)) : nb::none();return d;
}
inline nb::dict encode(const ControlRegion &v) {nb::dict d;F(name);F(bounds);F(excluded_lateral_cells);F(excluded_highest_cells);return d;}
inline nb::dict encode(const PolicyPrediction &v) {
  nb::dict d;F(available);F(reason);F(current_tail_reason);F(fresh_tail_available);F(anchor_iteration);
  F(vector_p95);F(vector_maximum);F(speed_p95);F(speed_maximum);F(required_maximum);F(hotspot_maximum);F(q_minimum);F(q_maximum);return d;
}
inline nb::dict encode(const PolicyEvidence &v) {
  nb::dict d;F(iteration);F(consecutive);F(safeguards_passed);F(candidate);F(ready);F(accepted);E(prediction);
  F(relative_residual_maximum);F(relative_residual_rms);F(scaled_mass_maximum);F(scaled_mass_rms);F(residual_cells);F(mass_regions);return d;
}
inline nb::dict encode(const MonitorSpec &v) {
  nb::dict d;d["region"]=nb::make_tuple(v.region.x_first,v.region.x_last,v.region.y_first,v.region.y_last);
  F(heights);F(origin);F(crs);F(reference_speed);F(short_window);F(long_window);F(history_limit);F(memory_limit_bytes);F(global_mass);F(low_flow_fraction);
  d["frame"]=v.frame==MonitorFrame::Local ? "local" : "world";
  nb::list receptors;
  for(const auto &r:v.receptors) {auto q=encode(r.location);q["id"]=r.id;q["required"]=r.required;receptors.append(q);}
  d["receptors"]=receptors;
  nb::list regions;for(const auto &r:v.mass_regions) {
    nb::dict q;q["name"]=r.name;q["bounds"]=nb::make_tuple(r.i_first,r.i_last,r.j_first,r.j_last,r.k_first,r.k_last);regions.append(q);
  }
  d["mass_regions"]=regions;return d;
}
inline nb::dict encode(const ControlTimings &t) {
  nb::dict timings;
#define T(name) timings[#name]=t.name
  T(preparation_seconds);T(mutex_wait_seconds);T(initialization_seconds);T(workspace_seconds);T(rhs_seconds);T(sweeps_seconds);T(monitoring_seconds);
  T(finalization_seconds);T(postprocessing_seconds);T(output_transfer_seconds);T(solve_seconds);T(native_total_seconds);T(deadline_overshoot_seconds);
#undef T
  return timings;
}
inline nb::dict encode(const ControlRecord &v) {
  nb::dict d;F(mode);F(termination_reason);F(accuracy_status);F(phase);F(iterations);F(actual_threads);
  F(policy);F(method);F(policy_revision);F(assessment_scope);F(assessment_reason);F(exclusions);F(accepted);F(assessment_count);
  d["assessment"]=v.assessment?nb::object(encode(*v.assessment)):nb::none();
  d["assessment_history"]=records(v.assessment_history);
  if(!v.policy.empty()) {
    nb::dict p;p["safety_factor"]=policy_safety_factor;p["minimum_iterations"]=policy_minimum_iterations;
    p["maximum_ratio"]=policy_maximum_ratio;p["anchor_maximum_sweeps"]=100;p["consecutive_checkpoints"]=3;
    p["vector_p95"]=policy_vector_p95;p["vector_maximum"]=policy_vector_maximum;
    p["speed_p95"]=policy_vector_p95;p["speed_maximum"]=policy_vector_maximum;
    p["mass_length_m"]=policy_mass_length;p["scaled_mass_maximum"]=policy_mass_maximum;p["scaled_mass_rms"]=policy_mass_rms;
    p["relative_residual_maximum"]=policy_residual_maximum;p["relative_residual_rms"]=policy_residual_rms;
    d["policy_parameters"]=p;
  }
  F(legacy_tolerance_satisfied);F(history_truncated);F(checkpoint_count);F(monitor_bytes);
  d["regions"]=records(v.regions);d["checkpoint_history"]=records(v.checkpoint_history);
  d["monitor"]=encode(v.effective_monitor);
  nb::dict requested;requested["max_solve_seconds"]=v.requested.max_solve_seconds;requested["checkpoint_interval"]=v.requested.checkpoint_interval;
  requested["residual_interval"]=v.requested.residual_interval;d["requested"]=requested;
  requested["policy"]=v.requested.policy.empty()?nb::none():nb::cast(v.requested.policy);
  d["timings"]=encode(v.timings);return d;
}

#undef F
#undef E
}
