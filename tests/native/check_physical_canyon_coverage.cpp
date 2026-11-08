#include "PhysicalCanyonCoverage.h"
#include <iostream>
#include <stdexcept>
using namespace physical_canyon;
namespace cov=physical_canyon::coverage;
static void require(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
static Polygon rectangle(int id,double x0,double x1,double y0=0,double y1=16,double roof=10) {
  return {id,{{x0,y0},{x0,y1},{x1,y1},{x1,y0},{x0,y0}},{0,5},0,roof};
}
static double area(const std::vector<cov::Region> &regions) {
  double result=0;for(const auto &r:regions)result+=cov::area(r.polygon());return result;
}
int main() {
  try {
    const std::vector<Polygon> pair{rectangle(49,-12,0),rectangle(50,20,32,0,16,14)};
    auto regions=cov::regions(pair,0,2,{1,0},2,30,1.8);
    require(regions.size()==1 && std::abs(area(regions)-320)<1e-12,"Physical ribbon area wrong");
    for(double scale:{1e-20,1e20})
      require(std::abs(area(cov::regions(pair,0,2,{scale,0},2,30,1.8))-320)<1e-12,"Direction magnitude changed physical coverage");
    const auto &r=regions[0];
    auto interval=cov::vertical_interval(r,0,10,-1,1);
    require(interval[0]==0 && interval[1]==1,"Partial end face interval wrong");
    auto a=cov::vertical(0,10,interval[0],interval[1],1,3,[](Point,double,double &v){v=2;return true;});
    require(a.valid && std::abs(a.area-2)<1e-14 && std::abs(a.value-4)<1e-14,"Vertical face integral wrong");
    for(int degree=0;degree<=5;++degree) {
      auto q=cov::vertical(0,10,0,1,0,1,[&](Point p,double z,double &v){v=std::pow(p[1],degree)*std::pow(z,degree);return true;});
      require(std::abs(q.value-1./((degree+1)*(degree+1)))<1e-14,"Gaussian polynomial moment wrong");
    }
    const auto p=cov::rectangle(r.polygon(),9,0,11,2);
    auto q=cov::horizontal(r,p,2,[](Point p,double,double &v){v=p[0]*p[0]*p[1];return true;});
    require(std::abs(q.area-4)<1e-13 && std::abs(q.value-1204./3)<1e-11,"Clipped polygon quadrature wrong");
    require(!cov::vertical(0,10,0,1,1,3,[](Point,double,double &){return false;}).valid,"Unsupported quadrature fabricated a value");
    auto blend=cov::blend({true,1,-4},4,4);
    require(blend.valid && blend.fraction==.25 && blend.value==2,"Incoming face remainder lost");
    blend=cov::blend({true,2,-8},4,4);
    require(blend.valid && blend.fraction==.5 && blend.value==0,"Disjoint pieces blended sequentially");
    blend=cov::blend({true,5,-20},4,4);
    require(!blend.valid && blend.value==4,"Overlapping coverage changed the incoming face");
    require(!cov::blend({false,1,2},4,4).valid && !cov::blend({true,1,NAN},4,4).valid,"Invalid integral accepted");
    // An explicit geometric partition checks boundary ownership independently
    // of any reference-sampling partition or velocity formulation.
    // The local transverse origin is y=16, so physical y=8 has eta=-8.
    std::array<cov::Region,2> parts{r,r};parts[0].hi=-8;parts[1].lo=-8;
    require(std::abs(cov::area(parts[0].polygon())+cov::area(parts[1].polygon())-320)<1e-12,
      "Partition changed physical area");
    double length=0;for(const auto &part:parts) {
      const auto x=cov::vertical_interval(part,1,8,0,20);length+=x[1]-x[0];
    }
    require(std::abs(length-20)<1e-12,"Normal face counted twice at an internal partition");
    auto oblique=cov::regions(pair,0,2,{1,.2},2,30,1.8);
    require(std::abs(area(oblique)-240)<1e-10,"Oblique finite span lost visibility");
    auto blocked=pair;blocked.push_back(rectangle(3,8,10,4,12,4));
    require(std::abs(area(cov::regions(blocked,0,2,{1,0},2,30,1.8))-224)<1e-12,"Near obstacle skipped");
    require(std::abs(area(cov::regions(blocked,0,2,{1,0},6,30,1.8))-320)<1e-12,"Height-dependent visibility wrong");
    blocked.push_back(rectangle(4,8,10,4,12,4));
    require(std::abs(area(cov::regions(blocked,0,2,{1,0},2,30,1.8))-160)<1e-12,"Ambiguous obstacle filled through");
    require(cov::regions(pair,0,2,{1,0},10,30,1.8).empty(),"Common roof became a normal interface owner");
    require(cov::regions(pair,0,2,{1,0},2,19,1.8).empty(),"Physical reach enlarged");
    require(cov::regions(pair,0,2,{1,0},2,30,20).empty(),"Minimum resolved gap ignored");
    bool limited=false;
    try {
      auto complex=pair;
      for(int id=0;id<cov::maximum_edges;++id)complex.push_back(rectangle(id+100,8,10));
      cov::regions(complex,0,2,{1,0},2,30,1.8);
    } catch(const std::length_error &){limited=true;}
    require(limited,"Coverage complexity bound did not reject excess edges");
    for(double angle:{0.,.3,.73,1.5707963267948966})for(double shift:{-1.,-.5,0.,.5,1.,1e9}) {
      auto transformed=pair;const Point d{std::cos(angle),std::sin(angle)};
      for(auto &poly:transformed)for(auto &v:poly.vertices) {
        const auto x=v;v={shift+x[0]*d[0]-x[1]*d[1],shift+x[0]*d[1]+x[1]*d[0]};
      }
      require(std::abs(area(cov::regions(transformed,0,2,d,2,30,1.8))-320)<3e-5,"Ribbon depends on translation/rotation");
    }
  } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
