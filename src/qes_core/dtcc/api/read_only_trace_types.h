#pragma once
// Private observational capture. No physical options or acceptance policy.
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace dtcc_qes {
struct ReadOnlyTraceOptions {
  std::vector<std::array<int,3>> cells, tensor_cells; // Physical (i,j,k).
  std::size_t maximum_frames=1024;
  std::vector<int> canyon_buildings;
  std::size_t maximum_decisions=50000;
  bool building_frames=true; // False retains whole stages for large scenes.
};
struct ReadOnlyTraceFrame {
  std::string stage;
  int building=-1; // Native actor index; -1 is a whole-stage observation.
  std::vector<float> faces; // Per cell: u_left,u_right,v_low,v_high,w_low,w_high.
  std::vector<std::int32_t> flags;
};
struct ReadOnlyTraceData {
  std::vector<std::array<int,3>> cells,tensor_cells;
  std::vector<float> cell_coordinates,tensor_coordinates;
  std::vector<ReadOnlyTraceFrame> frames;
  // pre_anisotropy, post_anisotropy, post_bound; raw native stored floats.
  std::vector<float> tensors,properties,uncapped_constitutive;
  std::vector<std::uint8_t> found;
  std::vector<std::int32_t> tensor_flags,wall_flags,neighbour_flags;
  // native index, source integer ID, centroid XY, centroid IJ, bounds XY, H.
  std::vector<double> buildings;
  std::vector<double> orientations; // c,s,actual native sigU/V/W multipliers per tensor cell.
  std::vector<std::string> canyon_events;
  std::vector<int> canyon_actors;
  std::vector<double> canyon_values; // Fixed 16-value rows; unused entries are NaN.
};
}
