#pragma once
#include <cstring>

// Private read-only provenance for writes that the physical-roof audit protects.
inline void joint_canyon_trace_write(WINDSGeneralData* data,const Building& building,int component,
                                    std::size_t face,float before,float x,float y,int k,int k_ref,
                                    double grid_x,double grid_y) {
  if(!data->canyon_trace_roof || !joint_canyon::vertical(x,building.H-data->domain.z[k])) return;
  const float after=component==0 ? data->u0[face] : data->v0[face];
  if(!std::memcmp(&before,&after,sizeof(float))) return;
  const auto found=std::find(data->allBuildingsV.begin(),data->allBuildingsV.end(),&building);
  data->canyon_roof_trace.insert(data->canyon_roof_trace.end(),
    {2.,double(component),double(face),double(found-data->allBuildingsV.begin()),x,y,
     double(data->domain.z[k]),double(building.H),double(data->domain.z_face[k_ref]),
     double(before),double(after),grid_x,grid_y});
}
