#pragma once
// Investigation-only sampler. No production call site or fallback policy.
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace reference_investigation {
using Vector=std::array<double,3>;
struct Estimate {
  bool supported=false;
  int lower=-1,upper=-1,count=0;
  double weight=0,mean_double=0;
  float mean_float=0;
};
template<class Sample>
Estimate interpolate(const std::vector<float>& centres,double height,int columns,Sample sample) {
  Estimate out;
  if(centres.empty() || !std::isfinite(height) || height<centres.front() || height>centres.back())return out;
  out.upper=int(std::lower_bound(centres.begin(),centres.end(),height)-centres.begin());
  out.lower=centres[out.upper]==height?out.upper:out.upper-1;
  out.weight=out.lower==out.upper?0:(height-centres[out.lower])/(centres[out.upper]-double(centres[out.lower]));
  double total=0;float narrow=0,ncount=0;
  for(int column=0;column<columns;++column) {
    const auto a=sample(out.lower,column),b=sample(out.upper,column);
    if(!a.first || (!b.first && out.weight>0))continue;
    Vector v;
    for(int c=0;c<3;++c)v[c]=(1-out.weight)*a.second[c]+out.weight*b.second[c];
    const double speed=std::sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);
    if(!std::isfinite(speed))continue;
    total+=speed;narrow+=speed;ncount++;out.count++;
  }
  if(out.count) {out.supported=true;out.mean_double=total/out.count;out.mean_float=narrow/ncount;}
  return out;
}
}
