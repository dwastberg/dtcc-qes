// Bounded S5b native study. No stopping/acceptance policy or numerical changes.
#include "model_inputs.h"
#include "monitor.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "util/QESLog.h"
#include "solver_policy_study_json.h"
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#ifdef _OPENMP
#include <omp.h>
#endif
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
using Clock=std::chrono::steady_clock;
static double elapsed(Clock::time_point t) {return std::chrono::duration<double>(Clock::now()-t).count();}
template<class T> static std::uint64_t fingerprint(const std::vector<T> &v) {
  std::uint64_t h=14695981039346656037ULL;const auto *p=reinterpret_cast<const unsigned char *>(v.data());
  for(std::size_t i=0;i<v.size()*sizeof(T);++i) h=(h^p[i])*1099511628211ULL;return h;
}
template<class V> static void json_array(const V &v) {std::cout<<'[';bool sep=false;for(auto x:v){if(sep)std::cout<<',';sep=true;std::cout<<x;}std::cout<<']';}
static void flux(const MassDiagnostics::Flux &f) {
  std::cout<<"{\"signed\":"<<f.net_cell_flux<<",\"absolute\":"<<f.absolute_cell_flux
    <<",\"boundary\":"<<f.boundary_flux<<",\"throughflow\":"<<f.throughflow<<'}';
}
static void mass(const MassDiagnostics &m) {
  std::cout<<"{\"maximum\":"<<m.interior_max<<",\"rms\":"<<m.interior_rms
    <<",\"top_maximum\":"<<m.top_band_max<<",\"cells\":"<<m.cells<<",\"top_cells\":"<<m.top_band_cells<<",\"flux\":";
  flux(m.interior_flux);std::cout<<",\"top_flux\":";flux(m.top_band_flux);std::cout<<'}';
}
static double divergence(const CellDiagnostics &c,const qes::Domain &d) {
  const auto a=c.coefficients;const int k=c.k+1;const double dx=d.dx(),dy=d.dy(),dz=d.dz_array[k];
  return (double(a.e)*dx*dx*c.faces[0]-double(a.f)*dx*dx*c.faces[1])/dx
    +(double(a.g)*dy*dy*c.faces[2]-double(a.h)*dy*dy*c.faces[3])/dy
    +(double(a.m)*dz*.5*(dz+d.dz_array[k+1])*c.faces[4]
      -double(a.n)*dz*.5*(dz+d.dz_array[k-1])*c.faces[5])/dz;
}
template<class Real> static void hotspot(const SolverState<Real> &s,const WINDSGeneralData &w,CellDiagnostics c) {
  const auto &d=w.domain;const auto a=c.coefficients;
  std::cout<<"{\"ijk\":["<<c.i<<','<<c.j<<','<<c.k<<"],\"xyz\":["<<d.x[c.i]<<','<<d.y[c.j]<<','<<d.z[c.k+1]
    <<"],\"flag\":"<<c.flag<<",\"initial_flag\":"<<w.icellflag_initial[d.cell(c.i,c.j,c.k+1)]
    <<",\"assessed\":"<<c.assessed<<",\"top_band\":"<<c.top_band<<",\"residual\":"<<c.equation_residual
    <<",\"divergence\":"<<divergence(c,d)<<",\"lambda\":"<<c.multiplier<<",\"rhs\":"<<c.rhs<<",\"coefficients\":";
  json_array(std::array<double,6>{a.e,a.f,a.g,a.h,a.m,a.n});std::cout<<",\"neighbour_lambda\":";json_array(c.neighbour_multipliers);
  std::cout<<",\"faces\":";json_array(c.faces);std::cout<<",\"initial_faces\":";json_array(c.initial_faces);
  std::cout<<",\"neighbours\":[";
  const int di[]={1,-1,0,0,0,0},dj[]={0,0,1,-1,0,0},dk[]={0,0,0,0,1,-1};
  for(int a=0;a<6;++a) {
    if(a)std::cout<<',';const int i=c.i+di[a],j=c.j+dj[a],k=c.k+1+dk[a];const auto n=d.cell(i,j,k);const auto b=s.prepared_operator().stencil(n,k);
    std::cout<<"{\"flag\":"<<w.icellflag[n]<<",\"initial_flag\":"<<w.icellflag_initial[n]<<",\"coefficients\":";
    json_array(std::array<double,6>{b.e,b.f,b.g,b.h,b.m,b.n});std::cout<<'}';
  }
  std::cout<<"],\"cell_mass\":";mass(s.diagnose({c.i,c.i+1,c.j,c.j+1,c.k,c.k+1},{true,5,{}}));std::cout<<'}';
}
template<class Real> static void run(const std::string &path,bool locate,int cap,int cadence,
                                    const GridConfig &g,const ModelSettings &m,const BuildingArrays &b,
                                    const WindCondition &condition,MonitorSpec spec,
                                    float relaxation=1.78f,double budget=0,bool policy_metrics=false) {
  int team=1;
#ifdef _OPENMP
#pragma omp parallel
  {
#pragma omp single
    team=omp_get_num_threads();
  }
#endif
  const auto start=Clock::now();ModelInputs input(g,m,b);input.set_condition(condition);
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  PoissonOperator op(w,CoefficientOwnership::Take);w.applyWindProfile(input.inflow);w.applyParametrizations();
  SolverState<Real> s(op,1e-5,default_order(),relaxation);s.begin(ConditionInputs(w),cap,StopRule::FixedSweeps);
  const auto &d=w.domain;Monitor monitor(s,spec);const double prepare=elapsed(start);
  std::ofstream samples(path,std::ios::binary);if(!samples)throw std::runtime_error("Cannot create samples");
  std::cout<<std::setprecision(17)<<"{\"team\":"<<team<<",\"relaxation\":"<<relaxation<<",\"budget_seconds\":"<<budget<<",\"prepare_seconds\":"<<prepare
    <<",\"initial_hashes\":[\""<<fingerprint(w.u0)<<"\",\""<<fingerprint(w.v0)<<"\",\""<<fingerprint(w.w0)<<"\",\""<<fingerprint(w.icellflag)<<"\"]"
    <<",\"plane_points\":"<<monitor.plane_points()<<",\"checkpoints\":[";
  bool sep=false;double sweep_seconds=0;
  for(int target=0;;target=std::min(cap,target+cadence)) {
    auto t=Clock::now();
    if(budget>0) {
      while(s.diagnostics().iterations<target && elapsed(start)<budget)s.advance(1);
      target=s.diagnostics().iterations;
    } else s.advance(target-s.diagnostics().iterations);
    sweep_seconds+=elapsed(t);
    t=Clock::now();const auto r=s.equation_residual();const double residual_seconds=elapsed(t);
    t=Clock::now();const auto md=s.diagnose({}, {true,condition.speed,{}});const double mass_seconds=elapsed(t);
    t=Clock::now();const auto &checkpoint=monitor.capture(s,elapsed(start));const double monitor_seconds=elapsed(t);
    if(sep)std::cout<<',';sep=true;
    std::cout<<"{\"iteration\":"<<target<<",\"sweep_seconds\":"<<sweep_seconds
      <<",\"residual_seconds\":"<<residual_seconds<<",\"mass_seconds\":"<<mass_seconds<<",\"monitor_seconds\":"<<monitor_seconds
      <<",\"maximum_change\":"<<s.diagnostics().max_lagrange_multiplier_change
      <<",\"residual\":{\"maximum\":"<<r.maximum<<",\"rms\":"<<r.volume_weighted_rms<<",\"rhs_maximum\":"<<r.rhs_maximum
      <<",\"rhs_rms\":"<<r.rhs_volume_weighted_rms<<",\"relative_maximum\":"<<r.relative_maximum.value_or(-1)
      <<",\"relative_rms\":"<<r.relative_volume_weighted_rms.value_or(-1)<<",\"cells\":"<<r.fluid_cells
      <<",\"excluded_solids\":"<<r.excluded_solid_cells<<"},\"mass\":";mass(md);
    const auto &v=monitor.samples();std::cout<<",\"samples\":"<<v.size();
    if(policy_metrics){
      std::cout<<",\"monitor\":";policy_study::checkpoint(checkpoint);
      std::cout<<",\"regional_residual\":[";bool separator=false;
      for(const auto &region:monitor.regions()) {
        if(separator)std::cout<<',';separator=true;
        const auto rr=s.equation_residual(region.bounds);
        std::cout<<"{\"maximum\":"<<rr.maximum<<",\"rms\":"<<rr.volume_weighted_rms<<",\"cells\":"<<rr.fluid_cells<<'}';
      }
      std::cout<<']';
    }
    for(const auto &point:v) {double values[]={point.velocity[0],point.velocity[1],point.velocity[2],double(point.valid)};
      samples.write(reinterpret_cast<const char *>(values),sizeof(values));}
    if(locate && (target==500 || target==cap)) {
      t=Clock::now();CellDiagnostics worst[3];double maxima[3]={-1,-1,-1};std::size_t relabeled=0;
      for(int k=1;k<d.nz()-2;++k) for(int j=1;j<d.ny()-2;++j) for(int i=1;i<d.nx()-2;++i) {
        const auto n=d.cell(i,j,k);if(w.icellflag[n]==0 || w.icellflag[n]==2)continue;
        const auto cell=s.diagnose_cell(i,j,k-1);const bool changed=w.icellflag_initial[n]==0 || w.icellflag_initial[n]==2;
        relabeled+=changed;const int group=cell.top_band?2:(changed?1:0);const double value=std::abs(divergence(cell,d));
        if(value>maxima[group]) {maxima[group]=value;worst[group]=cell;}
      }
      std::cout<<",\"relabeled_solid_cells\":"<<relabeled<<",\"hotspots\":[";
      for(int n=0;n<3;++n) {if(n)std::cout<<',';if(maxima[n]<0)std::cout<<"null";else hotspot(s,w,worst[n]);}
      std::cout<<"],\"hotspot_scan_seconds\":"<<elapsed(t);
    }
    std::cout<<",\"elapsed_seconds\":"<<elapsed(start)<<'}'<<std::flush;
    if(target==cap || (budget>0 && elapsed(start)>=budget))break;
  }
  if(!samples)throw std::runtime_error("Sample write failed");
  std::cout<<"],\"total_seconds\":"<<elapsed(start)<<",\"workspace_bytes\":"<<s.workspace_bytes()<<"}\n";
}
int main(int argc,char **argv) {
  try {
    qes::log::ScopedHandler silent({});if(argc!=4 && argc!=6 && argc!=7)throw std::runtime_error("Usage: solver_numerics_probe float32|float64 samples.bin locate(0|1) [omega budget_seconds [policy_metrics]]; protocol on stdin");
    const float relaxation=argc>=6?std::stof(argv[4]):1.78f;
    const double budget=argc>=6?std::stod(argv[5]):0;
    const bool policy_metrics=argc==7 && std::stoi(argv[6])!=0;
    if(!std::isfinite(budget) || budget<0)throw std::runtime_error("Invalid study budget");
    GridConfig g;WindCondition condition;ModelSettings m;MonitorSpec spec;int cap,cadence,count;
    if(!(std::cin>>g.nx>>g.ny>>g.nz>>g.cell_size>>condition.speed>>condition.direction>>condition.reference_height>>cap>>cadence>>m.street_canyon_flag))throw std::runtime_error("Missing header");
    if(cap<1 || cap>16000 || cadence<1 || (cap+cadence-1)/cadence>128)throw std::runtime_error("Invalid bounded study work");
    g.max_cells=40000000;g.dz_layers.resize(g.nz);for(auto &x:g.dz_layers)std::cin>>x;
    std::cin>>count;if(count<0 || count>1000)throw std::runtime_error("Invalid building count");
    BuildingArrays b;b.offsets={0};
    for(int n=0;n<count;++n) {int vertices;double height;std::cin>>vertices>>height;
      if(vertices<4 || vertices>100)throw std::runtime_error("Invalid polygon");
      for(int v=0;v<vertices;++v){double x,y;std::cin>>x>>y;b.vertices.push_back(x);b.vertices.push_back(y);}
      b.offsets.push_back(b.vertices.size()/2);b.ids.push_back(n);b.heights.push_back(height);b.base_heights.push_back(0);
    }
    std::cin>>spec.region.x_first>>spec.region.x_last>>spec.region.y_first>>spec.region.y_last>>count;
    if(count<0 || count>100)throw std::runtime_error("Invalid receptor count");
    for(int n=0;n<count;++n) {double x,y;std::cin>>x>>y;for(double h:{1.5,1.75})spec.receptors.push_back({std::to_string(spec.receptors.size()),{x,y,h},true});}
    if(!std::cin)throw std::runtime_error("Truncated study inputs");
    spec.reference_speed=condition.speed;spec.history_limit=4;spec.memory_limit_bytes=128*1024*1024;
    if(policy_metrics){spec.short_window=1;spec.long_window=4;spec.history_limit=8;spec.global_mass=true;}
    if(std::string(argv[1])=="float32")run<float>(argv[2],std::stoi(argv[3])!=0,cap,cadence,g,m,b,condition,spec,relaxation,budget,policy_metrics);
    else if(std::string(argv[1])=="float64")run<double>(argv[2],std::stoi(argv[3])!=0,cap,cadence,g,m,b,condition,spec,relaxation,budget,policy_metrics);
    else throw std::runtime_error("Invalid precision");
  } catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
