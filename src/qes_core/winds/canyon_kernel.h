// Research-only QES modified-canyon qualification helpers. Not a public model.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>
namespace joint_canyon {
struct Bounds { double lo_x=0, hi_x=0, lo_y=0, hi_y=0; bool valid=false; };
inline Bounds rectangle(const std::vector<std::array<double,2>>& points,
                        double cx, double cy, double angle) {
  Bounds b;
  if (points.size()!=5) return b;
  std::array<std::array<double,2>,5> q;
  for (int i=0;i<5;++i) {
    const double x=points[i][0]-cx,y=points[i][1]-cy;
    q[i]={x*std::cos(angle)+y*std::sin(angle),-x*std::sin(angle)+y*std::cos(angle)};
    if (!std::isfinite(q[i][0]) || !std::isfinite(q[i][1])) return b;
    if (i==0) b.lo_x=b.hi_x=q[i][0],b.lo_y=b.hi_y=q[i][1];
    b.lo_x=std::min(b.lo_x,q[i][0]); b.hi_x=std::max(b.hi_x,q[i][0]);
    b.lo_y=std::min(b.lo_y,q[i][1]); b.hi_y=std::max(b.hi_y,q[i][1]);
  }
  const double tol=1e-5*std::max({1.,b.hi_x-b.lo_x,b.hi_y-b.lo_y});
  if (b.hi_x-b.lo_x<=tol || b.hi_y-b.lo_y<=tol) return b;
  if (std::hypot(q[0][0]-q[4][0],q[0][1]-q[4][1])>tol) return b;
  int horizontal=0,vertical=0;
  for (int i=0;i<4;++i) {
    const double dx=std::abs(q[i+1][0]-q[i][0]),dy=std::abs(q[i+1][1]-q[i][1]);
    if (dx>tol && dy<=tol) ++horizontal;
    else if (dy>tol && dx<=tol) ++vertical;
    else return b;
  }
  b.valid=horizontal==2 && vertical==2;
  return b;
}
inline double core(double x, double y, double width) {
  const double half=.5*width-.2*x;
  // This factor is needed only in the interior; wedges overwrite outside it.
  if (!(half>0) || std::abs(y)>=half) return 0.;
  return std::pow(1.-std::abs(y)/half,.25);
}
inline bool lateral(double x,double y,double width) {
  return x>0 && std::abs(y)>=.5*width-.2*x;
}
inline bool vertical(double x,double roof_distance) {
  return x>0 && roof_distance<=.2*x;
}
inline double wedge(double x,double distance_from_inner_edge) {
  if (!(x>0)) return 0.;
  return std::tanh(distance_from_inner_edge/(.2*x))/std::tanh(1.);
}
}
