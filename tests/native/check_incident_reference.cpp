#include "building_fixtures.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "winds/PolyBuilding.h"
#include <array>
#include <iostream>
#include <stdexcept>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static std::vector<float> run(int wake,bool reversed,bool isolated,bool enforce) {
  GridConfig g;g.nx=150;g.ny=100;g.nz=70;g.cell_size=2;
  ModelSettings m;m.wake_flag=wake;
  auto b=test_fixture::empty_buildings();
  auto low=[&]{test_fixture::append(b,{84,94,84,106,94,106,94,94,84,94},8);};
  auto tower=[&]{test_fixture::append(b,{100,84,100,116,130,116,130,84,100,84},90);};
  if(reversed)low();if(!isolated)tower();if(!reversed)low();
  ModelInputs input(g,m,b);input.set_condition({5,270,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);
  std::vector<std::array<double,2>> incident;
  for(auto *building:w.allBuildingsV) {
    auto f=w.domain.face(building->i_building_cent,building->j_building_cent,building->k_end);
    incident.push_back({w.u0[f],w.v0[f]});
  }
  w.applyParametrizations({},[&](const char *stage,int id) {
    auto *building=w.allBuildingsV[id];
    if(enforce && (isolated || std::string(stage)=="cavity"))
      if(building->u0_h!=incident[id][0] || building->v0_h!=incident[id][1])
        throw std::runtime_error(std::string("Contaminated incident reference at ")+stage);
  });
  const auto initial=w.u0;
  PoissonOperator op(w);SolverState<float> state(op);
  state.begin(ConditionInputs(w),500,StopRule::FixedSweeps);state.advance(500);state.finalize(FaceDestination(w));
  double sum=0;int count=0;
  for(int j=47;j<53;++j)for(int i=30;i<42;++i) {
    auto f=w.domain.face(i,j,1);sum+=.5*(w.u[f]+w.u[f+1]);++count;
  }
  std::cout<<"wake "<<wake<<" reverse "<<reversed<<" isolated "<<isolated<<" upwind u "<<sum/count<<std::endl;
  if(enforce && sum<=0)throw std::runtime_error("Low-building upwind strip reversed");
  return initial;
}
static void profile_checks() {
  GridConfig g;g.nx=g.ny=40;g.nz=24;
  ModelInputs input(g,{},test_fixture::rectangle(30,30,12,12,8));
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  for(int scenario=0;scenario<3;++scenario) {
    WindCondition condition;condition.direction=195;condition.speed=scenario==1?0:5;
    if(scenario==2) {
      condition.profile_kind=ProfileKind::LayerTable;
      for(int k=0;k<g.nz;++k) {condition.layer_u.push_back(std::cos(k*.2)*5);condition.layer_v.push_back(std::sin(k*.2)*5);}
    }
    input.set_condition(condition);w.resetICellFlag();w.applyWindProfile(input.inflow);
    auto *b=w.allBuildingsV[0];const auto f=w.domain.face(b->i_building_cent,b->j_building_cent,b->k_end);
    const double u=w.u0[f],v=w.v0[f];
    const float direction=(u==0 && v==0)?float((270.-195)*std::acos(-1)/180):float(std::atan2(v,u));
    w.applyParametrizations();
    if(b->incident_u!=u || b->incident_v!=v || b->incident_dir!=direction)
      throw std::runtime_error("Incident reference lost profile height, calm direction or condition reset");
  }
}
int main(int argc,char**) try {
  bool enforce=argc==1;
  profile_checks();
  for(int wake:{2,3}) {
    run(wake,false,true,enforce);
    auto a=run(wake,false,false,enforce),b=run(wake,true,false,enforce);
    if(enforce && a!=b)throw std::runtime_error("Initial field depends on building input order");
  }
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
