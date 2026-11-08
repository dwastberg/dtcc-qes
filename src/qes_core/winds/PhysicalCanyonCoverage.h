#pragma once
#include "PhysicalCanyonGeometry.h"
#include <stdexcept>

namespace physical_canyon::coverage {
using Footprint=std::vector<Point>;
inline constexpr std::size_t maximum_edges=1024,maximum_cuts=65536;
struct Line {double intercept=0,slope=0,lo=0,hi=0;};
struct Region {
  Pair pair;
  Point origin{},direction{},transverse{};
  double lo=0,hi=0;
  Line upstream,downstream;
  Point point(double eta,const Line &line) const {
    return add(origin,add(mul(direction,line.intercept+line.slope*eta),mul(transverse,eta)));
  }
  Footprint polygon() const {
    return {point(lo,upstream),point(hi,upstream),point(hi,downstream),point(lo,downstream)};
  }
};
inline double area(const Footprint &p) {
  double sum=0;if(p.size()<3)return 0;
  for(std::size_t i=1;i+1<p.size();++i)sum+=cross(sub(p[i],p[0]),sub(p[i+1],p[0]));
  return std::abs(sum)*.5;
}
template<class Distance> Footprint clip(const Footprint &p,Distance distance) {
  Footprint out;if(p.empty())return out;
  auto a=p.back();double da=distance(a);
  for(auto b:p) {
    const double db=distance(b);
    if((da>=0)!=(db>=0))out.push_back(add(a,mul(sub(b,a),da/(da-db))));
    if(db>=0)out.push_back(b);
    a=b;da=db;
  }
  return out;
}
inline Footprint rectangle(Footprint p,double xmin,double ymin,double xmax,double ymax) {
  p=clip(p,[&](Point v){return v[0]-xmin;});p=clip(p,[&](Point v){return xmax-v[0];});
  p=clip(p,[&](Point v){return v[1]-ymin;});return clip(p,[&](Point v){return ymax-v[1];});
}
inline void cut(std::vector<double> &cuts,double eta,double lo,double hi) {
  if(std::isfinite(eta) && eta>lo && eta<hi) {
    if(cuts.size()>=maximum_cuts)throw std::length_error("Physical canyon coverage cut limit exceeded");
    cuts.push_back(eta);
  }
}
inline void order(std::vector<double> &cuts) {
  std::sort(cuts.begin(),cuts.end());
  const double epsilon=roundoff*std::max({1.,std::abs(cuts.front()),std::abs(cuts.back())});
  cuts.erase(std::unique(cuts.begin(),cuts.end(),[&](double a,double b){return b-a<=epsilon;}),cuts.end());
}
inline Line line(Point a,Point b,Point origin,Point d,Point e) {
  const auto x=sub(a,origin),y=sub(b,origin);const double eta0=dot(x,e),eta1=dot(y,e);
  const double slope=dot(sub(y,x),d)/(eta1-eta0);
  return {dot(x,d)-slope*eta0,slope,std::min(eta0,eta1),std::max(eta0,eta1)};
}

inline std::vector<Region> regions(const std::vector<Polygon> &scene,std::size_t upstream,
    std::size_t face,Point direction,double height,double reach,double minimum_gap) {
  std::vector<Region> out;
  const double length=norm(direction);
  if(upstream>=scene.size() || !scene[upstream].face(face) || !finite(direction) || !(length>0) || !std::isfinite(length))return out;
  direction=mul(direction,1/length);
  const auto &up=scene[upstream];
  if(!(height>up.base && height<up.roof) || !(reach>0) || !std::isfinite(reach) || !(dot(up.normal(face),direction)>roundoff))return out;
  const Point transverse{-direction[1],direction[0]},origin=up.vertices[face];
  const auto edge=sub(up.vertices[face+1],origin);const double eta_end=dot(edge,transverse);
  if(std::abs(eta_end)<=roundoff*norm(edge))return out;
  const double lo=std::min(0.,eta_end),hi=std::max(0.,eta_end);
  const auto up_line=line(up.vertices[face],up.vertices[face+1],origin,direction,transverse);
  std::vector<Line> lines;std::vector<double> cuts{lo,hi};
  for(const auto &p:scene)if(height>p.base && height<p.roof)
    for(std::size_t f=0;f+1<p.vertices.size();++f)if(p.face(f)) {
      const auto a=p.vertices[f],b=p.vertices[f+1];
      const double ea=dot(sub(a,origin),transverse),eb=dot(sub(b,origin),transverse);
      cut(cuts,ea,lo,hi);cut(cuts,eb,lo,hi);
      if(std::abs(eb-ea)<=roundoff*norm(sub(b,a)))continue;
      auto l=line(a,b,origin,direction,transverse);
      if(l.hi<=lo || l.lo>=hi)continue;
      if(lines.size()>=maximum_edges)throw std::length_error("Physical canyon coverage edge limit exceeded");
      lines.push_back(l);
      const double slope=l.slope-up_line.slope;
      if(std::abs(slope)>roundoff)
        for(double gap:{0.,reach,minimum_gap}) {
          const double eta=(gap-l.intercept+up_line.intercept)/slope;
          if(eta>l.lo && eta<l.hi)cut(cuts,eta,lo,hi);
        }
    }
  // Nearest intersection order can change only at a vertex or edge crossing.
  for(std::size_t i=0;i<lines.size();++i)for(std::size_t j=0;j<i;++j) {
    const auto &a=lines[i],&b=lines[j];const double slope=a.slope-b.slope;
    if(std::abs(slope)<=roundoff)continue;
    const double eta=(b.intercept-a.intercept)/slope;
    if(eta>a.lo && eta<a.hi && eta>b.lo && eta<b.hi)cut(cuts,eta,lo,hi);
  }
  order(cuts);
  for(std::size_t i=0;i+1<cuts.size();++i) {
    const double mid=.5*(cuts[i]+cuts[i+1]);
    const auto first=add(origin,add(mul(direction,up_line.intercept+up_line.slope*mid),mul(transverse,mid)));
    const auto pair=qualify(scene,upstream,face,first,direction,height,reach);
    if(!pair.valid || !(pair.gap>minimum_gap+roundoff*std::max(1.,reach)))continue;
    const auto &down=scene[pair.downstream];
    Region r{pair,origin,direction,transverse,cuts[i],cuts[i+1],up_line,
      line(down.vertices[pair.downstream_face],down.vertices[pair.downstream_face+1],origin,direction,transverse)};
    if(area(r.polygon())>0)out.push_back(r);
  }
  return out;
}

inline std::array<double,2> vertical_interval(const Region &r,int component,double normal,double lo,double hi) {
  Point a=component==0?Point{normal,0}:Point{0,normal};
  Point tangent=component==0?Point{0,1}:Point{1,0};
  const double eta=dot(sub(a,r.origin),r.transverse),slope=dot(tangent,r.transverse);
  const double epsilon=roundoff*std::max({1.,std::abs(r.lo),std::abs(r.hi)});
  // Half-open transverse intervals own a coincident normal face only once.
  // Actual physical corners are still rejected by node qualification.
  if(std::abs(slope)<=roundoff && (eta<r.lo-epsilon || eta>=r.hi-epsilon))return {0,0};
  const auto p=r.polygon();
  for(std::size_t i=0;i<p.size();++i) {
    const auto edge=sub(p[(i+1)%p.size()],p[i]);
    // Ribbons use clockwise vertex order; their interior is to the right.
    const double base=-cross(edge,sub(a,p[i])),gradient=-cross(edge,tangent);
    if(std::abs(gradient)<=roundoff*norm(edge)) {if(base<0)return {0,0};}
    else if(gradient>0)lo=std::max(lo,-base/gradient);else hi=std::min(hi,-base/gradient);
  }
  return hi>lo?std::array<double,2>{lo,hi}:std::array<double,2>{0,0};
}
inline std::array<Footprint,2> midpoint_split(const Region &r,const Footprint &p) {
  const auto distance=[&](Point v) {
    const auto delta=sub(v,r.origin);const double eta=dot(delta,r.transverse);
    return dot(delta,r.direction)-.5*(r.upstream.intercept+r.downstream.intercept+(r.upstream.slope+r.downstream.slope)*eta);
  };
  return {clip(p,distance),clip(p,[&](Point v){return -distance(v);})};
}
inline const std::array<double,3> nodes{.5-.5*std::sqrt(.6),.5,.5+.5*std::sqrt(.6)};
inline constexpr std::array<double,3> weights{5./18,4./9,5./18};
struct Integral {bool valid=true;double area=0,value=0;};
struct Blend {bool valid=false;double value=0,fraction=0;};
inline Blend blend(Integral integral,double total_area,double incoming) {
  Blend out{false,incoming,0};
  if(!integral.valid || !std::isfinite(integral.area) || !std::isfinite(integral.value)
      || !std::isfinite(incoming) || !std::isfinite(total_area) || !(total_area>0) || !(integral.area>0)
      || integral.area>total_area*(1+256*std::numeric_limits<double>::epsilon()))return out;
  out.fraction=std::min(1.,integral.area/total_area);
  const double bounded_integral=integral.value*std::min(1.,total_area/integral.area);
  out.value=(1-out.fraction)*incoming+bounded_integral/total_area;
  out.valid=std::isfinite(out.value);return out;
}
// Eval receives physical XY and height and returns a supported velocity value.
template<class Eval> Integral vertical(int component,double normal,double lo,double hi,double bottom,double top,Eval eval) {
  Integral out;if(!(hi>lo && top>bottom))return out;
  for(int i=0;i<3;++i)for(int j=0;j<3;++j) {
    const double tangent=lo+(hi-lo)*nodes[i],height=bottom+(top-bottom)*nodes[j];double value=0;
    const Point point=component==0?Point{normal,tangent}:Point{tangent,normal};
    if(!eval(point,height,value))return {false,0,0};
    out.value+=weights[i]*weights[j]*value;
  }
  out.area=(hi-lo)*(top-bottom);out.value*=out.area;return out;
}
template<class Eval> Integral horizontal(const Region &r,const Footprint &p,double height,Eval eval) {
  Integral out;
  for(const auto &part:midpoint_split(r,p))for(std::size_t t=1;t+1<part.size();++t) {
    const auto a=part[0],b=sub(part[t],a),c=sub(part[t+1],a);const double jacobian=std::abs(cross(b,c));
    if(!(jacobian>0))continue;
    for(int i=0;i<3;++i)for(int j=0;j<3;++j) {
      const double u=nodes[i],v=nodes[j],weight=jacobian*weights[i]*weights[j]*(1-u);double value=0;
      const auto point=add(a,add(mul(b,u),mul(c,(1-u)*v)));
      if(!eval(point,height,value))return {false,0,0};
      out.value+=weight*value;
    }
    out.area+=.5*jacobian;
  }
  return out;
}
}
