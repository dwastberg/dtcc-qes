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

// Constants of the tall-building option (Parameterizations.tall_buildings; validation/ACCURACY_RESULTS.md,
// sections 2, 5 and 6). Named here for the kernel; not user settings.
struct TallBuildingModel
{
  // Speed ratios to the undisturbed speed at the same height, against building height in metres at full
  // scale: Reiter (2010), Environment and Planning B 37, Fig. 5 (corner) and Fig. 7 (front vortex).
  static constexpr int corner_count = 8, vortex_count = 6;
  static constexpr double corner_height[corner_count] = { 0, 12, 24, 36, 48, 72, 96, 192 };
  static constexpr double corner_ratio[corner_count] = { 1.0, 1.58, 1.68, 1.8, 1.94, 2.38, 2.74, 3.3 };
  static constexpr double vortex_height[vortex_count] = { 24, 36, 48, 72, 96, 192 };
  static constexpr double vortex_ratio[vortex_count] = { 0.12, 0.28, 0.58, 1.2, 1.36, 1.4 };
  static constexpr double ratio_low = 1.5; // eligibility 0 at this roof-height ratio to the neighbours ...
  static constexpr double ratio_high = 2.5; // ... and 1 at this one (smoothstep)
  static constexpr double neighbourhood = 2.0; // neighbours: other buildings within this many roof heights
  static constexpr double reach = 0.75; // the zone ends this many roof heights from the walls (cosine decay)
  static constexpr double full_height = 0.25; // full weight up to this fraction of the roof height ...
  static constexpr double top_height = 0.5; // ... and none above this one
  static constexpr double reference_height = 0.75; // incident direction: the inflow at this fraction of the roof height
  static constexpr double mean_share = 0.8; // share of the target scalar speed imposed on the mean flow; the rest is turbulence
};
}
