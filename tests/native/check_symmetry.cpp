// Point reflection on the staggered grid, before and after pressure correction.
#include "building_fixtures.h"
#include "winds/CavityFrame.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
struct Field { std::array<std::vector<float>,3> initial, final; };
static Field run(const GridConfig &g, const BuildingArrays &b, double direction, int cavity) {
  ModelSettings m; m.upwind_cavity_flag=cavity;
  ModelInputs input(g,m,b); input.set_condition({5,direction,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);
  Field out;
  w.applyParametrizations([&](const char *stage) {
    if(std::string(stage)=="solid_mask") out.initial={w.u0,w.v0,w.w0};
  });
  if(out.initial[0].empty()) throw std::runtime_error("solid_mask callback missing");
  PoissonOperator op(w); SolverState<float> state(op);
  state.begin(ConditionInputs(w),200,StopRule::FixedSweeps); state.advance(200); state.finalize(FaceDestination(w));
  out.final={w.u,w.v,w.w}; return out;
}
static double error(const std::array<std::vector<float>,3> &a,
                    const std::array<std::vector<float>,3> &b, const qes::Domain &d) {
  double total=0;
  for(int k=1;k<d.nz()-1;++k) for(int j=1;j<d.ny()-2;++j) for(int i=1;i<d.nx()-2;++i) {
    const auto f=d.face(i,j,k);
    const long mirror[]={d.face(d.nx()-1-i,d.ny()-2-j,k),
                         d.face(d.nx()-2-i,d.ny()-1-j,k),
                         d.face(d.nx()-2-i,d.ny()-2-j,k)};
    for(int component=0;component<3;++component) {
      total=std::max(total,double(std::abs(a[component][f]+(component==2?-1:1)*b[component][mirror[component]])));
    }
  }
  return total;
}
static std::array<double,2> check(const GridConfig &g, BuildingArrays b,double direction,int cavity) {
  ModelInputs input(g,ModelSettings{},b); auto d=make_domain(input);
  auto reflected=b;
  for(size_t i=0;i<b.vertices.size();i+=2) {
    reflected.vertices[i]=(d.nx()-1)*g.cell_size-b.vertices[i];
    reflected.vertices[i+1]=(d.ny()-1)*g.cell_size-b.vertices[i+1];
  }
  auto a=run(g,b,direction,cavity), r=run(g,reflected,std::fmod(direction+180,360),cavity);
  return {error(a.initial,r.initial,d),error(a.final,r.final,d)};
}
int main(int argc,char **argv) try {
  // Eight facade normals, including the formerly unwrapped south-west normal.
  const double pi=std::acos(-1);
  for(int n=-1;n<=6;++n) {
    float normal=n*pi/4;
    const float gamma=cavityFrame(normal);
    // At half-quadrant boundaries float rounding can select either adjacent
    // grid component; both frames must represent the same facade modulo pi/2.
    if(normal>pi || normal < -pi || std::abs(std::sin(4*gamma)-std::sin(4*n*pi/4))>2e-6)
      throw std::runtime_error("Invalid cavity frame for 45-degree normal");
  }
  for(double angle:{-0.3,0.3,4.5}) {
    float normal=angle;
    const float gamma=cavityFrame(normal);
    if(std::abs(std::sin(4*gamma)-std::sin(4*angle))>2e-6)
      throw std::runtime_error("Cavity frame discarded facade angle");
  }
  GridConfig g; g.nx=g.ny=100; g.nz=45; g.cell_size=2;
  const bool enforce=argc<2 || std::string(argv[1])!="--report";
  for(auto parameters:{std::array<double,2>{70,200},{20,250},{0,180},{0,185}}) {
    auto b=test_fixture::rectangle(80,80,40,40,30);
    const double angle=parameters[0]*std::acos(-1)/180;
    for(size_t n=0;n<b.vertices.size();n+=2) {
      double x=b.vertices[n]-100,y=b.vertices[n+1]-100;
      b.vertices[n]=100+x*std::cos(angle)-y*std::sin(angle);
      b.vertices[n+1]=100+x*std::sin(angle)+y*std::cos(angle);
    }
    auto off=check(g,b,parameters[1],0),on=check(g,b,parameters[1],2);
    std::cout<<parameters[0]<<","<<parameters[1]<<" initial off/on "<<off[0]<<" "<<on[0]
             <<" final off/on "<<off[1]<<" "<<on[1]<<std::endl;
    if(enforce && on[0]>off[0]+0.01) throw std::runtime_error("Upwind cavity increases point-mirror error");
  }
} catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
