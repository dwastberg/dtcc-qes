// Positive controls for the exact native face audit used in the core experiment.
#include "canyon_kernel.h"
#include <iostream>
#include <stdexcept>
#include <tuple>
struct Vertex { float x_poly,y_poly; };
struct Building {
  float base_height=0,H=10,building_cent_x=0,building_cent_y=12,Lr=20;
  int i_building_cent=0,j_building_cent=12,k_end=10;
  std::vector<std::size_t> ringOffsets={0,5};
  std::vector<Vertex> polygonVertices;
};
struct Domain {
  std::vector<float> z,z_face;
  Domain() { for (int k=0;k<16;++k) z_face.push_back(k); for (int k=0;k<15;++k) z.push_back(k+.5f); }
  std::tuple<int,int,int> getDomainCellNum() const { return {48,24,16}; }
  double dx() const { return 1.; } double dy() const { return 1.; }
  std::size_t face(int i,int j,int k) const { return i+48*(j+24*k); }
};
struct WINDSGeneralData {
  bool canyon_trace_roof=true;
  std::vector<double> canyon_roof_trace;
  std::size_t canyon_voxel_roof_changes=0;
  Domain domain;
  std::vector<float> u0=std::vector<float>(48*24*16,5.),v0=std::vector<float>(48*24*16,0.),w0=v0;
  std::vector<Building*> allBuildingsV;
  std::size_t canyon_roof_changes=0,canyon_changed_faces=0,canyon_audit_zones=0;
};
#include "CanyonPreflight.h"
#include "CanyonRoofAudit.h"
Building block(float left) {
  Building b; b.building_cent_x=left+5; b.i_building_cent=int(left+5);
  b.polygonVertices={{left,7},{left,17},{left+10,17},{left+10,7},{left,7}};
  return b;
}
void require(bool condition,const char* text) { if (!condition) throw std::runtime_error(text); }
int main() {
  auto a=block(4),b=block(24);
  for (int component=0;component<3;++component) {
    WINDSGeneralData data;data.allBuildingsV={&a,&b};
    const auto u=data.u0,v=data.v0,w=data.w0;
    auto* field=component==0 ? &data.u0 : component==1 ? &data.v0 : &data.w0;
    (*field)[data.domain.face(22,12,9)]+=1.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_audit_zones==1,"Expected one supported canyon");
    require(data.canyon_changed_faces==1 && data.canyon_roof_changes==1,"Injected roof-face corruption escaped audit");
  }
  {
    WINDSGeneralData data;data.allBuildingsV={&a,&b};
    const auto u=data.u0,v=data.v0,w=data.w0;
    data.u0[data.domain.face(18,12,3)]+=1.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_changed_faces==1 && data.canyon_roof_changes==0,"Legal deep-core change misclassified");
  }
  {
    WINDSGeneralData data;data.allBuildingsV={&a,&b};
    const auto u=data.u0,v=data.v0,w=data.w0;
    data.w0[data.domain.face(22,12,9)]=-0.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_roof_changes==1,"Bitwise protection must detect signed-zero changes");
  }
  {
    auto first=block(4),last=block(24);first.H=last.H=9.5;
    WINDSGeneralData data;data.allBuildingsV={&first,&last};
    const auto u=data.u0,v=data.v0,w=data.w0;
    data.u0[data.domain.face(20,12,8)]+=1.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_roof_changes==1 && data.canyon_voxel_roof_changes==0,"Physical-only corruption");
    require(data.canyon_roof_trace.size()==13 && data.canyon_roof_trace[4]==6 &&
      data.canyon_roof_trace[6]==8.5 && data.canyon_roof_trace[7]==9.5 && data.canyon_roof_trace[8]==10,
      "Independent trace coordinates");
  }
  {
    auto first=block(4),last=block(24);first.H=last.H=10.5;
    WINDSGeneralData data;data.allBuildingsV={&first,&last};
    const auto u=data.u0,v=data.v0,w=data.w0;
    data.u0[data.domain.face(22,12,8)]+=1.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_roof_changes==0 && data.canyon_voxel_roof_changes==1,"Voxel-only corruption");
  }
  {
    WINDSGeneralData data;data.allBuildingsV={&a,&b};
    const auto u=data.u0,v=data.v0,w=data.w0;
    data.v0[data.domain.face(a.i_building_cent,a.j_building_cent,a.k_end)]=1.f;
    joint_core_roof_audit(&data,u,v,w);
    require(data.canyon_audit_zones==1 && data.canyon_roof_changes>0,"Corrupt reference cannot hide audit zone");
  }
  std::cout << "core audit: injected U/V/W roof changes detected, legal core change allowed, signed-zero mutation detected\n";
}
