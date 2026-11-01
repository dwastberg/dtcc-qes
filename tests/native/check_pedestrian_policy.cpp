#include "pedestrian_policy.h"
#include "solver_control.h"
#include "wind_runner.h"
#include <iostream>
#include <stdexcept>
using namespace dtcc_qes;
static void require(bool v,const char *s){if(!v)throw std::runtime_error(s);}
static MonitorWindow window(int iteration,int span,std::size_t count=100) {
  MonitorWindow w;w.available=true;w.from_iteration=iteration-span;w.to_iteration=iteration;w.common_valid=count;
  const double factor=span==25?1:15;
  w.vector_over_uref={factor*1e-5,factor*2e-5};w.speed_factor_change=w.vector_over_uref;
  w.ratios={.5,.5,.5,.5};
  for(auto &h:w.hotspots){h.present=true;h.before.valid=h.current.valid=true;}
  return w;
}
static MonitorCheckpoint checkpoint(int iteration) {
  MonitorCheckpoint c;c.iteration=iteration;c.heights.resize(2);c.receptors.resize(2);
  for(auto &h:c.heights){h.points=h.valid=100;h.short_change=window(iteration,25);h.long_change=window(iteration,100);}
  for(auto &r:c.receptors){r.required=true;r.sample.valid=true;r.short_change=window(iteration,25,1);r.long_change=window(iteration,100,1);}
  return c;
}
static PolicyEvidence evaluate(PedestrianDecision &p,MonitorCheckpoint c,bool safe=true) {return p.evaluate(c,1e-5,1e-6,100,safe,1e-5,1e-6);}
static MonitorCheckpoint plateau(int i) {
  auto c=checkpoint(i);
  for(auto &h:c.heights) {
    h.short_change.ratios=h.long_change.ratios={1.,1.,1.,1.};
    h.short_change.vector_over_uref={1e-7,1e-7};h.short_change.speed_factor_change=h.short_change.vector_over_uref;
  }
  return c;
}
int main() try {
  auto c=checkpoint(150);auto p=predict_pedestrian(c);
  require(p.available && prediction_meets_target(p),"Geometric prediction unavailable");
  require(std::abs(*p.vector_maximum-1.6e-4)<1e-15,"Tail calculation wrong");
  c.initial=true;require(!predict_pedestrian(c).available,"Initial state accepted");
  c=plateau(150);require(!predict_pedestrian(c).available,"Plateau interpreted as zero error");
  PedestrianDecision decision;
  require(!evaluate(decision,checkpoint(150)).ready,"One checkpoint accepted");
  auto b=evaluate(decision,plateau(175));
  require(b.prediction.available && !b.prediction.fresh_tail_available
      && b.prediction.reason=="transported_anchor" && *b.prediction.vector_maximum>1.6e-4,"Anchor discarded or made zero");
  b=evaluate(decision,plateau(200));require(b.ready && !b.accepted,"Policy bypasses deadline commit or loses streak");
  for(int i:{225,250,275})b=evaluate(decision,plateau(i));
  require(!b.prediction.available && !b.ready,"Expired anchor accepted");
  PedestrianDecision invalid;evaluate(invalid,checkpoint(150));c=plateau(175);c.receptors[0].sample.valid=false;c.required_receptors_valid=false;
  require(!evaluate(invalid,c).prediction.available,"Invalid required support accepted");
  PedestrianDecision unsafe;for(int i:{150,175,200})b=evaluate(unsafe,checkpoint(i),false);
  require(!b.ready,"Safeguards bypassed");
  PedestrianDecision stagnant;for(int i=400;i<=500;i+=25)b=evaluate(stagnant,plateau(i));
  require(stagnant.stagnated(),"Plateau termination unavailable");

  GridConfig g;g.nx=g.ny=80;g.nz=32;g.max_cells=300000;
  ModelSettings m;BuildingArrays buildings;buildings.offsets={0};
  for(const auto a: {std::array<float,3>{22,22,7.9f},{42,22,7.9f},{22,42,7.9f},{42,42,23.7f}}) {
    double x=a[0],y=a[1];for(auto xy:{std::array<double,2>{x,y},{x,y+12},{x+12,y+12},{x+12,y},{x,y}}){buildings.vertices.push_back(xy[0]);buildings.vertices.push_back(xy[1]);}
    buildings.offsets.push_back(buildings.vertices.size()/2);buildings.heights.push_back(a[2]);buildings.base_heights.push_back(0);buildings.ids.push_back(buildings.ids.size());
  }
  SolverControl settings;settings.mode="adaptive";settings.policy=pedestrian_policy_id;settings.max_solve_seconds=10;
  settings.monitor.region={0,80,0,80};settings.monitor.history_limit=5;
  for(double h:{1.5,1.75})settings.monitor.receptors.push_back({std::to_string(h),{27,21,h},true});
  SolverOptions opts;opts.max_iterations=600;opts.tolerance=.1;
  const auto check_scope=[&](GridConfig grid,ModelSettings model,BuildingArrays arrays,
      WindCondition condition,SolverOptions options,TurbulenceSettings turb,MonitorSpec monitor,int threads) {
    ModelInputs inputs(grid,model,arrays,turb);inputs.set_condition(condition);
    const auto all=pedestrian_exclusions(grid,model,inputs,options,monitor,threads);
    const auto first=pedestrian_scope(grid,model,inputs,options,monitor,threads);
    require(first==(all.empty()?"":all.front()),"First exclusion changed its legacy decision");
    const auto queried=pedestrian_preflight(grid,model,arrays,turb,condition,options,monitor,threads);
    require(queried.exclusions==all && queried.pending_runtime_checks.empty(),"Preflight/runtime narrowing disagrees");
    auto unique=all;std::sort(unique.begin(),unique.end());
    require(std::adjacent_find(unique.begin(),unique.end())==unique.end(),"Repeated exclusion reason");
    return all;
  };
  for(int team:{1,2,4,8})for(const auto *precision:{"float32","float64"})for(bool turbulence:{false,true}) {
    auto options=opts;options.precision=precision;
    const auto reasons=check_scope(g,m,buildings,{5,270,10},options,{turbulence,0},settings.monitor,team);
    if(team==8)require(std::find(reasons.begin(),reasons.end(),"unqualified_thread_team")!=reasons.end(),"Thread exclusion omitted");
    if(turbulence)require(std::find(reasons.begin(),reasons.end(),"turbulence_outside_assessment_scope")!=reasons.end(),"Turbulence exclusion omitted");
    if(std::string(precision)=="float64")require(std::find(reasons.begin(),reasons.end(),"unqualified_precision")!=reasons.end(),"Precision exclusion omitted");
  }
  auto altered=g;altered.cell_size=4;altered.nx=20;
  const auto grid_reasons=check_scope(altered,m,buildings,{5,270,10},opts,{},settings.monitor,2);
  require(std::find(grid_reasons.begin(),grid_reasons.end(),"unqualified_grid")!=grid_reasons.end(),"Grid exclusion omitted");
  require(std::find(grid_reasons.begin(),grid_reasons.end(),"unqualified_geometry")==grid_reasons.end(),"2m clearance check ran on an unqualified grid");
  auto no_receptors=settings.monitor;no_receptors.receptors.clear();
  const auto support=check_scope(g,m,buildings,{5,270,10},opts,{},no_receptors,2);
  require(std::find(support.begin(),support.end(),"required_receptors_at_both_heights")!=support.end(),"Required height exclusion omitted");
  Messages messages;WindRunner runner;runner.prepare(g,m,buildings,messages);
  const auto expected=runner.solve({5,270,10},opts,messages);
  const auto actual=runner.solve({5,270,10},opts,messages,&settings,[]{return 0.;});
  if(policy_build_supported()) {
    require(actual.control->accepted && actual.control->termination_reason=="accepted","Online policy failed its tower case");
    require(actual.iterations>=200 && actual.iterations>expected.iterations,"Adaptive policy stopped on legacy tolerance");
    require(actual.control->assessment->iteration==actual.iterations && actual.control->assessment->accepted,"Stale or uncommitted acceptance");
    require(actual.control->assessment_history.size()==5,"Policy history unbounded");
    require(actual.control->monitor_bytes<settings.monitor.memory_limit_bytes,"Policy memory cap exceeded");
    // Repeat the same deterministic clock sequence and expire only at final
    // acceptance commit, after every mathematical gate was satisfied.
    int calls=0;runner.solve({5,270,10},opts,messages,&settings,[&]{++calls;return 0.;});
    const int expire=calls-5;int ticks=0;
    const auto timed=runner.solve({5,270,10},opts,messages,&settings,[&]{return ++ticks>=expire?20.:0.;});
    require(!timed.control->accepted && timed.control->termination_reason=="time_limit","Deadline lost precedence");
  } else require(actual.control->accuracy_status=="not_assessed","Unqualified build accepted");
  const auto again=runner.solve({5,270,10},opts,messages);
  require(again.velocity==expected.velocity && again.iterations==expected.iterations,"Adaptive method poisoned default reuse");
  WindCondition table{5,270,10};table.profile_kind=ProfileKind::LayerTable;
  table.layer_u.assign(g.nz,5);table.layer_v.assign(g.nz,0);
  const auto tabulated=runner.solve(table,opts,messages,&settings,[]{return 0.;});
  require(!tabulated.control->accepted && tabulated.control->accuracy_status=="not_assessed",
          "Experimental inflow inherited log-profile qualification");
  if(policy_build_supported())
    require(tabulated.control->assessment_reason=="unqualified_inflow_profile",
            "Experimental inflow missing its scope reason");
  g.nx=96;runner.prepare(g,m,buildings,messages);
  const auto outside=runner.solve({5,270,10},opts,messages,&settings,[]{return 0.;});
  require(!outside.control->accepted && outside.control->accuracy_status=="not_assessed","Unqualified domain accepted");
  std::cout<<"Predictions, nonzero anchors, expiration, support, safeguards, native acceptance, deadlines and method reset passed\n";
  return 0;
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
