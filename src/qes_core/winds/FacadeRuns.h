#pragma once
#include "util/PolygonVertex.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <tuple>
#include <vector>

namespace facade_runs {
inline double cross(const polyVert &a,const polyVert &b,const polyVert &c) {
  return (double(b.x_poly)-a.x_poly)*(double(c.y_poly)-a.y_poly)
       -(double(b.y_poly)-a.y_poly)*(double(c.x_poly)-a.x_poly);
}
inline bool onSegment(const polyVert &a,const polyVert &b,const polyVert &p) {
  return cross(a,b,p)==0 && p.x_poly>=std::min(a.x_poly,b.x_poly) && p.x_poly<=std::max(a.x_poly,b.x_poly)
    && p.y_poly>=std::min(a.y_poly,b.y_poly) && p.y_poly<=std::max(a.y_poly,b.y_poly);
}
inline bool intersects(const polyVert &a,const polyVert &b,const polyVert &c,const polyVert &d) {
  const double x=cross(a,b,c),y=cross(a,b,d),z=cross(c,d,a),w=cross(c,d,b);
  return (((x>0 && y<0)||(x<0 && y>0)) && ((z>0 && w<0)||(z<0 && w>0)))
    || onSegment(a,b,c)||onSegment(a,b,d)||onSegment(c,d,a)||onSegment(c,d,b);
}
inline double distance(const polyVert &p,const polyVert &a,const polyVert &b) {
  const double x=double(b.x_poly)-a.x_poly,y=double(b.y_poly)-a.y_poly;
  if(x==0 && y==0)return std::hypot(double(p.x_poly)-a.x_poly,double(p.y_poly)-a.y_poly);
  const double t=std::clamp(((double(p.x_poly)-a.x_poly)*x+(double(p.y_poly)-a.y_poly)*y)/(x*x+y*y),0.,1.);
  return std::hypot(double(p.x_poly)-a.x_poly-t*x,double(p.y_poly)-a.y_poly-t*y);
}
inline bool inTriangle(const polyVert &p,const polyVert &a,const polyVert &b,const polyVert &c) {
  if(p.x_poly<std::min({a.x_poly,b.x_poly,c.x_poly}) || p.x_poly>std::max({a.x_poly,b.x_poly,c.x_poly})
     ||p.y_poly<std::min({a.y_poly,b.y_poly,c.y_poly}) || p.y_poly>std::max({a.y_poly,b.y_poly,c.y_poly}))return false;
  const double x=cross(a,b,p),y=cross(b,c,p),z=cross(c,a,p);
  return (x>=0 && y>=0 && z>=0)||(x<=0 && y<=0 && z<=0);
}

// Indices always refer to the original polygon, so merged runs retain all of
// their deviation constraints. Every ring participates in topology checks.
inline std::vector<std::vector<size_t>> simplify(const std::vector<polyVert> &v,
                                                const std::vector<size_t> &offsets,double tolerance) {
  std::vector<std::vector<size_t>> rings;
  for(size_t r=0;r+1<offsets.size();++r) {
    rings.emplace_back();for(size_t n=offsets[r];n+1<offsets[r+1];++n)rings.back().push_back(n);
  }
  while(true) {
    using Candidate=std::tuple<double,float,float,size_t,size_t>;
    Candidate best{std::numeric_limits<double>::infinity(),0,0,0,0};
    bool found=false;
    for(size_t r=0;r<rings.size();++r) {
      const auto &ring=rings[r];if(ring.size()<=3)continue;
      double area=0;for(size_t n=0;n<ring.size();++n) {
        const auto &a=v[ring[n]],&b=v[ring[(n+1)%ring.size()]];
        area+=double(a.x_poly)*b.y_poly-double(a.y_poly)*b.x_poly;
      }
      for(size_t n=0;n<ring.size();++n) {
        const size_t ai=ring[(n+ring.size()-1)%ring.size()],bi=ring[n],ci=ring[(n+1)%ring.size()];
        const auto &a=v[ai],&b=v[bi],&c=v[ci];
        const double deviation=distance(b,a,c);
        if(deviation>tolerance || area*(area-cross(a,b,c))<=0)continue;
        Candidate candidate{deviation,b.x_poly,b.y_poly,r,n};if(found && !(candidate<best))continue;
        bool allowed=true;
        size_t original=ai;
        do {
          if(distance(v[original],a,c)>tolerance){allowed=false;break;}
          original=original+1==offsets[r+1]-1?offsets[r]:original+1;
        } while(original!=ci);
        if(!allowed)continue;
        for(const auto &other:rings) {
          for(size_t j=0;j<other.size();++j) {
            const size_t pi=other[j],qi=other[(j+1)%other.size()];
            if(pi!=ai && pi!=bi && pi!=ci && inTriangle(v[pi],a,b,c)){allowed=false;break;}
            if(pi==ai || pi==ci || qi==ai || qi==ci || pi==bi || qi==bi)continue;
            if(intersects(a,c,v[pi],v[qi])){allowed=false;break;}
          }
          if(!allowed)break;
        }
        if(allowed){best=candidate;found=true;}
      }
    }
    if(!found)break;
    auto &ring=rings[std::get<3>(best)];ring.erase(ring.begin()+std::get<4>(best));
  }
  return rings;
}
}
