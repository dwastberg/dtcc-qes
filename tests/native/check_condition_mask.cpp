// S5c: condition labels may classify fluid but cannot open prepared solids.
#include "model_inputs.h"
#include "solver/solver.h"
#include "winds/WINDSGeneralData.h"
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#ifdef _OPENMP
#include <omp.h>
#endif
using namespace dtcc_qes;
using namespace dtcc_qes::solver;
static void require(bool ok,const char *message) {if(!ok)throw std::runtime_error(message);}
static BuildingArrays geometry() {
  BuildingArrays b;b.offsets={0};
  // Small crop of S5b downtown around the diagnosed corner. Metre coordinates
  // preserve odd-coordinate edges on the 2m raster and unequal roof heights.
  for(auto p:{std::array<double,5>{24,24,23,19,31},{53,24,17,18,24},{24,53,21,20,13},{53,53,22,22,18}}) {
    for(auto xy:{std::pair{p[0],p[1]},std::pair{p[0],p[1]+p[3]},std::pair{p[0]+p[2],p[1]+p[3]},std::pair{p[0]+p[2],p[1]},std::pair{p[0],p[1]}}) {
      b.vertices.push_back(xy.first);b.vertices.push_back(xy.second);
    }
    b.offsets.push_back(b.vertices.size()/2);b.ids.push_back(b.ids.size());b.heights.push_back(p[4]);b.base_heights.push_back(0);
  }return b;
}
static void check_mask(const WINDSGeneralData &w) {
  const auto &d=w.domain;
  for(int k=0;k<d.nz()-1;++k)for(int j=1;j<d.ny()-1;++j)for(int i=1;i<d.nx()-1;++i) {
    const auto c=d.cell(i,j,k);const auto original=w.icellflag_initial[c];
    if(original!=0 && original!=2)continue;
    require(w.icellflag[c]==original,"Parameterization relabeled a prepared solid/ground cell");
    const auto f=d.face(i,j,k);
    require(w.u0[f]==0 && w.u0[f+1]==0 && w.v0[f]==0 && w.v0[f+d.nx()]==0
         && w.w0[f]==0 && w.w0[f+d.nx()*d.ny()]==0,"A solid-owned initial face is not zero");
  }
}
template<class Real> static void repeated(bool stretched) {
  GridConfig g;g.nx=g.ny=48;g.nz=32;g.cell_size=2;
  if(stretched){g.dz_layers=std::vector<double>(16,1);g.dz_layers.insert(g.dz_layers.end(),16,3);}
  ModelSettings m;ModelInputs inputs(g,m,geometry());
  WINDSGeneralData w(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  const PoissonOperator op(w);SolverState<Real> state(op);
  std::vector<float> earlier;std::vector<int> flags;
  for(double dir:{225.,315.,270.,225.}) {
    inputs.set_condition({5,dir,10});w.resetICellFlag();w.applyWindProfile(inputs.inflow);w.applyParametrizations();check_mask(w);
    state.begin(ConditionInputs(w),10,StopRule::FixedSweeps);state.advance(10);state.finalize(FaceDestination(w));
    const auto &d=w.domain;
    for(int k=1;k<d.nz()-1;++k)for(int j=1;j<d.ny()-2;++j)for(int i=1;i<d.nx()-2;++i) {
      if(w.icellflag_initial[d.cell(i,j,k)]!=0)continue;
      const auto f=d.face(i,j,k);
      require(w.u[f]==0 && w.u[f+1]==0 && w.v[f]==0 && w.v[f+d.nx()]==0
           && w.w[f]==0 && w.w[f+d.nx()*d.ny()]==0,"Final reconstruction opened a solid-owned face");
    }
    if(dir==225.) {if(earlier.empty()){earlier=w.u;flags=w.icellflag;}else require(earlier==w.u && flags==w.icellflag,"Reused condition differs from its first zero start");}
    // Wall coefficients from initial geometry remain closed toward solids.
    for(int k=1;k<d.nz()-2;++k)for(int j=1;j<d.ny()-2;++j)for(int i=1;i<d.nx()-2;++i) {
      auto c=d.cell(i,j,k);if(w.icellflag[c]==0 || w.icellflag[c]==2)continue;
      auto a=op.stencil(c,k);const float coefficients[]={a.e,a.f,a.g,a.h,a.m,a.n};
      const int di[]={1,-1,0,0,0,0},dj[]={0,0,1,-1,0,0},dk[]={0,0,0,0,1,-1};
      for(int axis=0;axis<6;++axis){const int flag=w.icellflag[d.cell(i+di[axis],j+dj[axis],k+dk[axis])];
        if(flag==0 || flag==2)require(coefficients[axis]==0,"Fluid operator row points into a prepared solid");}
    }
  }
}
int main() try {
#ifdef _OPENMP
  omp_set_dynamic(0);omp_set_num_threads(2);
#endif
  GridConfig g;g.nx=g.ny=48;g.nz=32;g.cell_size=2;
  for(int roof:{0,1,2})for(int cavity:{0,1,2,3})for(int canyon:{0,1})for(int wake:{1,2})for(int side:{0,1})for(int high:{0,1}) {
    ModelSettings m;m.rooftop_flag=roof;m.upwind_cavity_flag=cavity;m.street_canyon_flag=canyon;
    m.wake_flag=wake;m.sidewall_flag=side;m.high_rise_flag=high;
    ModelInputs input(g,m,geometry());WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
    for(double dir:{225.,315.}){input.set_condition({5,dir,10});w.resetICellFlag();w.applyWindProfile(input.inflow);w.applyParametrizations();check_mask(w);}
  }
  repeated<float>(false);repeated<double>(false);repeated<float>(true);repeated<double>(true);
  std::cout<<"384 model combinations/directions preserve prepared solids and faces; repeated solves pass\n";
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
