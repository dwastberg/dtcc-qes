// Bounded S3 matched-work probe. Also built against the frozen S2 sources with
// DTCC_QES_MONITOR_BASELINE: identical geometry, work, clocks and finalization.
#include "model_inputs.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESLog.h"
#ifndef DTCC_QES_MONITOR_BASELINE
#include "monitor.h"
#endif
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <sys/resource.h>
#ifdef _OPENMP
#include <omp.h>
#endif
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
using Clock=std::chrono::steady_clock;
static double seconds(Clock::time_point start) { return std::chrono::duration<double>(Clock::now()-start).count(); }
template<class T> static std::uint64_t fingerprint(const std::vector<T> &values) {
  std::uint64_t h=14695981039346656037ULL;
  const auto *p=reinterpret_cast<const unsigned char *>(values.data());
  for(std::size_t i=0;i<values.size()*sizeof(T);++i) h=(h^p[i])*1099511628211ULL;
  return h;
}
template<class Real> static void run(const std::string &mode,const std::vector<double> &layers) {
  constexpr int work=40, cadence=10;
  int team=1;
#ifdef _OPENMP
#pragma omp parallel
  {
#pragma omp single
    team=omp_get_num_threads();
  }
#endif
  const auto all=Clock::now();auto clock=Clock::now();
  GridConfig grid;grid.nx=grid.ny=320;grid.nz=int(layers.size());grid.cell_size=.5;grid.max_cells=20000000;grid.dz_layers=layers;
  ModelSettings model;
  BuildingArrays buildings;buildings.offsets={0};
  for(auto b : {std::array<double,3>{22,22,7.9},{42,22,7.9},{22,42,7.9},{42,42,23.7}}) {
    const double x=b[0],y=b[1];
    for(auto p : {std::pair{x,y},std::pair{x,y+12},std::pair{x+12,y+12},std::pair{x+12,y},std::pair{x,y}})
      {buildings.vertices.push_back(p.first);buildings.vertices.push_back(p.second);}
    buildings.offsets.push_back(buildings.vertices.size()/2);buildings.ids.push_back(buildings.ids.size());
    buildings.heights.push_back(b[2]);buildings.base_heights.push_back(0);
  }
  ModelInputs inputs(grid,model,buildings);inputs.set_condition({5,270,10});
  WINDSGeneralData data(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  PoissonOperator op(data,CoefficientOwnership::Take);
  const double prepare=seconds(clock);clock=Clock::now();
  data.applyWindProfile(inputs.inflow);data.applyParametrizations();
  SolverState<Real> state(op);state.begin(ConditionInputs(data),work,StopRule::FixedSweeps);
  const double initialize=seconds(clock);clock=Clock::now();
  std::size_t planned=0,allocated=0,checkpoints=0,slab_layers=0;
#ifndef DTCC_QES_MONITOR_BASELINE
  std::unique_ptr<Monitor> monitor;
  if(mode!="disabled") {
    MonitorSpec spec;spec.region={0,80,0,80};spec.history_limit=8;
    for(double h : {1.5,1.75}) for(auto p : {std::pair{27.,21.},{21.,23.},{51.,35.},{15.,47.},{15.,29.}})
      spec.receptors.push_back({std::to_string(spec.receptors.size()),{p.first,p.second,h},true});
    monitor=std::make_unique<Monitor>(state,spec);monitor->capture(state,seconds(all));
    allocated=monitor->allocated_bytes();planned=monitor->planned_bytes();++checkpoints;
    for(const auto &s:monitor->slabs()) slab_layers+=s.layers.last-s.layers.first;
  }
#else
  if(mode!="disabled") throw std::runtime_error("S2 only supports disabled mode");
#endif
  const double compile=seconds(clock);double sweeps=0,observe=0;
  for(int block=0;block<work/cadence;++block) {
    clock=Clock::now();
#ifndef DTCC_QES_MONITOR_BASELINE
    if(mode=="trend-checkpoint") { state.advance(cadence-1);state.advance(1,true); }
    else if(mode=="trend-continuous") state.advance(cadence,true);
    else state.advance(cadence);
#else
    state.advance(cadence);
#endif
    sweeps+=seconds(clock);clock=Clock::now();
#ifndef DTCC_QES_MONITOR_BASELINE
    if(monitor) {
      monitor->capture(state,seconds(all));++checkpoints;
      if(monitor->allocated_bytes()!=allocated) throw std::runtime_error("Monitor grew between checkpoints");
    }
#endif
    observe+=seconds(clock);
  }
  clock=Clock::now();std::vector<float> velocity;std::vector<std::int32_t> flags;MassDiagnostics mass;
  state.finalize(FaceDestination(data),CenteredDestination{velocity,flags},&mass);
  const double finalize=seconds(clock),total=seconds(all);
  const auto diagnostics=state.diagnostics();
  if(diagnostics.iterations!=work || velocity.size()!=std::size_t(92*320*320*3)) throw std::runtime_error("Unexpected grid/work");
  rusage usage{};getrusage(RUSAGE_SELF,&usage);
#ifdef __APPLE__
  const auto rss=std::uint64_t(usage.ru_maxrss);
#else
  const auto rss=std::uint64_t(usage.ru_maxrss)*1024;
#endif
  std::cout<<std::setprecision(17)<<"{\"team\":"<<team<<",\"iterations\":"<<diagnostics.iterations
    <<",\"shape\":[92,320,320],\"seconds\":{\"prepare\":"<<prepare<<",\"initialize\":"<<initialize
    <<",\"monitor_compile_and_initial\":"<<compile<<",\"sweeps\":"<<sweeps<<",\"checkpoints\":"<<observe
    <<",\"finalize\":"<<finalize<<",\"total\":"<<total<<"},\"peak_rss_bytes\":"<<rss
    <<",\"monitor_planned_bytes\":"<<planned<<",\"monitor_allocated_bytes\":"<<allocated
    <<",\"checkpoints\":"<<checkpoints<<",\"slab_layers\":"<<slab_layers
    <<",\"max_change\":"<<diagnostics.max_lagrange_multiplier_change
    <<",\"mass\":["<<mass.interior_max<<","<<mass.interior_rms<<","<<mass.top_band_max
    <<"],\"fingerprints_fnv1a64\":[\""<<fingerprint(velocity)<<"\",\""<<fingerprint(flags)<<"\"]}\n";
}
int main(int argc,char **argv) {
  try {
    qes::log::ScopedHandler silent({});
    if(argc!=3) throw std::runtime_error("Usage: solver_monitor_probe float32|float64 disabled|planes|trend-checkpoint|trend-continuous");
    const std::string precision=argv[1],mode=argv[2];
    if(mode!="disabled" && mode!="planes" && mode!="trend-checkpoint" && mode!="trend-continuous") throw std::runtime_error("Unknown mode");
    std::vector<double> layers;double dz;while(std::cin>>dz) layers.push_back(dz);
    if(layers.size()!=92) throw std::runtime_error("Expected declared 92-layer input");
    if(precision=="float32") run<float>(mode,layers);
    else if(precision=="float64") run<double>(mode,layers);
    else throw std::runtime_error("Unknown precision");
    return 0;
  } catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
