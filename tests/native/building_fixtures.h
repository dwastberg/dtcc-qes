#pragma once
#include "model_inputs.h"
#include <initializer_list>

namespace test_fixture {
inline dtcc_qes::BuildingArrays empty_buildings()
{
  return {{}, {0}, {}, {}, {}};
}

inline void append(dtcc_qes::BuildingArrays &a, std::initializer_list<double> vertices,
                   double height, double base = 0)
{
  a.vertices.insert(a.vertices.end(), vertices);
  a.offsets.push_back(a.vertices.size()/2);
  a.ids.push_back(a.ids.size()); a.heights.push_back(height); a.base_heights.push_back(base);
}

inline dtcc_qes::BuildingArrays rectangle(double x, double y, double width, double depth,
                                         double height, double base = 0)
{
  auto a = empty_buildings();
  append(a, {x,y, x,y+depth, x+width,y+depth, x+width,y, x,y}, height, base);
  return a;
}

template<class Vertices>
dtcc_qes::BuildingArrays polygon(const Vertices &vertices, double height, double base = 0)
{
  auto a = empty_buildings();
  for (const auto &v : vertices) a.vertices.insert(a.vertices.end(), {v[0],v[1]});
  a.offsets.push_back(a.vertices.size()/2);
  a.ids = {0}; a.heights = {height}; a.base_heights = {base};
  return a;
}
}
