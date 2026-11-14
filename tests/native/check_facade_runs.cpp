#include "building_fixtures.h"
#include "winds/WINDSGeneralData.h"
#include "winds/PolyBuilding.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace dtcc_qes;
using Point=std::array<double,2>;
static void require(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
static std::vector<Point> simplify(std::vector<Point> ring,bool exposed=false,double dy=2) {
  GridConfig g;g.nx=g.ny=160;g.nz=24;g.cell_size=2;
  ModelSettings settings;settings.exposed_faces=exposed;
  auto b=test_fixture::polygon(ring,20);ModelInputs input(g,settings,b);
  WINDSGeneralData w(qes::Domain(g.nx,g.ny,g.nz,2,dy,2),input.buildings,input.parameterizations,input.inflow.site_z0);
  auto *building=w.allBuildingsV[0];
  Building original;original.polygonVertices=input.buildings[0].vertices;original.ringOffsets={0,original.polygonVertices.size()};
  for(int j=0;j<w.domain.ny()-1;++j)for(int i=0;i<w.domain.nx()-1;++i)
    require(building->containsXY((i+.5)*2,(j+.5)*dy)==original.containsXY((i+.5)*2,(j+.5)*dy),"Solid footprint changed during simplification");
  std::vector<Point> result;
  for(auto p:building->polygonVertices)result.push_back({p.x_poly,p.y_poly});
  // Independent deviation check against the final polyline, including removed vertices.
  for(auto p:ring) {
    double best=1e100;
    for(size_t e=0;e+1<result.size();++e) {
      auto a=result[e],b=result[e+1];double x=b[0]-a[0],y=b[1]-a[1];
      double t=std::clamp(((p[0]-a[0])*x+(p[1]-a[1])*y)/(x*x+y*y),0.,1.);
      best=std::min(best,std::hypot(p[0]-a[0]-t*x,p[1]-a[1]-t*y));
    }
    require(best<=.5*std::min(2.,dy)+1e-5,"Original facade exceeds modelling tolerance");
  }
  return result;
}
static std::vector<float> initial_field(const std::vector<Point> &ring,bool exposed) {
  GridConfig g;g.nx=g.ny=100;g.nz=30;
  ModelSettings settings;settings.exposed_faces=exposed;
  ModelInputs input(g,settings,test_fixture::polygon(ring,30));input.set_condition({5,0,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);w.applyParametrizations();
  std::vector<float> field=w.u0;field.insert(field.end(),w.v0.begin(),w.v0.end());field.insert(field.end(),w.w0.begin(),w.w0.end());
  return field;
}
static std::vector<Point> canonical(std::vector<Point> ring) {
  ring.pop_back();std::rotate(ring.begin(),std::min_element(ring.begin(),ring.end()),ring.end());return ring;
}
int main() try {
  const std::vector<Point> kink={{80,80},{80,100},{110,100.1},{140,100},{140,80},{80,80}};
  for(bool exposed:{false,true}) {
    require(simplify(kink,exposed).size()==5,"Small facade kink not merged");
    require(initial_field(kink,exposed)==initial_field({{80,80},{80,100},{140,100},{140,80},{80,80}},exposed),
            "Merged kink does not reproduce rectangle parameterizations");
    require(simplify({{80,80},{80,100},{95,100},{110,100},{125,100},{140,100},{140,80},{80,80}},exposed).size()==5,"Collinear facade not merged");
  }
  auto expected=simplify(kink);
  auto shifted=kink;shifted.pop_back();
  for(size_t n=0;n<shifted.size();++n) {
    auto ring=shifted;ring.push_back(ring.front());require(simplify(ring)==expected,"Simplification depends on starting vertex");
    std::rotate(shifted.begin(),shifted.begin()+1,shifted.end());
  }
  require(simplify({{80,80},{80,100},{110,102},{140,100},{140,80},{80,80}}).size()==6,"Real setback removed");
  require(simplify({{80,80},{80,100},{110,100.75},{140,100},{140,80},{80,80}},false,1).size()==6,"Unequal-spacing tolerance ignored");
  for(double radius:{20.,60.}) {
    std::vector<Point> ring;
    for(int n=0;n<32;++n){double a=-n*2*std::acos(-1)/32;ring.push_back({150+radius*std::cos(a),150+radius*std::sin(a)});}
    ring.push_back(ring.front());auto result=simplify(ring);
    require(radius==60?result.size()==33:result.size()<33,"Circular facade deviation criterion violated");
  }
  // The one-metre slot cannot be filled by simplifying its lips.
  auto slot=simplify({{80,80},{80,110},{90,110},{90,90},{91,90},{91,110},{101,110},{101,80},{80,80}});
  Building slot_polygon;
  for(auto p:slot) {polyVert v;v.x_poly=p[0];v.y_poly=p[1];slot_polygon.polygonVertices.push_back(v);}
  slot_polygon.ringOffsets={0,slot.size()};
  require(!slot_polygon.containsXY(90.5,105) && slot_polygon.containsXY(89.5,105),"Narrow slot collapsed");
  // Courtyard rings participate in the same topology checks and keep their
  // original solid raster, even when the wall is thinner than a cell.
  GridConfig g;g.nx=g.ny=80;g.nz=24;
  BuildingArrays courtyard{{60,60,60,80,60.1,100,100,100,100,60,60,60,
                           60.5,65,95,65,95,95,60.5,95,60.5,65},
                           {0,11},{0},{20},{0},{0,6,11}};
  ModelInputs input(g,{},courtyard);
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  auto *building=w.allBuildingsV[0];
  require(building->ringOffsets.size()==3,"Courtyard hole removed");
  Building original;original.polygonVertices=input.buildings[0].vertices;original.ringOffsets={0,6,11};
  for(int j=0;j<80;++j)for(int i=0;i<80;++i)
    require(building->containsXY(2*i+1,2*j+1)==original.containsXY(2*i+1,2*j+1),"Courtyard solid mask changed");
  Building parameter;parameter.polygonVertices=building->polygonVertices;parameter.ringOffsets=building->ringOffsets;
  require(!parameter.containsXY(61,80) && parameter.containsXY(60.25,80),"Courtyard thin wall lost");
  std::cout<<"Facade deviations, grid tolerance, start vertex and original masks pass\n";
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
