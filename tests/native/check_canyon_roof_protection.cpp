#include "CanyonRoofProtection.h"
#include <limits>
#include <stdexcept>

void require(bool ok,const char* message) { if(!ok) throw std::runtime_error(message); }
int main() {
  using joint_canyon::protected_roof;
  // x=10 gives a 2 m layer; physical H=10, voxel H=11 and z=8.
  require(protected_roof(10,2,3),"A roof below its voxel face must be protected");
  require(protected_roof(10,3,2),"A roof above its voxel face must retain legacy protection");
  require(!protected_roof(10,3,4),"Legal core must remain active");
  require(protected_roof(10,2,4),"Closed physical boundary");
  const double outside=std::nextafter(2.,std::numeric_limits<double>::infinity());
  require(!protected_roof(10,outside,outside),"No fitted tolerance may expand the boundary");
  require(!protected_roof(0,-1,-1),"Preserve zero-distance wall convention");
  for(double x: {0.,.01,.9375,1.,2.,5.,10.,20.})
    for(double physical: {9.5,10.,10.5,11.5})
      for(double voxel: {9.,10.,11.,12.})
        for(double z: {.5,2.,4.,6.,8.,10.,12.,14.}) {
          const double pd=physical-z,vd=float(voxel-z);
          const bool old=x>0 && vd<=.2*x;
          const bool geometric=x>0 && pd<=.2*x;
          require(protected_roof(x,pd,vd)==(old||geometric),"Independent union oracle");
          require(protected_roof(x,pd,pd)==joint_canyon::vertical(x,pd),"Aligned support equivalence");
        }
}
