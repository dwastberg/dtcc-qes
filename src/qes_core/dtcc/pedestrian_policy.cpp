#include "pedestrian_policy.h"
#include "api/build_info.h"
#include "pedestrian_qualification.h"
#include <cstring>
#include <limits>

namespace dtcc_qes {
bool policy_build_supported() {
#if defined(__apple_build_version__) && defined(__aarch64__) && __clang_major__ == 17
  return std::strcmp(fp_contract(),"on")==0 && std::strcmp(solver_policy_revision(),pedestrian_qualified_revision)==0;
#else
  return false;
#endif
}
std::vector<std::string> pedestrian_input_exclusions(ProfileKind kind,const SolverOptions &options,
                                                       bool turbulence,std::optional<int> threads) {
  std::vector<std::string> reasons;
  if(!policy_build_supported())reasons.push_back("unqualified_build");
  if(kind!=ProfileKind::Log)reasons.push_back("unqualified_inflow_profile");
  if(threads && (*threads<1 || *threads>4))reasons.push_back("unqualified_thread_team");
  if(options.precision!="float32")reasons.push_back("unqualified_precision");
  if(turbulence)reasons.push_back("turbulence_outside_assessment_scope");
  return reasons;
}
std::vector<std::string> pedestrian_exclusions(const GridConfig &g,const ModelSettings &m,const ModelInputs &in,
                                               const SolverOptions &options,const MonitorSpec &s,std::optional<int> threads) {
  auto reasons=pedestrian_input_exclusions(in.inflow.profile_kind,options,in.turbulence_enabled,threads);
  const auto add=[&](const char *reason) {
    if(std::find(reasons.begin(),reasons.end(),reason)==reasons.end())reasons.emplace_back(reason);
  };
  const bool grid_ok=in.spacing==2 && g.nx==80 && g.ny==80 && g.nz==32;
  if(!grid_ok)add("unqualified_grid");
  if(!in.layers.empty()) {
    bool uniform=true,graded=true;
    for(std::size_t k=0;k<in.layers.size();++k) {
      uniform &= in.layers[k]==2;
      graded &= std::abs(double(in.layers[k])-1.2*std::pow(1.03,double(k)))<=2e-5;
    }
    if(!uniform && !graded)add("unqualified_vertical_profile");
  }
  if(in.inflow.profile_kind==ProfileKind::Log && (in.inflow.site_U_ref<2 || in.inflow.site_U_ref>10
      || in.inflow.site_z_ref!=10 || in.inflow.site_z0!=.1f))add("unqualified_inflow");
  if(m.rooftop_flag!=1 || m.upwind_cavity_flag!=2 || m.street_canyon_flag!=1
      || m.street_intersection_flag!=0 || m.wake_flag!=2 || m.high_rise_flag!=0
      || m.sidewall_flag!=1 || float(m.wall_roughness)!=.001f)add("unqualified_model_settings");
  if(in.buildings.size()<4 || in.buildings.size()>32)add("unqualified_geometry");
  for(const auto &b:in.buildings) {
    if(b.height<4 || b.height>24 || b.base_height!=0 || b.vertices.size()!=5) {
      add("unqualified_geometry");continue;
    }
    float xmin=b.vertices[0].x_poly,xmax=xmin,ymin=b.vertices[0].y_poly,ymax=ymin;
    for(const auto &v:b.vertices){xmin=std::min(xmin,v.x_poly);xmax=std::max(xmax,v.x_poly);ymin=std::min(ymin,v.y_poly);ymax=std::max(ymax,v.y_poly);}
    if(xmax-xmin<8 || xmax-xmin>16 || ymax-ymin<8 || ymax-ymin>16
        || (grid_ok && (xmin<12 || ymin<12 || xmax>g.nx*2-12 || ymax>g.ny*2-12)))add("unqualified_geometry");
    unsigned corners=0;
    for(int i=0;i<4;++i) {
      const auto &a=b.vertices[i],&z=b.vertices[i+1];
      if((a.x_poly!=xmin && a.x_poly!=xmax) || (a.y_poly!=ymin && a.y_poly!=ymax)
          || ((a.x_poly==z.x_poly)==(a.y_poly==z.y_poly)))add("unqualified_geometry");
      corners |= 1u<<((a.x_poly==xmax?1:0)+(a.y_poly==ymax?2:0));
    }
    if(corners!=15)add("unqualified_geometry");
  }
  if(s.heights!=std::vector<double>{1.5,1.75} || s.region.x_last-s.region.x_first<20
      || s.region.y_last-s.region.y_first<20 || s.receptors.size()>16)add("unqualified_observables");
  bool first=false,second=false;
  for(const auto &r:s.receptors)if(r.required) {
    if(r.location.x<s.region.x_first+2 || r.location.x>s.region.x_last-2
        || r.location.y<s.region.y_first+2 || r.location.y>s.region.y_last-2)add("receptor_outside_roi_support");
    if(r.location.height_agl==1.5)first=true;
    else if(r.location.height_agl==1.75)second=true;
    else add("unqualified_observables");
  }
  if(!first || !second)add("required_receptors_at_both_heights");
  return reasons;
}
std::string pedestrian_scope(const GridConfig &g,const ModelSettings &m,const ModelInputs &in,
                             const SolverOptions &options,const MonitorSpec &s,int threads) {
  const auto reasons=pedestrian_exclusions(g,m,in,options,s,threads);
  return reasons.empty()?"":reasons.front();
}
PolicyEligibility pedestrian_preflight(const GridConfig &g,const ModelSettings &m,const BuildingArrays &arrays,
    const TurbulenceSettings &t,const WindCondition &condition,const SolverOptions &options,
    const MonitorSpec &monitor,std::optional<int> threads) {
  // The same coordinate-only constructor and set_condition perform every
  // float32 conversion for runtime preparation and this query without allocating 3D fields.
  ModelInputs inputs(g,m,arrays,t);
  inputs.set_condition(condition);
  solver_tolerance(options);
  PolicyEligibility out{pedestrian_exclusions(g,m,inputs,options,monitor,threads),{}};
  if(!threads)out.pending_runtime_checks.push_back("actual_thread_team");
  return out;
}
namespace {
struct Estimate {std::optional<double> value;double q0=0,q1=0;};
Estimate tail(const MonitorWindow &s,const MonitorWindow &l,int metric,int iteration) {
  if(!s.available || !l.available || s.validity_changes || l.validity_changes
      || !s.common_valid || s.common_valid!=l.common_valid || s.to_iteration!=iteration || l.to_iteration!=iteration
      || s.to_iteration-s.from_iteration!=25 || l.to_iteration-l.from_iteration!=100)return {};
  const auto &sn=metric<2?s.vector_over_uref:s.speed_factor_change;
  const auto &ln=metric<2?l.vector_over_uref:l.speed_factor_change;
  const auto ds=metric%2?sn.maximum:sn.p95,dl=metric%2?ln.maximum:ln.p95;
  const std::optional<double> sr[]={s.ratios.vector_p95,s.ratios.vector_max,s.ratios.speed_p95,s.ratios.speed_max};
  const std::optional<double> lr[]={l.ratios.vector_p95,l.ratios.vector_max,l.ratios.speed_p95,l.ratios.speed_max};
  const auto a=sr[metric],b=lr[metric];
  for(const auto &x:{ds,dl,a,b})if(!x || !std::isfinite(*x) || *x<=0)return {};
  const double q=std::max(*a,*b),low=std::min(*a,*b);
  if(low<.02 || q>=policy_maximum_ratio || q>4*low)return {};
  const double q4=q*q*q*q;
  const double result=policy_safety_factor*std::max(*ds*q/(1-q),*dl*q4/(1-q4));
  if(!std::isfinite(result))return {};
  return {result,*a,*b};
}
}
PolicyPrediction predict_pedestrian(const MonitorCheckpoint &c) {
  PolicyPrediction out;
  if(c.initial || c.iteration<policy_minimum_iterations)return out;
  if(!c.required_receptors_valid || c.heights.size()!=2
      || std::any_of(c.heights.begin(),c.heights.end(),[](const auto &h){return h.valid<16;})){
    out.reason="invalid_support";return out;
  }
  double bounds[4]={},required=0,hotspot=0,qmin=1,qmax=0;
  const auto collect=[&](const Estimate &e) {
    qmin=std::min({qmin,e.q0,e.q1});qmax=std::max({qmax,e.q0,e.q1});
  };
  for(const auto &h:c.heights) {
    for(int n=0;n<4;++n) {
      const auto e=tail(h.short_change,h.long_change,n,c.iteration);
      if(!e.value){out.reason="unstable_or_plateaued_tail";return out;}
      collect(e);bounds[n]=std::max(bounds[n],*e.value);
    }
    for(const auto *window:{&h.short_change,&h.long_change})for(const auto &peak:window->hotspots)
      if(!peak.present || !peak.before.valid || !peak.current.valid){out.reason="invalid_hotspot";return out;}
    hotspot=std::max({hotspot,bounds[1],bounds[3]});
  }
  int required_count=0;
  for(const auto &r:c.receptors)if(r.required) {
    ++required_count;
    if(!r.sample.valid || !r.short_change.available || !r.long_change.available
        || r.short_change.validity_changes || r.long_change.validity_changes
        || r.short_change.common_valid!=1 || r.long_change.common_valid!=1){out.reason="unavailable_required_support";return out;}
    // Eligibility requires each required receptor's interpolation support to
    // lie inside the ROI. Nonnegative bilinear weights preserve a uniform
    // spatial maximum bound, even if this individual point has no decay ratio.
    required=std::max({required,bounds[1],bounds[3]});
  }
  if(!required_count){out.reason="invalid_support";return out;}
  out.available=true;out.reason="predicted";
  out.vector_p95=bounds[0];out.vector_maximum=bounds[1];out.speed_p95=bounds[2];out.speed_maximum=bounds[3];
  out.required_maximum=required;out.hotspot_maximum=hotspot;out.q_minimum=qmin;out.q_maximum=qmax;
  return out;
}
bool prediction_meets_target(const PolicyPrediction &p) {
  const auto within=[](std::optional<double> x,double limit){return x && std::isfinite(*x) && *x>=0 && *x<=limit;};
  return p.available && within(p.vector_p95,policy_vector_p95) && within(p.vector_maximum,policy_vector_maximum)
    && within(p.speed_p95,policy_vector_p95) && within(p.speed_maximum,policy_vector_maximum)
    && within(p.required_maximum,policy_vector_maximum) && within(p.hotspot_maximum,policy_vector_maximum);
}
PolicyEvidence PedestrianDecision::evaluate(const MonitorCheckpoint &c,double residual_max,double residual_rms,
    std::size_t cells,bool safeguards,double mass_max,double mass_rms) {
  PolicyEvidence e;e.iteration=c.iteration;e.prediction=predict_pedestrian(c);
  const auto fresh=e.prediction;
  bool stable=c.required_receptors_valid;double vector_drift=0,speed_drift=0;
  const auto drift=[&](const MonitorWindow &w) {
    const auto v=w.vector_over_uref.maximum,k=w.speed_factor_change.maximum;
    stable &= w.available && !w.validity_changes && w.common_valid>0 && v && k
      && std::isfinite(v.value_or(-1)) && std::isfinite(k.value_or(-1));
    if(v && k){vector_drift=std::max(vector_drift,*v);speed_drift=std::max(speed_drift,*k);}
  };
  for(const auto &h:c.heights)drift(h.short_change);
  for(const auto &r:c.receptors)if(r.required)drift(r.short_change);
  if(anchor_) {
    if(!stable || previous_iteration_<0 || c.iteration-previous_iteration_!=25 || c.iteration-anchor_->iteration>100)anchor_.reset();
    else {anchor_->vector+=vector_drift;anchor_->speed+=speed_drift;}
  }
  if(fresh.available && (!anchor_ || std::max(*fresh.vector_maximum,*fresh.speed_maximum)<=std::max(anchor_->vector,anchor_->speed)))
    anchor_=Anchor{c.iteration,*fresh.vector_maximum,*fresh.speed_maximum,*fresh.q_minimum,*fresh.q_maximum};
  if(anchor_ && anchor_->iteration!=c.iteration) {
    auto &p=e.prediction;p.available=true;p.reason="transported_anchor";
    p.vector_p95=p.vector_maximum=anchor_->vector;p.speed_p95=p.speed_maximum=anchor_->speed;
    p.required_maximum=p.hotspot_maximum=std::max(anchor_->vector,anchor_->speed);
    p.q_minimum=anchor_->qmin;p.q_maximum=anchor_->qmax;
  }
  e.prediction.fresh_tail_available=fresh.available;e.prediction.current_tail_reason=fresh.reason;
  if(anchor_)e.prediction.anchor_iteration=anchor_->iteration;
  previous_iteration_=c.iteration;
  e.relative_residual_maximum=residual_max;e.relative_residual_rms=residual_rms;e.residual_cells=cells;
  e.scaled_mass_maximum=mass_max;e.scaled_mass_rms=mass_rms;e.mass_regions=c.mass.size();
  e.safeguards_passed=safeguards;e.candidate=safeguards && prediction_meets_target(e.prediction);
  consecutive_=e.candidate?consecutive_+1:0;e.consecutive=consecutive_;e.ready=consecutive_>=3;
  if(c.iteration>=400 && previous_residual_>0 && residual_rms>0 && residual_rms<5e-5
      && std::abs(residual_rms/previous_residual_-1)<.02)++stagnation_;else stagnation_=0;
  previous_residual_=residual_rms;
  return e;
}
}
