#include "building_fixtures.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "winds/TURBGeneralData.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void close(double actual,double expected,const char *message) {
  if(!std::isfinite(actual) || std::abs(actual-expected)>1e-5*std::max(1e-4,std::abs(expected)))
    throw std::runtime_error(std::string(message)+" actual="+std::to_string(actual)+" expected="+std::to_string(expected));
}
static void manufactured(bool stretched,int kind) {
  GridConfig g;g.nx=g.ny=30;g.nz=24;
  if(stretched){g.dz_layers={.5,1.,1.5,2.};g.dz_layers.resize(g.nz,2.);}
  ModelInputs input(g,{},test_fixture::empty_buildings());
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,.1);
  auto &d=w.domain;
  const auto value=[&](double z) {return kind==0?std::log((z+.1)/.1):kind==1?3.:z;};
  for(int k=1;k<int(d.z.size());++k)for(int j=0;j<d.ny();++j)for(int i=0;i<d.nx();++i) {
    auto f=d.face(i,j,k);w.u[f]=2*value(d.z[k]);w.v[f]=-1.5*value(d.z[k]);
  }
  TURBGeneralData turb(input.turbulence,&w);turb.derivativeVelocity();
  for(int k:{1,2}) {
    double gradient=kind==0?1/(d.z[k]+.1):0;
    if(kind==2) {int upper=k+1;gradient=(d.z[upper]-d.z[1])/((d.z[k]+.1)*std::log((d.z[upper]+.1)/(d.z[1]+.1)));}
    auto c=d.cell(10,10,k);
    std::cout<<"manufactured stretched "<<stretched<<" kind "<<kind<<" k "<<k<<std::endl;
    close(turb.Gxz[c],2*gradient,"Ground dU/dz violates profile oracle");
    close(turb.Gyz[c],-1.5*gradient,"Ground dV/dz violates profile oracle");
  }
}
static void roof_and_gap(bool gap) {
  GridConfig g;g.nx=g.ny=30;g.nz=24;
  ModelSettings settings;settings.exposed_faces=gap;
  ModelInputs input(g,settings,test_fixture::rectangle(20,20,20,20,8));
  // The public flat-ground bridge rejects elevated bases; construct this
  // overhang directly at the core boundary to test the unavailable stencil.
  input.buildings[0].base_height=gap?2.1f:0;
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,.1);auto &d=w.domain;
  const double roof=gap?10.1:8;
  for(int k=1;k<int(d.z.size());++k)for(int j=0;j<d.ny();++j)for(int i=0;i<d.nx();++i) {
    const auto f=d.face(i,j,k);
    w.u[f]=d.z[k]>roof?-2*std::log((d.z[k]-roof)/.1):2*std::log((d.z[k]+.1)/.1);
    w.v[f]=-.75*w.u[f];
  }
  const int k=w.allBuildingsV[0]->k_end;
  const auto f=d.face(15,15,k);
  const float roof_expected=(.5*(w.u[f+d.nx()*d.ny()]+w.u[f+1+d.nx()*d.ny()])-.5*(w.u[f]+w.u[f+1]))/(d.z[k+1]-d.z[k]);
  if(gap) {
    const auto above=d.face(15,15,2);
    w.u[above]=w.u[above+1]=w.v[above]=w.v[above+d.nx()]=std::numeric_limits<float>::quiet_NaN();
  }
  TURBGeneralData turb(input.turbulence,&w);turb.derivativeVelocity();
  if(turb.Gxz[d.cell(15,15,k)]!=roof_expected)throw std::runtime_error("Roof derivative changed");
  if(gap) {
    const auto ground=d.face(15,15,1);
    const double expected=w.u[ground]/((d.z[1]+.1)*std::log((d.z[1]+.1)/.1));
    close(turb.Gxz[d.cell(15,15,1)],expected,"One-cell gap used a solid velocity");
  }
}
static void solver_profile(double spacing,bool stretched) {
  GridConfig g;g.nx=g.ny=24;g.nz=24;g.cell_size=spacing;
  if(stretched){g.dz_layers={.5,.75,1.,1.25,1.5};g.dz_layers.resize(g.nz,2.);}
  ModelSettings settings;settings.sensor_x=settings.sensor_y=5;
  ModelInputs input(g,settings,test_fixture::empty_buildings());input.set_condition({5,270,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,.1);auto &d=w.domain;
  w.applyWindProfile(input.inflow);w.applyParametrizations();
  PoissonOperator op(w);SolverState<float> state(op);state.begin(ConditionInputs(w),100,StopRule::FixedSweeps);state.advance(100);state.finalize(FaceDestination(w));
  TURBGeneralData turb(input.turbulence,&w);turb.run();
  double last_intensity=1e100;
  for(int k=1;k<d.nz()-2;++k) {
    const auto c=d.cell(10,10,k);const double z=d.z[k];
    const auto log=[](double z){return std::log((z+.1)/.1);};
    double gradient=1/(z+.1);
    if(k>2) {
      const double a=z-d.z[k-1],b=d.z[k+1]-z;
      gradient=-b/(a*(a+b))*log(d.z[k-1])+(b-a)/(a*b)*log(z)+a/(b*(a+b))*log(d.z[k+1]);
    }
    const double expected=2.5*.4*z*5/std::log(10.1/.1)*gradient;
    const double sigma=std::sqrt(turb.txx[c]);
    if(std::abs(sigma/expected-1)>.02)throw std::runtime_error("Empty-domain sigma differs from scoped gradient and mixing-length prediction");
    const double intensity=sigma/w.u[d.face(10,10,k)];
    if(intensity>last_intensity+1e-6)throw std::runtime_error("Undisturbed intensity not monotone");
    last_intensity=intensity;
    if(k<=2)std::cout<<"spacing "<<spacing<<" stretched "<<stretched<<" z "<<z<<" sigma/uStar "<<sigma/turb.getFrictionVelocity()<<std::endl;
  }
}
int main() try {
  for(bool stretched:{false,true})for(int kind=0;kind<3;++kind)manufactured(stretched,kind);
  roof_and_gap(false);roof_and_gap(true);
  solver_profile(2,false);solver_profile(1,false);solver_profile(2,true);
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
