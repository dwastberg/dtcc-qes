// Research audit of the actual staggered fields, independent of probe interpolation.
#include <cstring>
void joint_core_roof_audit(WINDSGeneralData *data, const std::vector<float>& old_u,
                          const std::vector<float>& old_v, const std::vector<float>& old_w)
{
  struct Zone { double cx,cy,c,s,wall,gap,half_width,height,voxel_roof; std::size_t building; };
  std::vector<Zone> zones;
  for (std::size_t building=0;building<data->allBuildingsV.size();++building) {
    const auto* b=data->allBuildingsV[building];
    const double gap=joint_spacing(*b,*data,&old_u,&old_v);
    if (!(gap>0)) continue;
    const auto f=data->domain.face(b->i_building_cent,b->j_building_cent,b->k_end);
    // The reference lies above the building, so the complement must not alter it.
    if (std::memcmp(&old_u[f],&data->u0[f],sizeof(float)) || std::memcmp(&old_v[f],&data->v0[f],sizeof(float))) {
      ++data->canyon_roof_changes;
      ++data->canyon_voxel_roof_changes;
      if(data->canyon_trace_roof) {
        const bool u_changed=std::memcmp(&old_u[f],&data->u0[f],sizeof(float));
        data->canyon_roof_trace.insert(data->canyon_roof_trace.end(),
          {1.,u_changed?0.:1.,double(f),double(building),0.,0.,double(data->domain.z[b->k_end]),
           double(b->H),double(data->domain.z_face[b->k_end]),
           double(u_changed?old_u[f]:old_v[f]),double(u_changed?data->u0[f]:data->v0[f]),double(b->building_cent_x),double(b->building_cent_y)});
      }
    }
    const float angle=std::atan2(old_v[f],old_u[f]);
    const auto box=joint_bounds(*b,b->building_cent_x,b->building_cent_y,angle);
    zones.push_back({b->building_cent_x,b->building_cent_y,std::cos(angle),std::sin(angle),
                     box.hi_x,gap,.5*(box.hi_y-box.lo_y),b->H,data->domain.z_face[b->k_end],building});
  }
  data->canyon_audit_zones=zones.size();
  const auto [nx,ny,nz]=data->domain.getDomainCellNum();
  const double dx=data->domain.dx(),dy=data->domain.dy();
  const std::vector<float>* before[3]={&old_u,&old_v,&old_w};
  const std::vector<float>* after[3]={&data->u0,&data->v0,&data->w0};
  for (int component=0;component<3;++component) {
    for (std::size_t f=0;f<after[component]->size();++f) {
      if (!std::memcmp(&(*before[component])[f],&(*after[component])[f],sizeof(float))) continue;
      ++data->canyon_changed_faces;
      const int i=f%nx,j=(f/nx)%ny,k=f/(std::size_t(nx)*ny);
      if (component!=2 && k>=int(data->domain.z.size())) {
        ++data->canyon_roof_changes; ++data->canyon_voxel_roof_changes; continue;
      }
      const double gx=(i+(component==0 ? 0. : .5))*dx;
      const double gy=(j+(component==1 ? 0. : .5))*dy;
      const double height=component==2 ? data->domain.z_face[k] : data->domain.z[k];
      bool physical_counted=false,voxel_counted=false;
      for (const auto& q:zones) {
        // Match the coordinate precision used by the native canyon traversal.
        const float local_x=float((gx-q.cx)*q.c+(gy-q.cy)*q.s)-float(q.wall);
        const float local_y=float(-(gx-q.cx)*q.s+(gy-q.cy)*q.c);
        // Include the edge stencil: staggered writes can extend half a cell
        // beyond the projected wall. Protection is deliberately conservative.
        const bool in_plan=local_x>0 && local_x<=q.gap+.001 && std::abs(local_y)<=q.half_width+2*std::max(dx,dy);
        if (in_plan && q.height-height<=.2*local_x && !physical_counted) {
          ++data->canyon_roof_changes;
          physical_counted=true;
          if(data->canyon_trace_roof)
            data->canyon_roof_trace.insert(data->canyon_roof_trace.end(),
              {0.,double(component),double(f),double(q.building),local_x,local_y,height,q.height,q.voxel_roof,
               double((*before[component])[f]),double((*after[component])[f]),gx,gy});
        }
        if(in_plan && q.voxel_roof-height<=.2*local_x && !voxel_counted) {
          ++data->canyon_voxel_roof_changes;
          voxel_counted=true;
        }
        if(physical_counted && voxel_counted) break;
      }
    }
  }
}
