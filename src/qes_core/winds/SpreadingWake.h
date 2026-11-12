#pragma once

/** @file SpreadingWake.h
 * @brief Spreading far wake of one building (wake code 3; WAKE_UPDATE_V2.md, section 3.1).
 *
 * Not part of QES-Winds. The building's shadow is diffused across the wind and
 * in height by a mixing layer whose width grows linearly downstream:
 *
 *   G = min(1, T(x) Fy Fz),  sigma = max(0.2 (x - x1), dxy/2)
 *   Fy = 1/2 [erf((y - y1 + delta) / (sqrt2 sigma)) - erf((y - y2 - delta) / (sqrt2 sigma))]
 *   Fz = the same between z_a and z_t + delta, plus its image in the ground
 *
 * with T the end taper. The geometry depends only on the footprint, its base
 * and height, the wind direction at its roof and the grid; it reads no wind
 * field. The caller combines buildings: D = max_b G_b on u and v faces, and
 * max_b U_H,b^2 G_b on u faces.
 */

#include "qes/Domain.h"

#include <algorithm>
#include <cstddef>
#include <vector>

/** Constants of the spreading wake. Named here; they are not user settings. */
struct SpreadingWakeModel
{
  static constexpr double spread = 0.2; /**< c_s: sigma = c_s (x - x1) */
  static constexpr double bubble = 0.22; /**< delta = 0.22 R sqrt(1 - ((0.45 R - L) / (0.45 R))^2) */
  static constexpr double bubble_length = 0.9; /**< delta = 0 when L >= 0.9 R */
  static constexpr double turbulence = 0.08; /**< k_w = 0.08 max_b U_H,b^2 G_b */
  static constexpr double reach_cut = 0.05; /**< end of the reach: centreline Fy Fz below this */
  static constexpr double taper_start = 0.10; /**< start of the end taper: centreline Fy Fz below this */
  static constexpr double skip = 1e-4; /**< faces where T Fy is below this are not written */
};

/** One building's footprint in its wind frame, as polygonWake computes it. */
struct SpreadingWakeFootprint
{
  const std::vector<float> *xi = nullptr, *yi = nullptr; /**< wind-frame vertices (along, across the wind) */
  std::vector<char> face; /**< edge id -> id+1 is a face (holes included; ring jumps excluded) */
  float x1 = 0, x2 = 0, y1 = 0, y2 = 0; /**< bounding extents of the face vertices, as in polygonWake */
  float area = 0; /**< footprint area */
  float width = 0; /**< effective cross-wind width W = area / (x2 - x1) */
  float height = 0; /**< H, above the base */
  float base = 0; /**< base height above the model ground */
  float top = 0; /**< physical roof z_t = base + H */
  float direction = 0; /**< wind direction (radians, mathematical) of the frame's x axis */
  float centre_x = 0, centre_y = 0; /**< frame origin in the domain */
};

class SpreadingWake
{
public:
  /**
   * Geometry, reach and evaluated region of one building's far wake.
   * ``spread`` is c_s; it differs from SpreadingWakeModel::spread only in tests.
   */
  SpreadingWake(const SpreadingWakeFootprint &footprint, const qes::Domain &domain,
                double spread = SpreadingWakeModel::spread);

  /** False when the footprint has no cross-wind extent; G is then zero everywhere. */
  bool active() const { return active_; }

  /**
   * G at one staggered face: component 0 is the u face (i dx, (j + 1/2) dy, z[k]),
   * 1 the v face ((i + 1/2) dx, j dy, z[k]). Zero outside the evaluated region
   * and where T Fy < SpreadingWakeModel::skip, exactly as accumulate writes it.
   */
  float point(int component, int i, int j, int k) const;

  /**
   * Combine this building's wake into the face arrays: deficit_u, deficit_v =
   * max(., G) and roof_speed2_u = max(., roof_speed2 G) on u faces. Columns are
   * independent; the loop is parallel over rows and needs no ordering.
   */
  void accumulate(double roof_speed2, std::vector<float> &deficit_u, std::vector<float> &deficit_v,
                  std::vector<float> &roof_speed2_u) const;

  double reach() const { return reach_; } /**< x_r, downstream end in the wind frame */
  double taperFrom() const { return taper_from_; } /**< x_s; negative when the deficit ends without a taper */
  double edgeOffset() const { return bubble_; } /**< delta */
  double lowerEdge() const { return base_ > 0 ? std::max(base_ - bubble_, 0.0) : 0.0; } /**< z_a */
  double upperEdge() const { return top_ + bubble_; } /**< z_c */
  /** Index bounds of the evaluated region: faces i0..i1, j0..j1, layers 1..k1. */
  void region(int &i0, int &i1, int &j0, int &j1, int &k1) const { i0 = i0_; i1 = i1_; j0 = j0_; j1 = j1_; k1 = k1_; }

private:
  double across(double y, double sigma) const; /**< Fy */
  double vertical(double z, double sigma) const; /**< Fz, with the ground image */
  /** T Fy at a horizontal point (domain coordinates); sets sigma. Zero outside x1 < x <= x_r and upstream of the lee wall. */
  double column(double gx, double gy, double &sigma) const;
  bool inRegion(int i, int j, int k) const;

  const qes::Domain &domain_;
  bool active_ = false;
  double spread_;
  float x1_, x2_, y1_, y2_;
  double centre_x_, centre_y_, cos_, sin_;
  double base_, top_, bubble_ = 0, sigma_min_;
  double reach_ = 0, taper_from_ = -1;
  int strips_ = 1;
  double strip_width_ = 0;
  std::vector<double> lee_;
  int i0_ = 1, i1_ = 0, j0_ = 1, j1_ = 0, k1_ = 0;
};
