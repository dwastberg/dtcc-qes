#include "monitor.h"
#include "model_inputs.h"
#include "solver/mass_diagnostics.h"
#include "winds/WINDSGeneralData.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#ifdef _OPENMP
#include <omp.h>
#endif
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void require(bool ok,const char *message) { if (!ok) throw std::runtime_error(message); }
template<class F> static void rejects(F f) { try { f(); } catch (const std::exception &) { return; } throw std::runtime_error("Expected monitor rejection"); }
template<class T> static bool bits(const std::vector<T> &a,const std::vector<T> &b) {
  return a.size() == b.size() && (a.empty() || !std::memcmp(a.data(),b.data(),a.size()*sizeof(T)));
}
static std::unique_ptr<WINDSGeneralData> fixture(bool stretched,int nx=18,int ny=16,int nz=14,bool buildings=true) {
  GridConfig g; g.nx=nx; g.ny=ny; g.nz=nz;
  if (stretched) { g.dz_layers.resize(nz); for (int k=0;k<nz;++k) g.dz_layers[k] = k<8 ? .5 : 1.5; }
  ModelSettings model; model.sensor_x=model.sensor_y=3;
  BuildingArrays b{{},{0},{},{},{}};
  if (buildings) b={{12,12,12,18,18,18,18,12,12,12},{0,5},{0},{6},{0}};
  ModelInputs in(g,model,b); in.set_condition({5,33,10});
  auto d=std::make_unique<WINDSGeneralData>(make_domain(in),in.buildings,in.parameterizations,in.inflow.site_z0);
  d->applyWindProfile(in.inflow); d->applyParametrizations(); return d;
}
static MonitorSpec specification(const qes::Domain &d,bool world=false) {
  MonitorSpec s; s.region={0,double(d.dx())*(d.nx()-1),0,double(d.dy())*(d.ny()-1)};
  s.history_limit=4; s.global_mass=true; s.low_flow_fraction=1e-6;
  s.heights={double(d.z[1]),1.5,1.75,std::nextafter(double(d.z[1]),INFINITY),0,double(d.z.back()),double(d.z_face.back())};
  s.heights.erase(std::unique(s.heights.begin(),s.heights.end()),s.heights.end());
  for (double h : {1.5,1.75}) for (auto p : {std::pair{27.,21.},{21.,23.},{51.,35.},{15.,47.},{15.,29.}})
    s.receptors.push_back({std::to_string(s.receptors.size()),{p.first,p.second,h},true});
  s.receptors.push_back({"fractional",{11.25,9.5,1.5},true});
  s.receptors.push_back({"outside",{-1,9,1.5},false});
  if (world) {
    s.frame=MonitorFrame::World; s.origin={1e9,-2e9,100}; s.crs="test-local-frame";
    s.region.x_first+=s.origin[0];s.region.x_last+=s.origin[0];s.region.y_first+=s.origin[1];s.region.y_last+=s.origin[1];
    for (auto &r : s.receptors) { r.location.x+=s.origin[0];r.location.y+=s.origin[1]; }
  }
  return s;
}

struct Synthetic {
  std::unique_ptr<WINDSGeneralData> wind=fixture(false,5,4,6,false);
  std::vector<float> velocity;
  std::vector<std::int32_t> flags;
  Synthetic() { const auto &d=wind->domain;velocity.resize((d.nz()-2)*d.numHorizontalCellCentered()*3);flags.resize(velocity.size()/3,1); }
  Monitor::Source source(int iteration) {
    return {this,1,iteration,[&](LayerRange layers,CenteredDestination out) {
      const auto n=std::size_t(wind->domain.numHorizontalCellCentered()), first=std::size_t(layers.first)*n,last=std::size_t(layers.last)*n;
      out.velocity.assign(velocity.begin()+3*first,velocity.begin()+3*last);out.cell_flags.assign(flags.begin()+first,flags.begin()+last);
    },[](MassRegion,FluxOptions) { return MassDiagnostics{}; },{}};
  }
};

