#pragma STDC FENV_ACCESS ON
#include "canyon_kernel.h"
#include <cfenv>
#include <iostream>
#include <stdexcept>
void require(bool condition,const char* message) {
  if (!condition) throw std::runtime_error(message);
}
int main() {
  using namespace joint_canyon;
  const std::vector<std::array<double,2>> original={{-5,-5},{-5,5},{5,5},{5,-5},{-5,-5}};
  for (double angle:{0.,.3,1.2,3.141592653589793}) {
    auto p=original;
    for (auto& q:p) { const double x=q[0],y=q[1]; q={217.+x*std::cos(angle)-y*std::sin(angle),-53.+x*std::sin(angle)+y*std::cos(angle)}; }
    const auto b=rectangle(p,217.,-53.,angle);
    require(b.valid,"Rigid motion must preserve the normal-flow rectangle");
    require(std::abs(b.lo_x+5.)<1e-10 && std::abs(b.hi_y-5.)<1e-10,"Projected bounds changed");
  }
  require(!rectangle(original,0,0,.2).valid,"Oblique wind must use legacy");
  auto malformed=original; malformed[2][0]=3.;
  require(!rectangle(malformed,0,0,0).valid,"Trapezoid must use legacy");
  auto crossing=original; std::swap(crossing[1],crossing[2]);
  require(!rectangle(crossing,0,0,0).valid,"Crossed polygon must be unsupported");
  std::feclearexcept(FE_ALL_EXCEPT);
  for (double x:{0.,1e-300,.5,2.,25.,30.}) {
    for (double y:{-5.,-4.9,-1.,0.,1.,4.9,5.}) {
      require(std::isfinite(core(x,y,10.)),"Nonfinite core");
      require(std::isfinite(wedge(x,.2*x)),"Nonfinite wedge");
      require(core(x,y,10.)==core(x,-y,10.),"Lateral symmetry changed");
      if (std::fetestexcept(FE_INVALID|FE_DIVBYZERO|FE_OVERFLOW)) {
        std::cerr << "Floating exception at x=" << x << " y=" << y << " flags=" << std::fetestexcept(FE_ALL_EXCEPT) << '\n';
        return 1;
      }
    }
  }
  require(!std::fetestexcept(FE_INVALID|FE_DIVBYZERO|FE_OVERFLOW),"Invalid floating operation before overwrite");
  require(core(2,0,10)==1.,"Centre factor");
  require(core(2,4.6,10)==0.,"Core/wedge inner join");
  require(std::abs(wedge(2,.4)-1.)<1e-14,"Outer wedge velocity");
  require(wedge(0,0)==0.,"Zero-distance limit");
  require(lateral(2,4.6,10) && vertical(2,.4),"Wedge support");
  require(!lateral(0,5,10) && !vertical(0,0),"Degenerate wedge support");
  std::cout << "canyon helper: rigid transforms, oblique rejection, malformed geometry, symmetry, support, finite limits and joins passed\n";
}
