// Pure formula checks: no WindRunner, geometry preparation or native answers.
#include "CanyonJoin.h"
#include "dtcc/api/canyon_types.h"
#include "dtcc/api/canyon_contract.h"
#include <iostream>
#include <limits>

void require(bool ok,const char* message) { if(!ok) throw std::runtime_error(message); }
int main() {
  using joint_canyon::joined;
  require(dtcc_qes::canyon_model_parse("legacy")==dtcc_qes::CanyonModel::Legacy,"default selector");
  bool rejected=false;
  try { dtcc_qes::canyon_model_parse("guessed"); } catch(const std::invalid_argument&) { rejected=true; }
  require(rejected,"unknown selector must fail");
  dtcc_qes::CanyonOptions e;e.canyon_model=dtcc_qes::CanyonModel::JoinedV1;
  dtcc_qes::ModelSettings m;
  dtcc_qes::validate_canyon_contract(e,m,false);
  auto reject=[&](const dtcc_qes::CanyonOptions& options,const dtcc_qes::ModelSettings& model,bool turbulence) {
    bool failed=false;
    try { dtcc_qes::validate_canyon_contract(options,model,turbulence); }
    catch(const std::invalid_argument&) { failed=true; }
    require(failed,"stacked/incompatible candidate rejected before state attachment");
  };
  reject(e,m,true);
  e.canyon_baseline_turbulence=true;
  dtcc_qes::validate_canyon_contract(e,m,true,0);
  bool rejected_closure=false;
  try { dtcc_qes::validate_canyon_contract(e,m,true,1); }
  catch(const std::invalid_argument&) { rejected_closure=true; }
  require(rejected_closure,"AIJ baseline allowance cannot enable wall-distance turbulence");
  e.canyon_baseline_turbulence=false;
  m.high_rise_flag=1;reject(e,m,false);m.high_rise_flag=0;
  m.street_canyon_flag=0;reject(e,m,false);m.street_canyon_flag=1;
  e.canyon_model=static_cast<dtcc_qes::CanyonModel>(99);reject(e,m,false);
  const double x=5,W=10,s=3,b=5,A=-1,incident=2;
  const double f=std::pow(.25,.25),q0=-f;
  require(std::abs(joined(x,s,W,0,A,incident)-q0)<1e-14,"inner quarter-power anchor");
  require(joined(x,b,W,0,A,incident)==incident,"outer incident anchor");
  // At the old boundary y=4, t=1/2; h00=h01=1/2, h10=1/8.
  require(std::abs(joined(x,4,W,0,A,incident)-(1.-7.*f/16.))<1e-14,"independent midpoint/sign anchor");
  const double h=1e-6;
  const auto q=[&](double y) {return joined(x,y,W,0,A,incident);};
  require(std::abs((q(s)-q(s-h))/h-f/4)<1e-5,"retained inner derivative");
  require(std::abs((q(s+h)-q(s))/h-f/4)<1e-5,"bridge inner derivative");
  require(std::abs((q(b)-q(b-h))/h)<1e-5,"outer derivative");
  double last=q0;
  for(int i=0;i<=10000;++i) {
    const double y=s+(b-s)*i/10000.;
    const double value=q(y);
    require(value>=q0-1e-14 && value<=incident+1e-14 && value>=last-1e-14,"monotonic endpoint bounds");
    require(q(-y)==value,"transverse symmetry");last=value;
    const double angle=.71,c=std::cos(angle),t=std::sin(angle);
    require(std::abs(joined(x,y,W,0,A*c,incident*c)-value*c)<1e-14,"rigid rotation U");
    require(std::abs(joined(x,y,W,0,A*t,incident*t)-value*t)<1e-14,"rigid rotation V");
  }
  require(joined(0,0,W,0,-1,2)==-1,"finite zero-width bulk limit");
  require(joined(0,b,W,0,-1,2)==2,"finite zero-width edge limit");
  require(std::isfinite(joined(1e-12,b-1e-13,W,0,-1,2)),"shrinking layer finite limit");
  require(joined(x,1,W,0,A,incident)==joint_canyon::core(x,1,W)*A,"bulk exact retention");
  rejected=false;try { joined(20,1,10,0,-1,2); } catch(const std::invalid_argument&) {rejected=true;}
  require(rejected,"collapsed support rejection");
  rejected=false;try { joined(1,1,0,0,-1,2); } catch(const std::invalid_argument&) {rejected=true;}
  require(rejected,"zero span rejection");
  rejected=false;try { joined(1,1,10,0,std::numeric_limits<double>::quiet_NaN(),2); } catch(const std::invalid_argument&) {rejected=true;}
  require(rejected,"nonfinite rejection");
  std::cout<<"canyon join: anchors, signs, derivatives, bounds, symmetry, rotation and limits passed\n";
}
