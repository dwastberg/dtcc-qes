#include "building_fixtures.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static std::array<double,3> run(bool exposed,double obstacle_height,double x=150) {
  GridConfig g; g.nx=200;g.ny=100;g.nz=60;g.cell_size=2;g.max_cells=2000000;
  ModelSettings m;m.exposed_faces=exposed;
  auto b=test_fixture::rectangle(100,90,20,20,60);
  test_fixture::append(b,{x,97,x,103,x+6,103,x+6,97,x,97},obstacle_height);
  ModelInputs input(g,m,b);input.set_condition({5,270,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);w.applyParametrizations();
  PoissonOperator op(w);SolverState<float> state(op);
  state.begin(ConditionInputs(w),500,StopRule::FixedSweeps);state.advance(500);state.finalize(FaceDestination(w));
  std::array<double,3> values;int index=0;
  for(int i:{85,100,120}) {
    const auto f=w.domain.face(i,50,1);
    values[index++]=std::hypot(.5*(w.u[f]+w.u[f+1]),.5*(w.v[f]+w.v[f+w.domain.nx()]));
  }
  return values;
}
int main(int argc,char**) try {
  bool enforce=argc==1;
  for(auto scenario:{std::array<double,2>{4,150},{48,150},{4,120}}) {
    auto strict=run(false,scenario[0],scenario[1]),exposed=run(true,scenario[0],scenario[1]);
    std::cout<<"height "<<scenario[0]<<" x "<<scenario[1];
    for(int i=0;i<3;++i)std::cout<<" "<<strict[i]<<"/"<<exposed[i];std::cout<<std::endl;
    // F3 changes the pressure-corrected controls by <0.001 m/s; retain
    // the termination check without freezing unrelated roof-reference arithmetic.
    if(enforce && scenario[0]==48) {
      const double expected[]={.221810,2.09881,2.42385};
      for(int i=0;i<3;++i)if(std::abs(exposed[i]-expected[i])>1e-3)
        throw std::runtime_error("Tall obstacle wake changed");
    }
    if(enforce && scenario[1]==120) {
      const double expected[]={2.32239,2.34970,2.45106};
      for(int i=0;i<3;++i)if(std::abs(exposed[i]-expected[i])>1e-3)
        throw std::runtime_error("Touching obstacle wake changed");
    }
    if(enforce && scenario[0]==4 && scenario[1]==150)
      for(int i=0;i<3;++i)if(std::abs(strict[i]-exposed[i])>.15)throw std::runtime_error("Low obstacle terminates tower wake");
  }
} catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
