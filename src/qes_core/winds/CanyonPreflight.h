// Complete eligibility decision before any overlay write.
#pragma once
namespace {
joint_canyon::Bounds joint_bounds(const Building& b, double cx,double cy,double angle) {
  std::vector<std::array<double,2>> p;
  // One closed ring has two offsets: begin and end.
  if (b.ringOffsets.size()!=2 || b.ringOffsets.front()!=0 ||
      b.ringOffsets.back()!=b.polygonVertices.size()) return {};
  for (const auto& v:b.polygonVertices) p.push_back({v.x_poly,v.y_poly});
  return joint_canyon::rectangle(p,cx,cy,angle);
}
struct CanyonSupport { double spacing=-1.; const char* reason="no_downstream_support"; };
CanyonSupport joint_support(const Building& b, const WINDSGeneralData& data,
                            const std::vector<float>* snapshot_u=nullptr,
                            const std::vector<float>* snapshot_v=nullptr) {
  if (std::abs(b.base_height)>1e-6 || !(b.H>0)) return {-1.,"unsupported_height_or_base"};
  const auto face=data.domain.face(b.i_building_cent,b.j_building_cent,b.k_end);
  const double u=(snapshot_u ? *snapshot_u : data.u0)[face];
  const double v=(snapshot_v ? *snapshot_v : data.v0)[face];
  if (!(std::hypot(u,v)>1e-8) || !std::isfinite(u) || !std::isfinite(v)) return {-1.,"calm_or_nonfinite"};
  const double angle=std::atan2(v,u),cx=b.building_cent_x,cy=b.building_cent_y;
  const auto own=joint_bounds(b,cx,cy,angle);
  if (!own.valid) return {-1.,"unsupported_shape_or_oblique_flow"};
  const double tol=1e-4*std::max(1.,double(b.H));
  struct Obstacle { const Building* building; double lx,hx,ly,hy; };
  std::vector<Obstacle> obstacles;
  double nearest=1e30;
  for (const auto* other:data.allBuildingsV) {
    if (other==&b) continue;
    // Inspect all vertices even when the candidate is unsupported, so a nearer
    // obstructing shape cannot be skipped in favour of a farther rectangle.
    double lx=1e30,hx=-1e30,ly=1e30,hy=-1e30;
    if(other->polygonVertices.empty()) return {-1.,"malformed_obstacle"};
    for (const auto& p:other->polygonVertices) {
      const double x=(p.x_poly-cx)*std::cos(angle)+(p.y_poly-cy)*std::sin(angle);
      const double y=-(p.x_poly-cx)*std::sin(angle)+(p.y_poly-cy)*std::cos(angle);
      if(!std::isfinite(x) || !std::isfinite(y)) return {-1.,"malformed_obstacle"};
      lx=std::min(lx,x); hx=std::max(hx,x); ly=std::min(ly,y); hy=std::max(hy,y);
    }
    if (hx<=own.hi_x+tol || hy<=own.lo_y+tol || ly>=own.hi_y-tol) continue;
    const double gap=lx-own.hi_x;
    obstacles.push_back({other,lx,hx,ly,hy});
    nearest=std::min(nearest,gap);
  }
  if(obstacles.empty()) return {};
  if(!(nearest>tol)) return {-1.,"overlap_or_zero_spacing"};
  const Obstacle* chosen=nullptr;
  for(const auto& q:obstacles) if(std::abs(q.lx-own.hi_x-nearest)<=tol) {
    if(chosen) return {-1.,"ambiguous_downstream_support"};
    chosen=&q;
  }
  for(const auto& q:obstacles) if(&q!=chosen && q.lx<chosen->hx-tol &&
      q.hx>chosen->lx+tol && q.ly<chosen->hy-tol && q.hy>chosen->ly+tol)
    return {-1.,"overlapping_downstream_supports"};
  const auto* other=chosen->building;
  const auto next=joint_bounds(*other,cx,cy,angle);
  if(!next.valid || std::abs(other->H-b.H)>=tol || std::abs(other->base_height)>=tol ||
     std::abs(next.lo_y-own.lo_y)>=tol || std::abs(next.hi_y-own.hi_y)>=tol)
    return {-1.,"unsupported_downstream_shape_height_or_span"};
  if(!(nearest<b.Lr)) return {-1.,"outside_cavity_support"};
  return {nearest,"supported"};
}
double joint_spacing(const Building& b,const WINDSGeneralData& data,
                     const std::vector<float>* snapshot_u=nullptr,
                     const std::vector<float>* snapshot_v=nullptr) {
  return joint_support(b,data,snapshot_u,snapshot_v).spacing;
}
}
