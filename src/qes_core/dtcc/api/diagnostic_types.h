#pragma once
#include <cstddef>
namespace dtcc_qes {
struct DivergenceStats {
  double interior_max = 0, interior_rms = 0, top_band_max = 0;
  std::size_t cells = 0, top_band_cells = 0;
};
}