static void synthetic_checks() {
  Synthetic f; const auto &d=f.wind->domain;
  MonitorSpec s; s.region={0,10,0,8};s.heights={double(d.z[1]),3.0};s.history_limit=4;
  s.receptors={{"exact",{double(d.x[0]),double(d.y[0]),double(d.z[1])},true},
               {"fractional",{2,2,3},true},{"optional",{-1,1,1},false}};
  const auto n=std::size_t(d.numHorizontalCellCentered());
  for (int k=0;k<d.nz()-2;++k) for(std::size_t p=0;p<n;++p) f.velocity[3*(k*n+p)]=float(p+1);
  auto monitor=Monitor::compile_source(d,&f,1,s);
  require(monitor.slabs().size()==1 && monitor.slabs()[0].layers.first==0 && monitor.slabs()[0].layers.last==2,"Shared vertical support was not merged");
  const auto allocated=monitor.allocated_bytes();require(allocated<=monitor.planned_bytes(),"Memory estimate missed allocated buffers");
  const auto initial=monitor.capture_source(f.source(0),0);
  require(initial.initial && !initial.heights[0].short_change.available,"Initial reconstruction counted as stability evidence");
  for(int step=1;step<=4;++step) {
    for(int k=0;k<d.nz()-2;++k) for(std::size_t p=0;p<n;++p) f.velocity[3*(k*n+p)]=10+float((p+1)*std::pow(.5,step));
    const auto r=monitor.capture_source(f.source(2*step),step);
    require(r.required_receptors_valid,"Optional unsupported receptor invalidated required set");
    if(step==1) require(!r.heights[0].short_change.available,"Baseline used as post-initialization interval");
    if(step>=3) {
      require(r.heights[0].long_change.available,"Long window unavailable");
      require(r.heights[0].short_change.ratios.vector_max==.5,"Wrong successive-change ratio");
      require(r.heights[0].short_change.common_valid==n,"Wrong comparison support");
    }
  }
  require(monitor.history_size()==4 && monitor.history_at(0).iteration==2,"History ring was not bounded/chronological");
  // An invalid intermediate frame must remain visible even when endpoints recover.
  f.flags[0]=0;f.velocity[3]=std::numeric_limits<float>::quiet_NaN();
  auto r=monitor.capture_source(f.source(10),5);
  require(!r.required_receptors_valid && r.heights[0].short_change.validity_changes==2,"Validity changes were hidden");
  f.flags[0]=1;f.velocity[3]=1;
  r=monitor.capture_source(f.source(12),6);
  require(r.heights[0].long_change.validity_changes==2 && r.heights[0].long_change.common_valid==n-2
       && !r.heights[0].long_change.ratios.vector_max,"Intermediate invalid support contaminated long-window ratios");
  // A constant peak magnitude with a migrating location must retain both points.
  for(std::size_t c=0;c<f.flags.size();++c) { f.flags[c]=1;f.velocity[3*c]=1; }
  for(int k=0;k<d.nz()-2;++k) f.velocity[3*(k*n+2)]=20;
  monitor.capture_source(f.source(14),7);
  for(int k=0;k<d.nz()-2;++k) {f.velocity[3*(k*n+2)]=1;f.velocity[3*(k*n+3)]=20;}
  r=monitor.capture_source(f.source(16),8);
  const auto &hot=r.heights[0].short_change.hotspots;
  require(r.heights[0].peak.point==3 && hot[0].point==3 && hot[1].point==2
       && hot[0].vector_change==19 && hot[1].vector_change==19,"Moving hotspot evidence lost");
  require(monitor.allocated_bytes()==allocated,"Monitor grew with checkpoint count");
  // Exact centres must ignore zero-weight solid neighbors.
  f.flags[1]=2;
  auto exact=Monitor::compile_source(d,&f,1,s);r=exact.capture_source(f.source(0),0);
  require(r.receptors[0].sample.valid,"Inactive horizontal solid corner invalidated an exact centre");
  // The original double height distinguishes an exact centre from a height
  // just above it, even when both would round to the same float32 coordinate.
  f.flags[n]=2;
  auto near_spec=s;near_spec.receptors.clear();
  near_spec.heights={double(d.z[1]),std::nextafter(double(d.z[1]),INFINITY)};
  auto near=Monitor::compile_source(d,&f,1,near_spec);r=near.capture_source(f.source(0),0);
  require(near.samples()[0].valid && !near.samples()[n].valid,"Height narrowing hid an active vertical solid corner");
  f.flags[n]=1;f.velocity[0]=std::numeric_limits<float>::infinity();
  auto inf=Monitor::compile_source(d,&f,1,near_spec);r=inf.capture_source(f.source(0),0);
  require(!inf.samples()[0].valid,"Infinite component was treated as valid support");
  f.velocity[0]=1;
  auto distant_spec=s;distant_spec.heights={double(d.z[1]),double(d.z.back())};distant_spec.receptors.clear();
  auto distant=Monitor::compile_source(d,&f,1,distant_spec);
  require(distant.slabs().size()==2 && distant.slabs()[0].layers.last==1
       && distant.slabs()[1].layers.first==d.nz()-3,"Separated supports materialized their intervening volume");
  // No support and calm normalization stay explicitly unavailable.
  s.reference_speed=0;s.heights={0};s.receptors.clear();
  auto calm=Monitor::compile_source(d,&f,1,s);r=calm.capture_source(f.source(0),0);
  require(r.heights[0].valid==0 && !r.heights[0].peak.valid,"Out-of-centre height extrapolated");
  calm.capture_source(f.source(1),1);r=calm.capture_source(f.source(2),2);
  require(!r.heights[0].short_change.vector_change.maximum && !r.heights[0].short_change.vector_over_uref.maximum,"No valid support reported zero error");
  s.heights={1};for(auto &v:f.velocity)v=0;
  auto zero=Monitor::compile_source(d,&f,1,s);zero.capture_source(f.source(1),1);r=zero.capture_source(f.source(2),2);
  require(r.heights[0].short_change.vector_change.maximum==0 && !r.heights[0].short_change.vector_over_uref.maximum,"Calm normalization is defined");
  // Missing source lengths, duplicate work, wrong condition and memory limits fail.
  s.memory_limit_bytes=1;rejects([&] {Monitor::compile_source(d,&f,1,s);});
  s.memory_limit_bytes=64*1024*1024;s.long_window=std::numeric_limits<std::size_t>::max();rejects([&] {Monitor::compile_source(d,&f,1,s);});
  auto repeated=Monitor::compile_source(d,&f,1,MonitorSpec{{0,10,0,8},{1}});
  repeated.capture_source(f.source(1),0);rejects([&] {repeated.capture_source(f.source(1),1);});
  auto bad=Monitor::compile_source(d,&f,1,MonitorSpec{{0,10,0,8},{1}});
  auto src=f.source(1);src.epoch=2;rejects([&] {bad.capture_source(src,1);});
  auto lengths=Monitor::compile_source(d,&f,1,MonitorSpec{{0,10,0,8},{1}});
  src=f.source(1);src.observe=[](LayerRange,CenteredDestination out) {out.velocity.clear();};
  rejects([&] {lengths.capture_source(src,1);});
}

