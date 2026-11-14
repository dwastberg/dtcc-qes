// Unhashed verification probe; no solver preparation or field allocation.
#include "dtcc/api/covariance_model.h"
#include <iomanip>
#include <iostream>
int main() {
  dtcc_qes::StressTensor tensor;
  float bound;
  std::cout << std::setprecision(17);
  while (std::cin >> tensor[0]) {
    for (int n=1;n<6;++n) if (!(std::cin >> tensor[n])) return 2;
    if (!(std::cin >> bound)) return 2;
    const double alpha=dtcc_qes::spectral_limit(tensor,bound);
    std::cout << alpha;
    for (float value:tensor) std::cout << ' ' << value;
    std::cout << '\n';
  }
}
