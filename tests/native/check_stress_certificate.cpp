#include "dtcc/api/stress_validity.h"
#include <iostream>
#include <random>
#include <stdexcept>

using namespace dtcc_qes;
void check(const StressTensor &t) {
  if(stress_is_valid(t)!=stress_validity(t).valid)
    throw std::runtime_error("Boolean certificate changed the raw validity policy");
}
int main() {
  try {
    std::mt19937 rng(20261108);std::normal_distribution<double> normal;
    for(int n=0;n<40000;++n) {
      double a[3][3];for(auto &row:a)for(auto &v:row)v=normal(rng);
      const double scale=std::pow(10.,(n%121-60)*.5);
      StressTensor t{};const int row[]={0,0,0,1,1,2},col[]={0,1,2,1,2,2};
      for(int k=0;k<6;++k) {
        double sum=0;for(int j=0;j<3;++j)sum+=a[row[k]][j]*a[col[k]][j];
        t[k]=float(scale*sum);
      }
      check(t);
      // General indefinite matrices, rank-deficient blocks and tolerance edges.
      t[n%6]=float(-scale*normal(rng));check(t);
      for(float x:{-2.f,-1.f,0.f,1.f,2.f})
        check({float(scale),0,0,float(scale),0,float(x*stress_validity_relative_tolerance*scale)});
      const float s=float(scale),next=std::nextafter(s,INFINITY);
      check({s,s,0,s,0,0});check({s,next,0,s,0,0});
    }
    for(float s:{0.f,std::numeric_limits<float>::denorm_min(),std::numeric_limits<float>::min(),
                 std::numeric_limits<float>::max()}) {
      check({s,0,0,s,0,s});check({s,s,s,s,s,s});check({-s,0,0,s,0,s});
    }
    for(float bad:{NAN,INFINITY,-INFINITY})for(int n=0;n<6;++n) {
      StressTensor t{};t[n]=bad;check(t);
      if(stress_is_valid(t))throw std::runtime_error("Nonfinite input became valid");
    }
  }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
