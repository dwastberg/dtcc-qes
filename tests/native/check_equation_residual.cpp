// Independent dense-row oracle for the completed-iterate diagnostic.
#include "solver/solver.h"
#include "model_inputs.h"
#include "winds/WINDSGeneralData.h"
#include <cmath>
#include <cstring>
#include <limits>
#include <stdexcept>
#ifdef _OPENMP
#include <omp.h>
#endif
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void require_check(bool ok,int line) { if (!ok) throw std::runtime_error("Equation residual check failed at line "+std::to_string(line)); }
#define check(ok) require_check((ok),__LINE__)
static void close(double a,double b) { check(std::abs(a-b)<=2e-12*std::max(1.,std::abs(b))); }
template<class F> static void rejects(F f) { bool caught=false;try { f(); } catch(const std::exception &) { caught=true; } check(caught); }
template<class T> static bool bits(const std::vector<T> &a,const std::vector<T> &b) {
  return a.size()==b.size() && std::memcmp(a.data(),b.data(),a.size()*sizeof(T))==0;
}
template<class Real> static void oracle(bool stretched,OperatorStorage storage,SweepOrder order) {
  GridConfig g;g.nx=8;g.ny=7;g.nz=8;g.cell_size=2;
  if(stretched) g.dz_layers={.5,.5,.75,1,1.5,2,3,4};
  ModelSettings m; m.sensor_x=m.sensor_y=2;
  BuildingArrays buildings;buildings.offsets={0};
  ModelInputs input(g,m,buildings);input.set_condition({5,225,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);
  const auto &d=w.domain;w.u0[d.face(3,3,2)]+=.4f;
  // A solid row stays in the iteration but is excluded from fluid diagnostics.
  w.icellflag[d.cell(3,3,3)]=0;
  PoissonOperator op(w,storage);SolverState<Real> s(op,1e-5,order), control(op,1e-5,order);
  rejects([&]{s.equation_residual();});rejects([&]{s.diagnose_cell(2,2,0);});
  s.begin(ConditionInputs(w),17,StopRule::FixedSweeps);control.begin(ConditionInputs(w),17,StopRule::FixedSweeps);
  const auto initial=s.equation_residual();
  close(*initial.relative_maximum,1);close(*initial.relative_volume_weighted_rms,1);
  const auto bytes=s.workspace_bytes();
  for(int work : {0,1,6,10}) {
    s.advance(work,true);control.advance(work);
    const auto before=s.copy_state_for_study();
    const auto out=s.equation_residual();
    // Assemble A rows independently with explicit linear indices. Multiply the
    // dense row by the copied CURRENT vector, including prescribed lateral/top
    // values and the already refreshed ground ghost. No diagnostic helpers.
    const int nx=d.nx()-1,ny=d.ny()-1,plane=nx*ny;
    double maximum=0,square=0,bmax=0,bsquare=0,volume=0;std::size_t count=0,solids=0;
    const auto idx=[&](int i,int j,int k){return i+j*nx+k*plane;};
    for(int k=1;k<d.nz()-2;++k) for(int j=1;j<ny-1;++j) for(int i=1;i<nx-1;++i) {
      const int c=idx(i,j,k);
      if(w.icellflag[c]==0 || w.icellflag[c]==2) {++solids;continue;}
      const double coeff[]={w.e[c],w.f[c],w.g[c],w.h[c],w.m[c],w.n[c]};
      const int offsets[]={1,-1,nx,-nx,plane,-plane};
      std::vector<double> row(before.multipliers.size(),0);
      for(int a=0;a<6;++a) {row[c]+=coeff[a];row[c+offsets[a]]-=coeff[a];}
      double product=0;for(std::size_t n=0;n<row.size();++n) product+=row[n]*double(before.multipliers[n]);
      const double r=-double(before.rhs[c])-product,b=double(before.rhs[c]);
      const double v=double(d.dx())*d.dy()*d.dz_array[k];
      maximum=std::max(maximum,std::abs(r));bmax=std::max(bmax,std::abs(b));
      square+=v*r*r;bsquare+=v*b*b;volume+=v;++count;
      const auto cell=s.diagnose_cell(i,j,k-1);close(cell.equation_residual,r);check(cell.assessed);
      check(cell.top_band==(k==d.nz()-3));
      if(k==1) close(cell.neighbour_multipliers[5],cell.multiplier);
      if(i==1) close(cell.neighbour_multipliers[1],0);
      if(k==d.nz()-3) close(cell.neighbour_multipliers[4],0);
    }
    close(out.maximum,maximum);close(out.volume_weighted_rms,std::sqrt(square/volume));
    close(out.rhs_maximum,bmax);close(out.rhs_volume_weighted_rms,std::sqrt(bsquare/volume));
    close(*out.relative_maximum,maximum/bmax);close(*out.relative_volume_weighted_rms,std::sqrt(square/bsquare));
    check(out.fluid_cells==count && out.excluded_solid_cells==solids && out.iteration==s.diagnostics().iterations);
    const auto empty=s.equation_residual({1,1,1,2,0,1});check(!empty.fluid_cells && !empty.relative_maximum);
    const auto excluded=s.equation_residual({3,4,3,4,2,3});check(excluded.excluded_solid_cells==1 && !excluded.relative_maximum);
    check(!s.diagnose_cell(3,3,2).assessed);
    const auto after=s.copy_state_for_study(),expected=control.copy_state_for_study();
    check(bits(before.rhs,after.rhs) && bits(before.multipliers,after.multipliers));
    check(bits(after.multipliers,expected.multipliers) && bits(after.rhs,expected.rhs));
    check(s.workspace_bytes()==bytes);
  }
  rejects([&]{s.equation_residual({}, {0,1});});rejects([&]{s.equation_residual({}, {1,std::nan("")});});
  rejects([&]{s.equation_residual({0,2,1,2,0,1});});rejects([&]{s.diagnose_cell(0,1,0);});rejects([&]{s.diagnose_cell(1,1,g.nz-1);});
  const auto result=s.equation_residual();s.finalize(FaceDestination(w));close(result.maximum,s.equation_residual().maximum);
  // Restart zeros the iterate and normalizer is recomputed for the new RHS.
  std::fill(w.u0.begin(),w.u0.end(),0);std::fill(w.v0.begin(),w.v0.end(),0);std::fill(w.w0.begin(),w.w0.end(),0);
  s.begin(ConditionInputs(w),1,StopRule::FixedSweeps);s.advance(1);
  const auto calm=s.equation_residual({}, {1e-20,1e-18});
  check(calm.maximum==0 && calm.rhs_maximum==0 && *calm.relative_maximum==0);
  // Negative misuse case: borrowed inputs may not mutate. Even then, an
  // invalid face must fail the diagnostic, never produce plausible evidence.
  w.u0[d.face(2,2,1)]=std::numeric_limits<float>::quiet_NaN();rejects([&]{s.diagnose_cell(2,2,0);});
}
static void nonfinite_rhs() {
  WINDSGeneralData w(qes::Domain(6,6,6,1,1,1));
  std::fill(w.e.begin(),w.e.end(),std::numeric_limits<float>::max());
  std::fill(w.u0.begin(),w.u0.end(),std::numeric_limits<float>::max());
  PoissonOperator op(w,OperatorStorage::Explicit);SolverState<float> s(op);
  s.begin(ConditionInputs(w),1,StopRule::FixedSweeps);
  rejects([&]{s.equation_residual();}); // finite inputs, overflowing stored RHS
}
int main() {
#ifdef _OPENMP
  omp_set_dynamic(0);omp_set_num_threads(2);
#endif
  for(bool stretched : {false,true}) for(auto storage : {OperatorStorage::Automatic,OperatorStorage::Explicit})
    for(auto order : {SweepOrder::RedBlack,SweepOrder::Lexicographic}) {
      oracle<float>(stretched,storage,order);oracle<double>(stretched,storage,order);
    }
  nonfinite_rhs();
}