template<class Real> static void trajectory(bool stretched,SweepOrder order,OperatorStorage storage) {
  auto d=fixture(stretched);const PoissonOperator op(*d,storage);
  SolverState<Real> a(op,1e-5,order),b(op,1e-5,order);
  a.begin(ConditionInputs(*d),83,StopRule::FixedSweeps);b.begin(ConditionInputs(*d),83,StopRule::FixedSweeps);
  Monitor monitor(b,specification(d->domain));monitor.capture(b,0);
  const auto bytes=monitor.allocated_bytes();
  for(int work : {1,7,25,25,25}) {
    const auto ra=a.advance(work),rb=b.advance(work,true);
    require(ra.diagnostics.iterations==rb.diagnostics.iterations && ra.diagnostics.max_lagrange_multiplier_change==rb.diagnostics.max_lagrange_multiplier_change,"Trend changes stopping norm");
    const auto before=b.copy_state_for_study();const auto record=monitor.capture(b,rb.diagnostics.iterations);
    require(record.residual_trend && record.residual_trend->iteration==record.iteration,"Stale/missing in-sweep trend");
    const auto after=b.copy_state_for_study(),expected=a.copy_state_for_study();
    require(bits(before.multipliers,after.multipliers) && bits(before.rhs,after.rhs),"Observation changed state");
    require(bits(expected.multipliers,after.multipliers) && bits(expected.rhs,after.rhs),"Monitoring changed solver trajectory");
    const auto global=b.diagnose();const auto &mass=record.mass[0].divergence;
    require(mass.interior_max==global.interior_max && mass.interior_rms==global.interior_rms && mass.top_band_max==global.top_band_max,"Monitored global mass changed legacy values");
  }
  std::vector<float> centers;std::vector<std::int32_t> flags;
  b.finalize(FaceDestination(*d),CenteredDestination{centers,flags});const auto u=d->u,v=d->v,w=d->w;
  a.finalize(FaceDestination(*d));require(bits(u,d->u)&&bits(v,d->v)&&bits(w,d->w),"Monitored final output changed");
  require(monitor.allocated_bytes()==bytes,"Trajectory history grew unbounded");
  b.begin(ConditionInputs(*d),1,StopRule::FixedSweeps);rejects([&] {monitor.capture(b,100);});
}
template<class Real> static void residual() {
  auto d=fixture(false,3,3,2,false);
  for(auto *a : {&d->u0,&d->v0,&d->w0}) std::fill(a->begin(),a->end(),0);
  const auto &domain=d->domain;const auto c=domain.cell(1,1,1);d->u0[domain.face(2,1,1)]=.125f;
  const PoissonOperator op(*d);SolverState<Real> state(op);state.begin(ConditionInputs(*d),2,StopRule::FixedSweeps);
  const auto rhs=state.copy_state_for_study().rhs[c];state.advance(1,true);
  auto trend=state.residual_trend();require(trend && trend->fluid_cells==1 && trend->maximum==std::abs(double(rhs))
       && trend->volume_weighted_rms==trend->maximum,"First-sweep algebraic trend is not the known single-cell residual");
  const auto previous=state.copy_state_for_study().multipliers[c];const auto coef=op.stencil(c,1);
  const double diagonal=double(coef.e)+coef.f+coef.g+coef.h+coef.m+coef.n;
  const double expected=double(coef.n)*previous-double(rhs)-diagonal*previous;
  state.advance(1,true);trend=state.residual_trend();
  require(trend && trend->iteration==2 && trend->maximum==std::abs(expected),"Partly updated residual or ground-mirror timing changed");
  state.begin(ConditionInputs(*d),1,StopRule::FixedSweeps);state.advance(1);
  require(!state.residual_trend(),"Disabled trend leaked an old condition");
}
static void mass_flux() {
  auto wind=fixture(false,5,5,4,false);const auto &d=wind->domain;const PoissonOperator op(*wind);
  const auto run=[&](FluxOptions opts,MassRegion region=MassRegion{}) {
    return mass_diagnostics(op,wind->icellflag,[&](int component,int i,int j,int k) {
      return component==0 ? wind->u[d.face(i,j,k)] : 0.0f;
    },region,opts);
  };
  std::fill(wind->u.begin(),wind->u.end(),0);
  auto stats=run({true,5,1e-6});require(stats.interior_flux.low_flow_cells==stats.cells && !stats.interior_flux.relative_max,"Zero flow silently normalized");
  stats=run({true,5,{}});require(stats.interior_flux.unassessed_cells==stats.cells,"Absent threshold treated as calibrated");
  for(int k=0;k<d.nz();++k) for(int j=0;j<d.ny();++j) for(int i=0;i<d.nx();++i)wind->u[d.face(i,j,k)]=float(i*d.dx());
  stats=run({true,5,1e-6});
  require(stats.cells==18 && stats.top_band_cells==9 && stats.interior_max==1 && stats.interior_rms==1,"Legacy mass region changed");
  require(stats.interior_flux.net_cell_flux==144 && stats.interior_flux.boundary_flux==144
       && stats.interior_flux.absolute_cell_flux==144 && stats.interior_flux.resolved_cells==18,"Uniform flux/volume oracle failed");
  std::fill(wind->u.begin(),wind->u.end(),0);
  for(int k=0;k<d.nz();++k)for(int j=0;j<d.ny();++j)wind->u[d.face(2,j,k)]=1;
  stats=run({true,5,1e-6},{1,3,1,4,0,2});
  require(stats.interior_flux.boundary_flux==0 && stats.interior_flux.net_cell_flux==0
       && stats.interior_flux.absolute_cell_flux>0,"Canceling local errors hidden by boundary imbalance");
}

