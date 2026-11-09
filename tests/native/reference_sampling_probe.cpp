// Read-only reference-plane capture plus constitutive replay on one fixed mean.
#include "reference_sampling_candidate.h"
#include "model_inputs.h"
#include "log_sink.h"
#include "turbulence_reference.h"
#include "winds/TURBGeneralData.h"
#include "solver/solver.h"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>

using namespace dtcc_qes;
using V=reference_investigation::Vector;
using Tensor=std::array<float,6>;
static void require(bool ok,const char *why){if(!ok)throw std::runtime_error(why);}
template<class T> void number(T x){if(std::isfinite(double(x)))std::cout<<x;else std::cout<<"null";}
template<class T> void emit(const T& values){std::cout<<'[';bool first=true;for(auto x:values){if(!first)std::cout<<',';first=false;number(x);}std::cout<<']';}
template<class T> void read_vector(std::istream& in,std::vector<T>& values){std::size_t n;in>>n;require(bool(in)&&n<10000000,"Invalid vector length");values.resize(n);for(auto &v:values)in>>v;require(bool(in),"Truncated vector");}
static V velocity(const WINDSGeneralData& w,int i,int j,int k) {
  const auto &d=w.domain;const auto f=d.face(i,j,k);
  // Preserve native float face-pair addition before widening, as frictionVelocity does.
  return {.5*(w.u[f]+w.u[f+1]),.5*(w.v[f]+w.v[f+d.nx()]),.5*(w.w[f]+w.w[f+d.nx()*d.ny()])};
}
static bool fluid(const WINDSGeneralData& w,int i,int j,int k){const auto flag=w.icellflag[w.domain.cell(i,j,k)];return flag!=0 && flag!=2;}
struct References {
  int legacy=-1,count=0;double exact_mean=0;float legacy_mean=0;
  reference_investigation::Estimate interpolation;
};
static References references(const WINDSGeneralData& wind,float reference) {
  const auto &d=wind.domain;References out;
  out.legacy=int(std::lower_bound(d.z_face.begin(),d.z_face.end(),reference)-d.z_face.begin());
  require(out.legacy<int(d.z.size()),"Legacy reference has no cell");
  float sum=0,n=0;double wide=0;
  for(int j=0;j<d.ny()-1;++j)for(int i=0;i<d.nx()-1;++i)if(fluid(wind,i,j,out.legacy)) {
    auto v=velocity(wind,i,j,out.legacy);const double speed=std::sqrt(std::pow(v[0],2)+std::pow(v[1],2)+std::pow(v[2],2));
    sum+=speed;n++;wide+=speed;out.count++;
  }
  out.legacy_mean=sum/n;out.exact_mean=wide/out.count;
  const std::vector<float> centres(d.z.begin()+1,d.z.end());
  out.interpolation=reference_investigation::interpolate(centres,reference,(d.nx()-1)*(d.ny()-1),[&](int k,int c){
    const int i=c%(d.nx()-1),j=c/(d.nx()-1);
    return std::make_pair(fluid(wind,i,j,k+1),velocity(wind,i,j,k+1));
  });
  return out;
}
static void emit_reference(const References &r,const WINDSGeneralData& w) {
  std::cout<<"\"legacy_native_k\":"<<r.legacy<<",\"legacy_height\":"<<w.domain.z[r.legacy]
    <<",\"legacy_count\":"<<r.count<<",\"legacy_float_mean\":";number(r.legacy_mean);
  std::cout<<",\"legacy_double_mean\":";number(r.exact_mean);
  const auto &s=r.interpolation;
  std::cout<<",\"interpolation\":{\"supported\":"<<(s.supported?"true":"false")<<",\"lower\":"<<s.lower<<",\"upper\":"<<s.upper
    <<",\"weight\":"<<s.weight<<",\"count\":"<<s.count<<",\"float_mean\":";number(s.mean_float);
  std::cout<<",\"double_mean\":";number(s.mean_double);std::cout<<'}';
}
static float friction(float speed,float reference,float displacement,float roughness){return .4*speed/std::log((reference-displacement)/roughness);}
using Matrix=std::array<std::array<double,3>,3>;
static Matrix multiply(const Matrix&a,const Matrix&b){Matrix out{};for(int i=0;i<3;++i)for(int j=0;j<3;++j)out[i][j]=a[i][0]*b[0][j]+a[i][1]*b[1][j]+a[i][2]*b[2][j];return out;}
static Tensor replay(const std::array<float,14>&p,const std::array<double,5>&o,float bound) {
  const float k=std::min(p[12],bound),nu=p[10];
  const std::array<float,6> s={p[0],.5f*(p[1]+p[3]),.5f*(p[2]+p[6]),p[4],.5f*(p[5]+p[7]),p[8]};
  Tensor v;for(int c=0;c<6;++c)v[c]=float((c==0 || c==3 || c==5?(2./3.)*k:0.)-2.*(nu*s[c]));
  Matrix t{{{v[0],v[1],v[2]},{v[1],v[3],v[4]},{v[2],v[4],v[5]}}};
  const double c=o[0],sn=o[1];const Matrix q{{{c,-sn,0},{sn,c,0},{0,0,1}}},qt{{{c,sn,0},{-sn,c,0},{0,0,1}}};
  t=multiply(qt,multiply(t,q));for(int i=0;i<3;++i)t[i][i]=std::abs(o[i+2]*t[i][i]);t=multiply(q,multiply(t,qt));
  return {std::clamp(float(t[0][0]),-bound,bound),std::clamp(float(t[0][1]),-bound,bound),std::clamp(float(t[0][2]),-bound,bound),
    std::clamp(float(t[1][1]),-bound,bound),std::clamp(float(t[1][2]),-bound,bound),std::clamp(float(t[2][2]),-bound,bound)};
}
static void capture(std::istream& in) {
  GridConfig grid;ModelSettings model;BuildingArrays geometry;WindCondition condition;
  in>>grid.nx>>grid.ny>>grid.nz>>grid.cell_size>>grid.max_cells;
  in>>model.roughness_length>>model.sensor_x>>model.sensor_y>>model.exposed_faces>>model.wall_roughness;
  in>>model.rooftop_flag>>model.upwind_cavity_flag>>model.street_canyon_flag>>model.street_intersection_flag>>model.wake_flag>>model.high_rise_flag>>model.sidewall_flag;
  read_vector(in,grid.dz_layers);read_vector(in,geometry.vertices);read_vector(in,geometry.offsets);read_vector(in,geometry.ids);
  read_vector(in,geometry.heights);read_vector(in,geometry.base_heights);read_vector(in,geometry.ring_offsets);
  int kind;in>>condition.speed>>condition.direction>>condition.reference_height>>kind;
  condition.profile_kind=static_cast<ProfileKind>(kind);read_vector(in,condition.layer_u);read_vector(in,condition.layer_v);
  int iterations;double tolerance;in>>iterations>>tolerance;
  std::size_t n;in>>n;require(n<=4096,"Too many source cells");std::vector<std::array<int,3>> cells(n);
  for(auto &c:cells)in>>c[0]>>c[1]>>c[2];require(bool(in),"Truncated recipe");
  TurbulenceSettings settings;settings.enabled=true;ModelInputs inputs(grid,model,geometry,settings);
  WINDSGeneralData wind(make_domain(inputs),inputs.buildings,inputs.parameterizations,inputs.inflow.site_z0);
  solver::PoissonOperator poisson(wind,solver::CoefficientOwnership::Take);
  TURBGeneralData turb(inputs.turbulence,&wind);
  inputs.set_condition(condition);wind.resetICellFlag();wind.applyWindProfile(inputs.inflow);wind.applyParametrizations();
  solver::SolverState<double> workspace(poisson,tolerance,solver::default_order(),1.78f);
  workspace.begin(solver::ConditionInputs(wind),iterations);workspace.advance(iterations);workspace.finalize(solver::FaceDestination(wind));
  const auto diagnostics=workspace.diagnostics();require(diagnostics.converged,"Mean solve not converged");
  const auto &d=wind.domain;std::map<int,std::size_t> lookup;
  for(std::size_t i=0;i<n;++i) {
    auto c=cells[i];require(c[0]>=0 && c[0]<d.nx()-1 && c[1]>=0 && c[1]<d.ny()-1 && c[2]>=0 && c[2]<d.nz()-2,"Source outside domain");
    lookup.emplace(d.cell(c[0],c[1],c[2]+1),i);
  }
  std::vector<std::array<float,14>> properties(n);std::vector<std::array<double,5>> orientation(n);std::vector<bool> found(n,false);
  std::vector<Tensor> native_post(n);
  turb.production_observer=[&](int cell,float nu,float uncapped){auto at=lookup.find(cell);if(at!=lookup.end()){properties[at->second][10]=nu;properties[at->second][12]=uncapped;found[at->second]=true;}};
  turb.orientation_observer=[&](int cell,double c,double s){auto at=lookup.find(cell);if(at!=lookup.end())orientation[at->second]={c,s,turb.sigUConst,turb.sigVConst,turb.sigWConst};};
  turb.stress_observer=[&](int stage,int cell,const Tensor&value){auto at=lookup.find(cell);if(stage==1 && at!=lookup.end())native_post[at->second]=value;};
  turb.run();turb.production_observer={};turb.orientation_observer={};turb.stress_observer={};
  require(std::all_of(found.begin(),found.end(),[](bool v){return v;}),"Uncomputed requested source");
  const auto r=references(wind,turb.getReferenceHeight());
  require(float(r.interpolation.mean_double)==turb.getReferenceSpeed(),"Interpolated plane reduction differs from native reference");
  require(r.interpolation.supported,"No continuous reference support");
  const std::array<float,4> speed={r.legacy_mean,float(r.exact_mean),r.interpolation.mean_float,float(r.interpolation.mean_double)};
  std::array<float,4> stars,bounds;
  for(int a=0;a<4;++a){stars[a]=friction(speed[a],turb.getReferenceHeight(),turb.getDisplacementHeight(),turb.getRoughnessLength());bounds[a]=turb.getUpperBound()*stars[a]*stars[a];}
  std::cout<<"{\"schema\":\"native-reference-capture-v1\",\"iterations\":"<<diagnostics.iterations<<",\"reference_height\":"<<turb.getReferenceHeight()
    <<",\"roughness\":"<<turb.getRoughnessLength()<<",\"displacement\":"<<turb.getDisplacementHeight()<<',';emit_reference(r,wind);
  std::cout<<",\"speed\":";emit(speed);std::cout<<",\"friction_velocity\":";emit(stars);std::cout<<",\"bound\":";emit(bounds);
  std::cout<<",\"z\":";emit(std::vector<float>(d.z.begin()+1,d.z.end()));
  std::cout<<",\"z_faces\":";emit(std::vector<float>(d.z_face.begin()+1,d.z_face.end()));
  const std::set<int> planes={r.legacy,r.interpolation.lower+1,r.interpolation.upper+1};
  std::cout<<",\"planes\":[";bool first=true;
  for(int k:planes){if(!first)std::cout<<',';first=false;std::cout<<"{\"native_k\":"<<k<<",\"height\":"<<d.z[k]<<",\"vectors\":[";
    bool comma=false;for(int j=0;j<d.ny()-1;++j)for(int i=0;i<d.nx()-1;++i){if(comma)std::cout<<',';comma=true;emit(velocity(wind,i,j,k));}
    std::cout<<"],\"fluid\":[";comma=false;for(int j=0;j<d.ny()-1;++j)for(int i=0;i<d.nx()-1;++i){if(comma)std::cout<<',';comma=true;std::cout<<fluid(wind,i,j,k);}std::cout<<"]}";}
  std::cout<<"],\"sources\":[";
  for(std::size_t i=0;i<n;++i) {
    if(i)std::cout<<',';auto c=cells[i];const auto at=d.cell(c[0],c[1],c[2]+1);
    auto &p=properties[i];p[0]=turb.Gxx[at];p[1]=turb.Gxy[at];p[2]=turb.Gxz[at];p[3]=turb.Gyx[at];p[4]=turb.Gyy[at];p[5]=turb.Gyz[at];
    p[6]=turb.Gzx[at];p[7]=turb.Gzy[at];p[8]=turb.Gzz[at];p[9]=turb.Lm[at];p[11]=turb.tke[at];p[13]=bounds[3];
    const Tensor actual={turb.txx[at],turb.txy[at],turb.txz[at],turb.tyy[at],turb.tyz[at],turb.tzz[at]};
    std::cout<<"{\"cell\":";emit(c);std::cout<<",\"velocity\":";emit(velocity(wind,c[0],c[1],c[2]+1));
    std::cout<<",\"properties\":";emit(p);std::cout<<",\"orientation\":";emit(orientation[i]);std::cout<<",\"actual_stress\":";emit(actual);
    std::cout<<",\"post_anisotropy\":";emit(native_post[i]);std::cout<<",\"reconstruction\":";emit(replay(p,orientation[i],bounds[3]));
    std::cout<<",\"replays\":[";for(int a=0;a<4;++a){if(a)std::cout<<',';
      auto value=replay(p,orientation[i],bounds[a]);
      // If internal energy is unchanged, reuse the executed anisotropy stage:
      // only the final component cap changes, with no reconstruction roundoff.
      if(std::min(p[12],bounds[a])==p[11]){value=native_post[i];for(float &v:value)v=std::clamp(v,-bounds[a],bounds[a]);}
      emit(value);}std::cout<<"]}";
  }
  std::cout<<"]}\n";
}
static void manufactured() {
  std::cout<<"{\"schema\":\"reference-manufactured-v1\",\"cases\":[";bool first=true;
  for(double h:{.035,.0175,.00875,.004375})for(std::string field:{"affine","curved","turning","vertical"})for(int phase:{-1,0,1}) {
    GridConfig g;g.nx=g.ny=4;g.cell_size=h;g.max_cells=100000;
    const int count=int(std::round(.84/h));g.dz_layers.assign(count,h);
    if(phase){const int face=int(std::round(.21/h));g.dz_layers[face-1]+=phase*1e-6;g.dz_layers[face]-=phase*1e-6;}
    double top=.84,step=h;while(top<16){step*=1.2;const double take=std::min(step,16-top);g.dz_layers.push_back(take);top+=take;}g.nz=g.dz_layers.size();
    ModelSettings m;m.roughness_length=.0021;m.sensor_x=m.sensor_y=h/2;
    BuildingArrays b{{},{0},{},{},{}};ModelInputs input(g,m,b);WINDSGeneralData wind(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
    const auto &d=wind.domain;for(int k=0;k<d.nz();++k)for(int j=0;j<d.ny();++j)for(int i=0;i<d.nx();++i) {
      const auto f=d.face(i,j,k);const double z=d.z[std::min(k,int(d.z.size())-1)];
      wind.u[f]=field=="turning" || field=="vertical"?1:1+2*z+(field=="curved"?4*z*z:0);
      wind.v[f]=field=="turning"?20*(z-.21):0;wind.w[f]=field=="vertical"?.2+3*d.z_face[k]:0;
    }
    TURBGeneralData t(input.turbulence,&wind);auto r=references(wind,t.getReferenceHeight());
    require(float(r.interpolation.mean_double)==t.getReferenceSpeed(),"Manufactured interpolation differs from native");
    if(!first)std::cout<<',';first=false;std::cout<<"{\"spacing\":"<<h<<",\"field\":\""<<field<<"\",\"face_phase\":"<<phase<<",\"reference\":"<<t.getReferenceHeight()<<',';emit_reference(r,wind);std::cout<<'}';
  }
  std::cout<<"],\"constant_reductions\":[";first=true;
  const float u=1.312345f,v=-.2f,w=.3f;const double magnitude=std::sqrt(double(u)*u+double(v)*v+double(w)*w);
  for(int n:{16,192,11264,45056}) {
    auto estimate=reference_investigation::interpolate(std::vector<float>{.1f,.3f},.2,n,[&](int,int){return std::make_pair(true,V{u,v,w});});
    if(!first)std::cout<<',';first=false;std::cout<<"{\"columns\":"<<n<<",\"oracle\":"<<magnitude<<",\"float_mean\":"<<estimate.mean_float<<",\"double_mean\":"<<estimate.mean_double<<'}';
  }
  auto masked=reference_investigation::interpolate(std::vector<float>{.1f,.3f},.2,4,[](int k,int col){return std::make_pair(!(k==0 && col==0),V{1,0,0});});
  auto empty=reference_investigation::interpolate(std::vector<float>{.1f,.3f},.2,4,[](int,int){return std::make_pair(false,V{1,0,0});});
  auto below=reference_investigation::interpolate(std::vector<float>{.1f,.3f},.01,4,[](int,int){return std::make_pair(true,V{1,0,0});});
  auto a=turbulence_reference(std::vector<float>(64,.07f),.0019f),b=turbulence_reference(std::vector<float>(80,.07f),.0019f);
  std::cout<<"],\"support\":{\"masked_count\":"<<masked.count<<",\"empty_supported\":"<<(empty.supported?"true":"false")<<",\"below_supported\":"<<(below.supported?"true":"false")
    <<"},\"morphometric_references\":["<<a.reference_height<<','<<b.reference_height<<"]}\n";
}
int main(int argc,char **argv) {
  try {std::cout<<std::setprecision(17);Messages messages;BufferedLogSink sink(messages);
    if(argc==2 && std::string(argv[1])=="--manufactured")manufactured();
    else {require(argc==2,"Expected recipe path or --manufactured");std::ifstream input(argv[1]);require(bool(input),"Cannot open recipe");capture(input);}
  }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
