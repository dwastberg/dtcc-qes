#include "model_inputs.h"
#include "wind_runner.h"
#include "winds/WINDSGeneralData.h"
#include <cmath>
#include <stdexcept>
#include <limits>
using namespace dtcc_qes;
static void require(bool ok,const char *why) { if(!ok) throw std::runtime_error(why); }
template<class F> void rejects(F f) {
  try { f(); } catch(const std::invalid_argument &) { return; }
  throw std::runtime_error("Malformed table accepted");
}
int main() {
  GridConfig g; g.nx=6; g.ny=6; g.nz=5; g.dz_layers={1,2,9,8,20};
  ModelSettings m; m.sensor_x=m.sensor_y=3;
  const BuildingArrays empty{{},{0},{},{},{}};
  ModelInputs inputs(g,m,empty);
  WindCondition p; p.profile_kind=ProfileKind::LayerTable;
  p.layer_u={1,3,9,4,2}; p.layer_v={0,-1,0,1,0}; p.speed=4;
  inputs.set_condition(p);
  p.layer_u[0]=99;
  require(inputs.inflow.layer_u.front()==1,"Inputs borrowed condition table");
  p.layer_u[0]=1;
  WINDSGeneralData field(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  field.applyWindProfile(inputs.inflow);
  const auto &d=field.domain;
  for(int k=0;k<d.nz();++k) for(int j=0;j<d.ny();++j) for(int i=0;i<d.nx();++i) {
    auto index=d.face(i,j,k);
    bool physical=k>0 && k<d.nz()-1;
    require(field.u0[index]==(physical?p.layer_u[k-1]:0),"Wrong layer/ghost u");
    require(field.v0[index]==(physical?p.layer_v[k-1]:0),"Wrong layer/ghost v");
    require(field.w0[index]==0,"Wrong w");
  }
  require(std::abs(field.max_velmag-10.8f)<1e-5,"Interior maximum omitted");
  const auto before=inputs.inflow;
  auto bad=p; bad.layer_u.pop_back(); rejects([&]{inputs.set_condition(bad);});
  bad=p; bad.layer_v[1]=std::numeric_limits<double>::infinity(); rejects([&]{inputs.set_condition(bad);});
  bad=p; bad.layer_u[1]=1e40; rejects([&]{inputs.set_condition(bad);});
  bad=p; bad.profile_kind=static_cast<ProfileKind>(99); rejects([&]{inputs.set_condition(bad);});
  bad=p; bad.profile_kind=ProfileKind::Log; rejects([&]{inputs.set_condition(bad);});
  bad=p; bad.reference_height=0; rejects([&]{inputs.set_condition(bad);});
  require(inputs.inflow.layer_u==before.layer_u && inputs.inflow.site_U_ref==before.site_U_ref,"Failed table replaced active condition");
  inputs.set_condition(WindCondition{});
  require(inputs.inflow.layer_u.empty(),"Table leaked into legacy log");
  TurbulenceSettings t; t.enabled=true;
  ModelInputs with_turb(g,m,empty,t); with_turb.set_condition(p);
  require(with_turb.inflow.layer_u==before.layer_u,"Turbulence rejected layer table");
  Messages messages; WindRunner reused; reused.prepare(g,m,empty,messages);
  SolverOptions options;
  for(auto precision:{"float32","float64"}) {
    options.precision=precision;
    for(auto condition:{p,WindCondition{},p}) {
      WindRunner fresh; fresh.prepare(g,m,empty,messages);
      auto expected=fresh.solve(condition,options,messages);
      auto actual=reused.solve(condition,options,messages);
      require(actual.velocity==expected.velocity,"Repeated table differs from fresh runner");
    }
  }
}
