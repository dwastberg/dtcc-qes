// Compile the actual research preflight against a minimal native data fixture.
#include "canyon_kernel.h"
#include <iostream>
#include <stdexcept>
struct Vertex { float x_poly,y_poly; };
struct Building {
  float base_height=0,H=10,building_cent_x=0,building_cent_y=0,Lr=20;
  int i_building_cent=0,j_building_cent=0,k_end=10;
  std::vector<std::size_t> ringOffsets={0,5};
  std::vector<Vertex> polygonVertices;
};
struct Domain { int face(int,int,int) const { return 0; } };
struct WINDSGeneralData {
  Domain domain; std::vector<float> u0={5},v0={0};
  std::vector<Building*> allBuildingsV;
};
#include "CanyonPreflight.h"
Building block(float left) {
  Building b; b.building_cent_x=left+5;
  b.polygonVertices={{left,-5},{left,5},{left+10,5},{left+10,-5},{left,-5}};
  return b;
}
void require(bool condition,const char* message) { if (!condition) throw std::runtime_error(message); }
int main() {
  auto a=block(0),b=block(20),obstacle=block(15);
  WINDSGeneralData data; data.allBuildingsV={&a,&b};
  require(joint_spacing(a,data)==10.,"Single ring uses begin AND end offsets");
  require(joint_spacing(b,data)<0.,"No downstream canyon must fall back");
  b.H=9; require(joint_spacing(a,data)<0.,"Unequal height must fall back"); b.H=10;
  data.v0[0]=1; require(joint_spacing(a,data)<0.,"Oblique wind must fall back"); data.v0[0]=0;
  a.ringOffsets={0,5,10}; require(joint_spacing(a,data)<0.,"Hole must fall back"); a.ringOffsets={0,5};
  obstacle.polygonVertices[1].y_poly=3;
  data.allBuildingsV={&a,&b,&obstacle};
  require(joint_spacing(a,data)<0.,"Nearer unsupported obstruction cannot be skipped");
  auto duplicate=block(20),overlap=block(25),touch=block(10);
  data.allBuildingsV={&a,&b,&duplicate};
  require(joint_spacing(a,data)<0.,"Ambiguous downstream ties");
  data.allBuildingsV={&a,&duplicate,&b};
  require(joint_spacing(a,data)<0.,"Tie fallback independent of traversal order");
  data.allBuildingsV={&a,&b,&overlap};
  require(joint_spacing(a,data)<0.,"Overlapping downstream supports");
  data.allBuildingsV={&a,&b,&touch};
  require(joint_spacing(a,data)<0.,"Collapsed or touching spacing");
  data.allBuildingsV={&a,&b};
  a.base_height=1;require(joint_spacing(a,data)<0.,"Unsupported base");a.base_height=0;
  b.ringOffsets={0,4};require(joint_spacing(a,data)<0.,"Malformed ring");b.ringOffsets={0,5};
  data.u0[0]=0;require(joint_spacing(a,data)<0.,"Calm fallback");data.u0[0]=5;
  for (auto* item:data.allBuildingsV) {
    for (auto& q:item->polygonVertices) { const float x=q.x_poly,y=q.y_poly; q={211-y,37+x}; }
    const float x=item->building_cent_x,y=item->building_cent_y;
    item->building_cent_x=211-y; item->building_cent_y=37+x;
  }
  data.u0[0]=0;data.v0[0]=5;
  require(std::abs(joint_spacing(a,data)-10.)<1e-5,"Rigid native preflight transform");
  std::cout << "canyon preflight: native ring representation, pair spacing, final-row fallback, unsupported geometry, oblique wind and rigid transforms passed\n";
}
