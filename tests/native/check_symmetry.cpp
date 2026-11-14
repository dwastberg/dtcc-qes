#include "symmetry_helpers.h"
int main(int argc,char **argv) try {
  // Eight facade normals, including the formerly unwrapped south-west normal.
  const double pi=std::acos(-1);
  for(int n=-1;n<=6;++n) {
    float normal=n*pi/4;
    const float gamma=cavityFrame(normal);
    // At half-quadrant boundaries float rounding can select either adjacent
    // grid component; both frames must represent the same facade modulo pi/2.
    if(normal>pi || normal < -pi || std::abs(std::sin(4*gamma)-std::sin(4*n*pi/4))>2e-6)
      throw std::runtime_error("Invalid cavity frame for 45-degree normal");
  }
  for(double angle:{-0.3,0.3,4.5}) {
    float normal=angle;
    const float gamma=cavityFrame(normal);
    if(std::abs(std::sin(4*gamma)-std::sin(4*angle))>2e-6)
      throw std::runtime_error("Cavity frame discarded facade angle");
  }
  GridConfig g; g.nx=g.ny=100; g.nz=45; g.cell_size=2;
  const bool enforce=argc<2 || std::string(argv[1])!="--report";
  for(auto parameters:{std::array<double,2>{70,200},{20,250},{0,180},{0,185}}) {
    auto b=test_fixture::rectangle(80,80,40,40,30);
    const double angle=parameters[0]*std::acos(-1)/180;
    for(size_t n=0;n<b.vertices.size();n+=2) {
      double x=b.vertices[n]-100,y=b.vertices[n+1]-100;
      b.vertices[n]=100+x*std::cos(angle)-y*std::sin(angle);
      b.vertices[n+1]=100+x*std::sin(angle)+y*std::cos(angle);
    }
    auto off=check(g,b,parameters[1],0),on=check(g,b,parameters[1],2);
    std::cout<<parameters[0]<<","<<parameters[1]<<" initial off/on "<<off[0]<<" "<<on[0]
             <<" final off/on "<<off[1]<<" "<<on[1]<<std::endl;
    if(enforce && on[0]>off[0]+0.01) throw std::runtime_error("Upwind cavity increases point-mirror error");
  }
} catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
