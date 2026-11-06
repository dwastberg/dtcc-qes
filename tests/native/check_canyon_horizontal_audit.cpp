// Positive controls for complete-field bitwise W preservation.
#include <vector>
#include <stdexcept>
#include <iostream>
struct WINDSGeneralData {
  std::vector<float> w0=std::vector<float>(32,0.f);
  std::size_t canyon_W_changes=0;
};
#include "CanyonWAudit.h"
void require(bool condition,const char* text) { if (!condition) throw std::runtime_error(text); }
int main() {
  for (const auto index:{0,7,31}) {
    WINDSGeneralData data;
    const auto before=data.w0;
    data.w0[index]=1.f;
    joint_horizontal_W_audit(&data,before);
    require(data.canyon_W_changes==1,"A W change escaped the complete-field audit");
  }
  {
    WINDSGeneralData data;
    const auto before=data.w0;
    joint_horizontal_W_audit(&data,before);
    require(data.canyon_W_changes==0,"Unchanged W misclassified");
    data.w0[7]=-0.f;
    joint_horizontal_W_audit(&data,before);
    require(data.canyon_W_changes==1,"Signed-zero change escaped the bitwise audit");
  }
  {
    WINDSGeneralData data;
    bool rejected=false;
    try { joint_horizontal_W_audit(&data,std::vector<float>(31)); }
    catch (const std::runtime_error&) { rejected=true; }
    require(rejected,"Shape mismatch must fail");
  }
  std::cout << "horizontal audit: core and boundary W changes, signed-zero changes and shape mismatch detected; unchanged W accepted\n";
}
