#include "PhysicalCanyonGeometry.h"
#include <iostream>
#include <stdexcept>

using namespace physical_canyon;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
Polygon rectangle(std::int64_t id,double lo,double hi,double height=10) {
  return {id,{{lo,-20},{lo,20},{hi,20},{hi,-20},{lo,-20}},{0,5},0,height};
}
Point transform(Point p,Point shift,double angle) {
  return add(shift,{p[0]*std::cos(angle)-p[1]*std::sin(angle),p[0]*std::sin(angle)+p[1]*std::cos(angle)});
}
int main() {
  try {
    for(double angle:{0.,.15,.73,1.5707963267948966,3.141592653589793})
      for(double offset:{-1.,-.5,0.,.5,1.,1e9}) {
        auto scene=std::vector<Polygon>{rectangle(49,-40,0),rectangle(50,20,60,14)};
        const Point shift{offset,offset},direction{std::cos(angle),std::sin(angle)};
        for(auto &p:scene)for(auto &v:p.vertices)v=transform(v,shift,angle);
        const Point origin=transform({0,1},shift,angle),point=transform({9,1},shift,angle);
        const auto located=locate(scene[0],2,point,direction,30);
        require(located.valid && norm(sub(located.origin,origin))<2e-6,"Physical face ray depends on grid/origin");
        const auto pair=qualify(scene,0,2,located.origin,direction,2,30);
        require(pair.valid && pair.upstream_id==49 && pair.downstream_id==50 && pair.downstream_face==0,"Wrong physical opposing face");
        require(std::abs(pair.gap-20)<2e-6 && pair.roof==10,"Physical gap or shared roof changed");
        std::swap(scene[0],scene[1]);
        require(qualify(scene,1,2,located.origin,direction,2,30).downstream_id==50,"Source IDs depend on input order");
      }
    auto scene=std::vector<Polygon>{rectangle(1,-40,0),rectangle(2,20,60)};
    const auto oblique=qualify(scene,0,2,{0,1},{1,.2},2,30);
    require(oblique.valid && std::abs(oblique.gap-20*std::sqrt(1.04))<1e-12,
      "Oblique flow did not use ray distance");
    require(!qualify(scene,0,2,{0,1},{0,1},2,30).valid,"Parallel ray accepted");
    require(!qualify(scene,0,2,{0,1},{1,.95},2,30).valid,"Ambiguous downstream corner accepted");
    require(!qualify(scene,0,2,{0,1},{1,0},10,30).valid,"Roof plane treated as a wall interior");
    require(!qualify(scene,0,2,{0,1},{1,0},2,19).valid,"Search exceeds existing physical reach");
    require(!locate(scene[0],2,{10,20},{1,0},30).valid,"Upstream corner has no unique face");
    scene.push_back(rectangle(3,8,10,4));
    require(qualify(scene,0,2,{0,1},{1,0},2,30).downstream_id==3,"Nearer occluder skipped");
    require(qualify(scene,0,2,{0,1},{1,0},6,30).downstream_id==2,"Unequal-height occluder not level aware");
    scene.push_back(rectangle(4,8,10,4));
    require(!qualify(scene,0,2,{0,1},{1,0},2,30).valid,"Ambiguous overlapping faces accepted");
    scene={rectangle(1,-40,0),rectangle(2,0,20)};
    require(!qualify(scene,0,2,{0,1},{1,0},2,30).valid,"Zero physical spacing accepted");
    // A concave upstream object re-enters the outgoing ray before another building.
    scene={Polygon{1,{{-10,-10},{-10,10},{20,10},{20,0},{10,0},{10,5},{0,5},{0,-10},{-10,-10}},{0,9},0,10},rectangle(2,30,50)};
    const auto blocked=qualify(scene,0,6,{0,2},{1,0},2,60);
    require(!blocked.valid && std::string(blocked.reason)=="self_occlusion","Concave self obstruction skipped");
  } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
