// Pure constitutive replay on captured inputs; no wind or turbulence solver.
#include "replay_covariance.h"
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>

using Matrix=std::array<std::array<double,3>,3>;
static Matrix multiply(const Matrix &a,const Matrix &b) {
  Matrix c{};
  for(int i=0;i<3;++i)for(int j=0;j<3;++j)c[i][j]=a[i][0]*b[0][j]+a[i][1]*b[1][j]+a[i][2]*b[2][j];
  return c;
}
static dtcc_qes::StressTensor anisotropy(dtcc_qes::StressTensor v,const std::array<double,19> &p) {
  Matrix t{{{v[0],v[1],v[2]},{v[1],v[3],v[4]},{v[2],v[4],v[5]}}};
  const double c=p[14],s=p[15];
  const Matrix q{{{c,-s,0},{s,c,0},{0,0,1}}},qt{{{c,s,0},{-s,c,0},{0,0,1}}};
  t=multiply(qt,multiply(t,q));
  for(int i=0;i<3;++i)t[i][i]=std::abs(p[16+i]*t[i][i]);
  t=multiply(q,multiply(t,qt));
  return {float(t[0][0]),float(t[0][1]),float(t[0][2]),float(t[1][1]),float(t[1][2]),float(t[2][2])};
}
int main() {
  std::cout<<std::setprecision(9);
  std::array<double,19> p;
  while(std::cin>>p[0]) {
    for(int i=1;i<19;++i)if(!(std::cin>>p[i]))return 2;
    const float nu=p[10],lm=p[9],capped=p[11],bound=p[13];
    const dtcc_qes::StressTensor strain{float(p[0]),.5f*(float(p[1])+float(p[3])),.5f*(float(p[2])+float(p[6])),
      float(p[4]),.5f*(float(p[5])+float(p[7])),float(p[8])};
    dtcc_qes::StressTensor pre;
    for(int i=0;i<6;++i)pre[i]=float((i==0 || i==3 || i==5 ? (2./3.)*capped : 0.)-2.*(nu*strain[i]));
    const auto post=anisotropy(pre,p);
    auto spectral=post;dtcc_qes::spectral_limit(spectral,bound);
    auto consistent=anisotropy(dtcc_qes::consistent_constitutive(strain,nu,
      dtcc_qes::uncapped_energy(nu,lm),capped),p);
    dtcc_qes::spectral_limit(consistent,bound);
    for(auto values:{post,spectral,consistent})for(float v:values)std::cout<<v<<' ';
    std::cout<<'\n';
  }
}
