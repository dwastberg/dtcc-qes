#include "wind_runner.h"
#include "solver_control.h"
#include <cmath>
#include <set>
#include <stdexcept>
#include <iostream>
using namespace dtcc_qes;
static void require(bool v,const char *message) {if(!v) throw std::runtime_error(message);}
int main() try {
  GridConfig grid;grid.nx=18;grid.ny=16;grid.nz=14;
  BuildingArrays geometry{{12,12,12,18,18,18,18,12,12,12},{0,5},{0},{6},{0}};
  ModelSettings model;model.sensor_x=model.sensor_y=3;
  Messages messages;WindRunner runner;runner.prepare(grid,model,geometry,messages);
  SolverOptions options;options.max_iterations=3;
  SolverControl settings;settings.max_solve_seconds=1;settings.checkpoint_interval=1;
  settings.monitor.region={0,36,0,32};settings.monitor.history_limit=3;
  std::set<std::string> phases;bool late_converged=false,output_overrun=false;
  for(const auto *precision : {"float32","float64"}) {
    options.precision=precision;
    const auto expected=runner.solve({5,33,10},options,messages);
    const auto actual=runner.solve({5,33,10},options,messages,&settings,[] {return 0.;});
    require(actual.control && actual.control->termination_reason=="iteration_limit" && actual.control->iterations==3,
            "Bounded accounting/iteration termination failed");
    require(actual.velocity==expected.velocity && actual.cell_flags==expected.cell_flags && actual.iterations==expected.iterations,
            "Controls changed the fixed completed-work field");
    require(actual.control->checkpoint_history.size()==3 && actual.control->history_truncated
            && actual.control->checkpoint_count==4,"Controller history is not bounded");
    for(int trip=2;trip<=100;++trip) {
      int ticks=0;
      try {
        const auto r=runner.solve({5,33,10},options,messages,&settings,[&] {return ++ticks>=trip ? 2. : 0.;});
        require(r.iterations>=1 && r.iterations<=3,"Partial sweep counted or initial output returned");
        require(r.control->accuracy_status=="not_assessed","Bounded run claims accuracy acceptance");
        if(r.control->termination_reason=="time_limit") phases.insert(r.control->phase);
        else if(r.control->timings.native_total_seconds>1) output_overrun=true;
      } catch(const BudgetExhausted &e) {
        require(e.record.iterations==0 && e.record.termination_reason=="time_limit","Zero-work error lost its evidence");
        phases.insert(e.record.phase);
      }
    }
    const auto calm=runner.solve({0,270,10},options,messages,&settings,[] {return 0.;});
    require(calm.converged && calm.control->termination_reason=="legacy_tolerance" && calm.iterations==1,
            "Legacy convergence semantics changed");
    for(int trip=2;trip<55;++trip) {
      int ticks=0;
      try {const auto r=runner.solve({0,270,10},options,messages,&settings,[&] {return ++ticks>=trip ? 2.:0.;});
        late_converged |= r.converged && r.control->termination_reason=="time_limit";
      } catch(const BudgetExhausted &) {}
    }
  }
  for(const auto *phase : {"mutex_wait","before_initialization","after_initialization","before_rhs","after_rhs",
      "before_monitor_compile","after_monitor_compile","after_initial_checkpoint","before_sweep","after_sweep",
      "before_checkpoint","after_checkpoint","before_finalization"})
    require(phases.count(phase),phase);
  require(late_converged,"Deadline failed to take precedence over a simultaneous legacy success");
  require(output_overrun,"Output overhead was included in the cooperative solve deadline");
  settings.mode="adaptive";bool rejected=false;
  try {runner.solve({5,33,10},options,messages,&settings);} catch(const std::exception &) {rejected=true;}
  require(rejected,"Unvalidated adaptive controls accepted");
  const auto retry=runner.solve({5,33,10},options,messages);
  require(retry.iterations==3 && !retry.control,"Failed controlled run poisoned the legacy retry");
  std::cout<<"Deadline phase boundaries, precedence, histories, output scope and trajectory checks passed\n";
  return 0;
} catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