static void number(double x) {if(std::isfinite(x))std::cout<<x;else std::cout<<"null";}
template<class T> static void json_array(const std::vector<T> &v) {std::cout<<'[';for(std::size_t i=0;i<v.size();++i){if(i)std::cout<<',';number(double(v[i]));}std::cout<<']';}
static void sample_json(const MonitorSample &v) {
  std::cout<<"{\"valid\":"<<(v.valid?"true":"false")<<",\"velocity\":[";
  for(int c=0;c<3;++c){if(c)std::cout<<',';number(v.valid?v.velocity[c]:NAN);}std::cout<<"]}";
}
template<class Real> static void dump(bool stretched,bool world) {
  auto data=fixture(stretched,40,40,32);const auto &d=data->domain;const PoissonOperator op(*data,CoefficientOwnership::Take);
  SolverState<Real> state(op);state.begin(ConditionInputs(*data),37,StopRule::FixedSweeps);
  Monitor monitor(state,specification(d,world));state.advance(37,true);monitor.capture(state,1);
  std::vector<float> velocity;std::vector<std::int32_t> flags;
  state.finalize(FaceDestination(*data),CenteredDestination{velocity,flags});
  std::cout<<std::setprecision(17)<<"{\"x\":";json_array(d.x);std::cout<<",\"y\":";json_array(d.y);
  std::cout<<",\"z\":";json_array(std::vector<float>(d.z.begin()+1,d.z.end()));
  std::cout<<",\"z_faces\":";json_array(std::vector<float>(d.z_face.begin()+1,d.z_face.end()));
  std::cout<<",\"origin\":["<<monitor.specification().origin[0]<<','<<monitor.specification().origin[1]<<','<<monitor.specification().origin[2]<<']';
  std::cout<<",\"world\":"<<(world?"true":"false")<<",\"heights\":";json_array(monitor.specification().heights);
  std::set<int> layers{0,d.nz()-3};for(const auto &slab:monitor.slabs())for(int k=slab.layers.first;k<slab.layers.last;++k)layers.insert(k);
  const auto n=std::size_t(d.numHorizontalCellCentered());std::cout<<",\"materialized\":[";bool first=true;
  for(int k:layers){if(!first)std::cout<<',';first=false;std::cout<<"{\"layer\":"<<k<<",\"velocity\":";
    json_array(std::vector<float>(velocity.begin()+k*n*3,velocity.begin()+(k+1)*n*3));std::cout<<",\"flags\":";
    json_array(std::vector<std::int32_t>(flags.begin()+k*n,flags.begin()+(k+1)*n));std::cout<<'}';}
  std::cout<<"],\"samples\":[";for(std::size_t i=0;i<monitor.samples().size();++i){if(i)std::cout<<',';sample_json(monitor.samples()[i]);}
  std::cout<<"],\"receptors\":[";first=true;for(const auto &r:monitor.specification().receptors){if(!first)std::cout<<',';first=false;std::cout<<'['<<r.location.x<<','<<r.location.y<<','<<r.location.height_agl<<']';}
  std::cout<<"],\"allocated_bytes\":"<<monitor.allocated_bytes()<<",\"planned_bytes\":"<<monitor.planned_bytes()<<"}\n";
}
int main(int argc,char **argv) try {
#ifdef _OPENMP
  omp_set_dynamic(0);omp_set_num_threads(2);
#endif
  if(argc>1 && std::string(argv[1])=="--dump") {
    const bool stretched=argc>3&&std::string(argv[3])=="stretched",world=argc>4&&std::string(argv[4])=="world";
    if(argc>2&&std::string(argv[2])=="float64")dump<double>(stretched,world);else dump<float>(stretched,world);return 0;
  }
  synthetic_checks();mass_flux();residual<float>();residual<double>();
  for(int threads : {1,2,4,8}) {
#ifdef _OPENMP
    omp_set_num_threads(threads);
#endif
    for(bool stretched : {false,true})for(auto order : {SweepOrder::Lexicographic,SweepOrder::RedBlack})for(auto storage : {OperatorStorage::Automatic,OperatorStorage::Explicit}) {
      trajectory<float>(stretched,order,storage);trajectory<double>(stretched,order,storage);
    }
  }
  std::cout<<"Monitor sampling, windows, mass, trend and trajectory checks passed\n";return 0;
} catch(const std::exception &error) {std::cerr<<error.what()<<'\n';return 1;}
