#pragma once

namespace dtcc_qes {
// Constants of the spreading far wake, wake code 3 (WAKE_UPDATE_V2.md,
// section 3.1). Named here for the kernel and the bindings; not user settings.
struct SpreadingWakeModel
{
  static constexpr double spread = 0.2; // c_s: sigma = c_s (x - x1)
  static constexpr double bubble = 0.22; // delta = 0.22 R sqrt(1 - ((0.45 R - L) / (0.45 R))^2)
  static constexpr double bubble_length = 0.9; // delta = 0 when L >= 0.9 R
  static constexpr double turbulence = 0.08; // k_w = 0.08 max_b U_H,b^2 G_b
  static constexpr double reach_cut = 0.05; // end of the reach: centreline Fy Fz below this
  static constexpr double taper_start = 0.10; // start of the end taper: centreline Fy Fz below this
  static constexpr double skip = 1e-4; // faces where T Fy is below this are not written
  static constexpr double layer_cut = 6.0; // a column's layers end at z > z_c + 6 sigma(x), where Fz < 1e-9
};
}
