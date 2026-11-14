#include "building_fixtures.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include "winds/TURBGeneralData.h"
#include "dtcc/turbulence.h"
#include "dtcc/api/stress_validity.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
int main() try {
  GridConfig g;g.nx=70;g.ny=60;g.nz=40;g.cell_size=2;
  for(auto condition:{std::array<double,2>{270,5},{225,5},{247.5,5},{270,0}}) {
    const double direction=condition[0];
    ModelInputs input(g,{},test_fixture::rectangle(50,50,20,20,20));input.set_condition({condition[1],direction,10});
    WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
    w.applyWindProfile(input.inflow);w.applyParametrizations();
    PoissonOperator op(w);SolverState<float> state(op);state.begin(ConditionInputs(w),300,StopRule::FixedSweeps);
    state.advance(300);state.finalize(FaceDestination(w));
    TURBGeneralData turb(input.turbulence,&w);
    std::vector<StressTensor> raw(w.domain.numCellCentered());
    turb.stress_observer=[&](int stage,int cell,const StressTensor &stress) {if(stage==1)raw[cell]=stress;};
    const auto wind=w.u;
    turb.run();
    if(w.u!=wind)throw std::runtime_error("Limiter changed mean wind");
    const auto output=turbulence_fields(turb,g);
    size_t spectral_count=0,energy_count=0,capped_count=0;
    const double bound=turb.getUpperBound()*turb.getFrictionVelocity()*turb.getFrictionVelocity();
    double maximum=0;
    for(int cell:turb.icellfluid) {
      StressTensor stress{turb.txx[cell],turb.txy[cell],turb.txz[cell],turb.tyy[cell],turb.tyz[cell],turb.tzz[cell]};
      const double radius=stress_validity(stress).spectral_radius;
      maximum=std::max(maximum,bound>0?radius/bound:radius);
      const bool spectral=bound>0 && turb.spectralScale[cell]<1;
      const bool energy=bound>0 && turb.energyCapped[cell];
      const bool capped=spectral||energy;
      spectral_count+=spectral;energy_count+=energy;capped_count+=capped;
      const auto physical=cell-g.nx*g.ny;
      if((output.state[physical]==2)!=capped)throw std::runtime_error("Export guessed cap activity");
      const int plane=(w.domain.nx()-1)*(w.domain.ny()-1);
      const int k=cell/plane,j=(cell%plane)/(w.domain.nx()-1),i=cell%(w.domain.nx()-1);
      const auto sample=turbulence_sample(turb,w,{w.domain.x[i],w.domain.y[j],w.domain.z[k]});
      if(!sample.computed || sample.capped!=capped)throw std::runtime_error("Probe cap activity differs from cell");
      for(int n=0;n<6;++n)
        if(stress[n]!=float(double(raw[cell][n])*turb.spectralScale[cell]))
          throw std::runtime_error("Limiter changed an inactive cell or tensor shape");
      const double angle=(270.-direction)*std::acos(-1)/180;
      const double u=std::cos(angle),v=std::sin(angle);
      if(u*u*stress[0]+2*u*v*stress[1]+v*v*stress[3]>bound*(1+2e-6))
        throw std::runtime_error("Streamwise variance exceeds cap");
    }
    if(output.capped_cells!=capped_count || output.spectral_limited_cells!=spectral_count
       || output.energy_capped_cells!=energy_count)throw std::runtime_error("Cap activity counts differ");
    if(bound==0 && capped_count)throw std::runtime_error("Calm flow reported capped");
    std::cout<<direction<<" maximum spectral radius / B "<<maximum<<std::endl;
    if(maximum>1+2e-6)throw std::runtime_error("Directional variance exceeds cap");
  }
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
