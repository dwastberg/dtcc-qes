#pragma once
// Internal geometry utilities. No velocity law, grid indices or QES state.
// These helpers do not select or apply a runtime canyon model.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

namespace physical_canyon {
using Point=std::array<double,2>;
inline Point add(Point a,Point b) {return {a[0]+b[0],a[1]+b[1]};}
inline Point sub(Point a,Point b) {return {a[0]-b[0],a[1]-b[1]};}
inline Point mul(Point a,double s) {return {a[0]*s,a[1]*s};}
inline double dot(Point a,Point b) {return a[0]*b[0]+a[1]*b[1];}
inline double cross(Point a,Point b) {return a[0]*b[1]-a[1]*b[0];}
inline double norm(Point a) {return std::hypot(a[0],a[1]);}
inline bool finite(Point a) {return std::isfinite(a[0]) && std::isfinite(a[1]);}
inline constexpr double roundoff=64*std::numeric_limits<double>::epsilon();

struct Polygon {
  std::int64_t source_id=0;
  std::vector<Point> vertices;
  std::vector<std::size_t> rings; // Closed-ring boundaries, including final end.
  double base=0,roof=0;
  bool face(std::size_t i) const {
    return i+1<vertices.size() && !std::binary_search(rings.begin(),rings.end(),i+1);
  }
  Point normal(std::size_t i) const {
    const auto e=sub(vertices[i+1],vertices[i]);const double length=norm(e);
    return length>0?Point{-e[1]/length,e[0]/length}:Point{NAN,NAN};
  }
  bool contains(Point p) const {
    bool inside=false;
    for(std::size_t i=0;i+1<vertices.size();++i)if(face(i)) {
      const auto a=sub(vertices[i],p),b=sub(vertices[i+1],p);
      if((a[1]<=0 && b[1]>0)||(a[1]>0 && b[1]<=0))
        if(0<a[0]-a[1]*(b[0]-a[0])/(b[1]-a[1]))inside=!inside;
    }
    return inside;
  }
  std::array<double,4> bounds() const {
    std::array<double,4> b{INFINITY,INFINITY,-INFINITY,-INFINITY};
    for(const auto &v:vertices){b[0]=std::min(b[0],v[0]);b[1]=std::min(b[1],v[1]);b[2]=std::max(b[2],v[0]);b[3]=std::max(b[3],v[1]);}
    return b;
  }
};

struct RayLocation {
  bool valid=false;
  Point origin{};
  double distance=0;
  const char *reason="unsupported_face_ray";
};

inline RayLocation locate(const Polygon &up,std::size_t face,Point point,Point direction,double reach) {
  RayLocation out;
  if(!up.face(face) || !finite(point) || !finite(direction) || !(reach>0))return out;
  const double length=norm(direction);if(!(length>0))return out;
  direction=mul(direction,1/length);
  const auto a=up.vertices[face],edge=sub(up.vertices[face+1],a);
  const double scale=std::max({1.,norm(a),norm(point),norm(edge),reach});
  const double denominator=cross(edge,direction),epsilon=roundoff*scale;
  if(!(dot(up.normal(face),direction)>roundoff) || std::abs(denominator)<=roundoff*norm(edge))return out;
  const double fraction=cross(sub(point,a),direction)/denominator;
  // A ray leaving exactly a polygon corner has no unique upstream face.
  if(!(fraction>roundoff && fraction<1-roundoff)) {out.reason="upstream_corner_or_outside_span";return out;}
  out.origin=add(a,mul(edge,fraction));out.distance=dot(sub(point,out.origin),direction);
  if(!(out.distance>epsilon && out.distance<=reach+epsilon)) {out.reason="outside_physical_reach";return out;}
  out.valid=true;out.reason="located";return out;
}

struct Pair {
  bool valid=false;
  std::size_t upstream=0,downstream=0,upstream_face=0,downstream_face=0;
  std::int64_t upstream_id=-1,downstream_id=-1;
  Point first{},last{},up_normal{},down_normal{};
  double gap=0,base=0,roof=0;
  const char *reason="no_downstream_intersection";
};

inline Pair qualify(const std::vector<Polygon> &scene,std::size_t upstream,std::size_t face,
                    Point origin,Point direction,double height,double reach) {
  Pair out;out.upstream=upstream;out.upstream_face=face;out.first=origin;
  if(upstream>=scene.size() || !scene[upstream].face(face) || !finite(origin)
      || !finite(direction) || !std::isfinite(height) || !std::isfinite(reach) || !(reach>0)) {
    out.reason="invalid_pair_input";return out;
  }
  const double length=norm(direction);if(!(length>0)){out.reason="calm_incident";return out;}
  direction=mul(direction,1/length);const auto &up=scene[upstream];out.upstream_id=up.source_id;
  out.up_normal=up.normal(face);
  if(!(dot(out.up_normal,direction)>roundoff)){out.reason="upstream_not_outgoing";return out;}
  const double scale=std::max({1.,norm(origin),reach,std::abs(height)});
  const double epsilon=roundoff*scale;
  if(!(height>up.base+epsilon && height<up.roof-epsilon)){out.reason="outside_upstream_wall_height";return out;}
  double nearest=std::numeric_limits<double>::infinity();bool ambiguous=false;
  std::size_t chosen=0,chosen_face=0;Point normal{};
  for(std::size_t n=0;n<scene.size();++n) {
    const auto &p=scene[n];
    if(!(height>p.base+epsilon && height<p.roof-epsilon))continue;
    const auto bounds=p.bounds();double near=0,far=reach;
    for(int dim=0;dim<2;++dim) {
      if(std::abs(direction[dim])<=roundoff) {
        if(origin[dim]<bounds[dim]-epsilon || origin[dim]>bounds[dim+2]+epsilon)far=-1;
      } else {
        double lo=(bounds[dim]-origin[dim])/direction[dim],hi=(bounds[dim+2]-origin[dim])/direction[dim];
        if(lo>hi)std::swap(lo,hi);near=std::max(near,lo);far=std::min(far,hi);
      }
    }
    if(near>far+epsilon || far<0)continue;
    if(n!=upstream && p.contains(origin)){out.reason="overlapping_origin";return out;}
    for(std::size_t f=0;f+1<p.vertices.size();++f)if(p.face(f) && !(n==upstream && f==face)) {
      const auto edge=sub(p.vertices[f+1],p.vertices[f]);
      const double denominator=cross(direction,edge);
      if(std::abs(denominator)<=roundoff*norm(edge))continue;
      const auto offset=sub(p.vertices[f],origin);
      const double distance=cross(offset,edge)/denominator;
      const double fraction=cross(offset,direction)/denominator;
      if(fraction<-roundoff || fraction>1+roundoff || distance<-epsilon || distance>reach+epsilon)continue;
      if(distance<=epsilon) {
        if(n!=upstream){out.reason="zero_gap_or_touching_origin";return out;}
        continue;
      }
      const auto candidate_normal=p.normal(f);
      if(distance<nearest-epsilon) {
        nearest=distance;chosen=n;chosen_face=f;normal=candidate_normal;ambiguous=false;
      } else if(std::abs(distance-nearest)<=epsilon) {
        if(p.source_id!=scene[chosen].source_id || dot(normal,candidate_normal)<1-roundoff)ambiguous=true;
        else if(f<chosen_face)chosen_face=f;
      }
    }
  }
  if(!std::isfinite(nearest))return out;
  out.downstream=chosen;out.downstream_face=chosen_face;out.downstream_id=scene[chosen].source_id;
  out.last=add(origin,mul(direction,nearest));out.gap=nearest;out.down_normal=normal;
  if(ambiguous){out.reason="ambiguous_first_intersection";return out;}
  if(chosen==upstream){out.reason="self_occlusion";return out;}
  // Do not skip a nearer nonopposing obstacle to select a farther face.
  if(dot(out.up_normal,normal)>-std::sqrt(.5)+roundoff){out.reason="first_face_not_opposing";return out;}
  out.base=std::max(up.base,scene[chosen].base);out.roof=std::min(up.roof,scene[chosen].roof);
  if(!(out.roof>out.base)){out.reason="no_common_wall_height";return out;}
  out.valid=true;out.reason="qualified";return out;
}

}
