// Research-only face error validation; links the frozen production solver.
#include "model_inputs.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include <fstream>
#include <iostream>
#include <iomanip>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
template<class T> void read(std::istream &in,std::vector<T> &v) { size_t n; in>>n;v.resize(n);for(auto &x:v)in>>x; }
// Same assessed faces as check_estimate; differences evaluated before float32 output rounding.
template<class A,class B> double error(const WINDSGeneralData &w,const PoissonOperator &op,const A &x,const B &y,double speed,double height=1e30) {
 const auto &d=w.domain; double maximum=0;
 auto solid=[&](int i,int j,int k){if(k<1)return false;auto f=w.icellflag[d.cell(i,j,k)];return f==0||f==2;};
 auto delta=[&](size_t c){return double(x[c])-double(y[c]);};
 for(int k=1;k<d.nz()-2;++k) {if(d.z[k]>height)continue;
 for(int j=1;j<d.ny()-1;++j)for(int i=1;i<d.nx()-1;++i){
  if(solid(i,j,k))continue;auto c=d.cell(i,j,k);auto a=op.stencil(c,k);double here=delta(c);
  if(!solid(i-1,j,k))maximum=std::max(maximum,std::abs(.5*double(a.f)*d.dx()*(here-delta(d.cellAdd(c,-1,0,0)))));
  if(!solid(i,j-1,k))maximum=std::max(maximum,std::abs(.5*double(a.h)*d.dy()*(here-delta(d.cellAdd(c,0,-1,0)))));
  if(!solid(i,j,k-1))maximum=std::max(maximum,std::abs(.5*double(a.n)*d.dz_array[k]*(here-delta(d.cellAdd(c,0,0,-1)))));
 }}return maximum/speed;
}
int main(int argc,char **argv) {
 if(argc!=3)return 2;std::ifstream in(argv[1]);GridConfig g;ModelSettings m;BuildingArrays b;WindCondition c;
 in>>g.nx>>g.ny>>g.nz>>g.cell_size;g.max_cells=200000000;read(in,g.dz_layers);
 in>>m.roughness_length>>m.sensor_x>>m.sensor_y>>m.exposed_faces>>m.wall_roughness
   >>m.rooftop_flag>>m.upwind_cavity_flag>>m.street_canyon_flag>>m.street_intersection_flag
   >>m.wake_flag>>m.high_rise_flag>>m.sidewall_flag>>m.tall_buildings_flag>>m.angle_fade;
 read(in,b.vertices);read(in,b.offsets);read(in,b.ids);read(in,b.heights);read(in,b.base_heights);read(in,b.ring_offsets);
 in>>c.speed>>c.direction>>c.reference_height;read(in,c.layer_u);read(in,c.layer_v);c.profile_kind=c.layer_u.empty()?ProfileKind::Log:ProfileKind::LayerTable;
 if(!in)throw std::runtime_error("Invalid probe input");
 ModelInputs inputs(g,m,b);inputs.set_condition(c);
 WINDSGeneralData w(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
 w.applyWindProfile(inputs.inflow);w.applyParametrizations();PoissonOperator op(w,CoefficientOwnership::Take);
 const float omega=grid_relaxation(std::min(g.nx,g.ny));
 std::vector<float> candidate;EstimateReport report;int iterations;
 {SolverState<float> state(op,1e-4,default_order(),omega);
  state.begin(ConditionInputs(w),20000,StopRule::VelocityEstimate,nullptr,{true,c.speed,1e-3,25});
  auto work=state.advance(20000);iterations=work.diagnostics.iterations;report=*state.estimate_report();
  candidate=state.copy_state_for_study().multipliers;
 }
 SolverState<double> reference(op,1e-12,default_order(),omega);
 reference.begin(ConditionInputs(w),20000,StopRule::FixedSweeps,nullptr,{true,c.speed,1e-8,25});
 int steps=0;double stability=1,estimate=1;
 while(steps<19500){reference.advance(500);steps+=500;estimate=reference.estimate_report()->history.back().estimate;
  if(estimate<=1e-8){auto before=reference.copy_state_for_study().multipliers;reference.advance(500);steps+=500;
   stability=error(w,op,before,reference.copy_state_for_study().multipliers,c.speed);if(stability<=1e-9)break;}}
 auto exact=reference.copy_state_for_study().multipliers;
 double maximum=error(w,op,candidate,exact,c.speed),pedestrian=error(w,op,candidate,exact,c.speed,2.);
 std::ofstream out(argv[2]);out<<std::setprecision(17)<<"{\"iterations\":"<<iterations<<",\"stagnation\":"<<(report.stagnation_floor?"true":"false")
 <<",\"direction\":"<<c.direction<<",\"resolution\":"<<g.cell_size<<",\"reference_iterations\":"<<steps
 <<",\"reference_estimate\":"<<estimate<<",\"reference_stability\":"<<stability<<",\"max_face_error\":"<<maximum
 <<",\"pedestrian_face_error\":"<<pedestrian<<",\"pass\":"<<((maximum<=.001&&estimate<=1e-8&&stability<=1e-9)?"true":"false")<<"}\n";
 return maximum<=.001&&estimate<=1e-8&&stability<=1e-9?0:1;
}
