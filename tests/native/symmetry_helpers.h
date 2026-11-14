#pragma once
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
static Field run(const GridConfig &g, const BuildingArrays &b, double direction, int cavity, int wake=2) {
  ModelSettings m; m.upwind_cavity_flag=cavity; m.wake_flag=wake;
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
                    const std::array<std::vector<float>,3> &b, const qes::Domain &d, bool mean=false) {
  double total=0; size_t count=0;
  for(int k=1;k<d.nz()-1;++k) for(int j=1;j<d.ny()-2;++j) for(int i=1;i<d.nx()-2;++i) {
    const auto f=d.face(i,j,k);
    const long mirror[]={d.face(d.nx()-1-i,d.ny()-2-j,k),
                         d.face(d.nx()-2-i,d.ny()-1-j,k),
                         d.face(d.nx()-2-i,d.ny()-2-j,k)};
    for(int component=0;component<3;++component) {
      double difference=std::abs(a[component][f]+(component==2?-1:1)*b[component][mirror[component]]);
      total=mean?total+difference:std::max(total,difference); ++count;
    }
  }
  return mean?total/count:total;
}
static std::array<double,4> check(const GridConfig &g, BuildingArrays b,double direction,int cavity,int wake=2) {
  ModelInputs input(g,ModelSettings{},b); auto d=make_domain(input);
  auto reflected=b;
  for(size_t i=0;i<b.vertices.size();i+=2) {
    reflected.vertices[i]=(d.nx()-1)*g.cell_size-b.vertices[i];
    reflected.vertices[i+1]=(d.ny()-1)*g.cell_size-b.vertices[i+1];
  }
  auto a=run(g,b,direction,cavity,wake), r=run(g,reflected,std::fmod(direction+180,360),cavity,wake);
  return {error(a.initial,r.initial,d),error(a.final,r.final,d),error(a.initial,r.initial,d,true),error(a.final,r.final,d,true)};
}
