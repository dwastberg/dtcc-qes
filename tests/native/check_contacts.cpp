#include "model_inputs.h"
#include "wind_runner.h"
#include "winds/WINDSGeneralData.h"
#include "winds/PolyBuilding.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <limits>

using namespace dtcc_qes;
static void require(bool v, const char *message) { if (!v) throw std::runtime_error(message); }
static void rejects(const BuildingArrays &arrays)
{
  try { ModelInputs input(GridConfig{},ModelSettings{},arrays); }
  catch (const std::invalid_argument &) { return; }
  throw std::runtime_error("Malformed rings accepted");
}
static void append(BuildingArrays &a, std::initializer_list<double> vertices, double height)
{
  a.vertices.insert(a.vertices.end(),vertices);
  a.offsets.push_back(a.vertices.size()/2);
  a.ids.push_back(a.ids.size()); a.heights.push_back(height); a.base_heights.push_back(0);
}
int main()
{
  GridConfig grid; grid.nx=40; grid.ny=30; grid.nz=24; grid.cell_size=1;
  ModelSettings model; model.exposed_faces=true; model.sensor_x=5; model.sensor_y=5;
  BuildingArrays arrays{{},{0},{},{},{}};
  append(arrays,{8,8,8,20,20,20,20,8,8,8},6);
  append(arrays,{20,8,20,14,28,14,28,8,20,8},12);
  ModelInputs input(grid,model,arrays);
  WINDSGeneralData data(make_domain(input),input.buildings,input.parameterizations,.1);
  auto *low=dynamic_cast<PolyBuilding*>(data.allBuildingsV[0]);
  auto *high=dynamic_cast<PolyBuilding*>(data.allBuildingsV[1]);
  require(!low->faceExposed(&data,2,20,10,3),"Shared wall exposed below neighbor roof");
  require(low->faceExposed(&data,2,20,18,3),"Uncovered part of shared wall hidden");
  require(!high->faceExposed(&data,0,20,10,3),"High wall exposed below low roof");
  require(high->faceExposed(&data,0,20,10,9),"Height-step wall hidden above low roof");
  std::fill(data.icellflag.begin(),data.icellflag.end(),1);
  require(!low->faceExposed(&data,2,20,10,3),"Exposure used mutable parameterization flags");

  BuildingArrays blocked{{},{0},{},{},{}};
  append(blocked,{8,8,8,20,20,20,20,8,8,8},6);
  append(blocked,{20,8,20,20,28,20,28,8,20,8},12);
  ModelInputs blocked_input(grid,model,blocked);
  blocked_input.set_condition(WindCondition{});
  WINDSGeneralData blocked_data(make_domain(blocked_input),blocked_input.buildings,blocked_input.parameterizations,.1);
  blocked_data.applyWindProfile(blocked_input.inflow);
  const auto initial_flags=blocked_data.icellflag;
  auto *source=dynamic_cast<PolyBuilding*>(blocked_data.allBuildingsV[0]);
  source->polygonWake(&blocked_data,0); source->streetCanyon(&blocked_data);
  require(blocked_data.icellflag==initial_flags,"Hidden wall cast wake or canyon through neighbor");

  BuildingArrays shallow{{},{0},{},{},{}};
  append(shallow,{18,8,18,20,20,20,20,8,18,8},6);
  append(shallow,{20,8,20,20,28,20,28,8,20,8},12);
  ModelInputs shallow_input(grid,model,shallow); shallow_input.set_condition(WindCondition{});
  WINDSGeneralData shallow_data(make_domain(shallow_input),shallow_input.buildings,shallow_input.parameterizations,.1);
  shallow_data.applyWindProfile(shallow_input.inflow);
  const auto sample=shallow_data.domain.face(16,14,3);
  const auto before=shallow_data.u0[sample];
  shallow_data.allBuildingsV[1]->upwindCavity(&shallow_data);
  require(shallow_data.u0[sample]==before,"Hidden upwind wall projected cavity through shallow neighbor");

  BuildingArrays oblique{{},{0},{},{},{}};
  append(oblique,{8,8,8,20,20,8,8,8},6);
  append(oblique,{8,20,20,20,20,8,8,20},12);
  ModelInputs oblique_input(grid,model,oblique);
  WINDSGeneralData oblique_data(make_domain(oblique_input),oblique_input.buildings,oblique_input.parameterizations,.1);
  auto *oblique_low=dynamic_cast<PolyBuilding*>(oblique_data.allBuildingsV[0]);
  auto *oblique_high=dynamic_cast<PolyBuilding*>(oblique_data.allBuildingsV[1]);
  require(!oblique_low->faceExposed(&oblique_data,1,14,14,3),"Oblique shared wall exposed");
  require(oblique_high->faceExposed(&oblique_data,2,14,14,9),"Oblique step wall hidden above low roof");

  BuildingArrays junction{{},{0},{},{},{}};
  append(junction,{8,8,8,20,20,20,20,14,20,8,8,8},6);
  ModelInputs junction_input(grid,model,junction);
  WINDSGeneralData junction_data(make_domain(junction_input),junction_input.buildings,junction_input.parameterizations,.1);
  require(junction_data.allBuildingsV[0]->polygonVertices.size()==5,"Collinear topology vertex split parameterization face");
  require(junction_data.allBuildingsV[0]->maskVertices.size()==6,"Parameter face merge lost raster topology vertices");

  junction.ring_offsets=junction.offsets;
  auto disabled=model; disabled.exposed_faces=false;
  ModelInputs canonical_input(grid,disabled,junction);
  WINDSGeneralData canonical_data(make_domain(canonical_input),canonical_input.buildings,canonical_input.parameterizations,.1);
  require(canonical_data.allBuildingsV[0]->polygonVertices.size()==5,"Exposure-off changed canonical parameterization faces");

  BuildingArrays courtyard{{},{0},{},{},{}};
  append(courtyard,{8,8,8,20,20,20,20,8,8,8, 12,12,16,12,16,16,12,16,12,12},10);
  courtyard.ring_offsets={0,5,10};
  ModelInputs rings(grid,model,courtyard);
  WINDSGeneralData ring_data(make_domain(rings),rings.buildings,rings.parameterizations,.1);
  auto *building=dynamic_cast<PolyBuilding*>(ring_data.allBuildingsV[0]);
  require(!building->isFace(4) && !building->isFace(9),"Jump or closing sentinel treated as a face");
  require(building->previousFace(5)==8 && building->nextFace(8)==5,"Hole neighbors crossed rings");
  require(!building->containsXY(14,14) && building->containsXY(10,10),"Hole membership is wrong");
  require(ring_data.icellflag_initial[ring_data.domain.cell(14,14,3)]==1,"Courtyard rasterized solid");
  require(building->faceExposed(&ring_data,5,14,12,3),"Courtyard wall not exposed");
  for (bool exposed: {false,true}) {
    auto settings=model; settings.exposed_faces=exposed;
    WindRunner courtyard_runner; Messages messages;
    courtyard_runner.prepare(grid,settings,courtyard,messages);
    SolverOptions options; options.max_iterations=3;
    for (double direction: {0.,90.,180.,270.,25.}) {
      auto condition=WindCondition{}; condition.direction=direction;
      const auto result=courtyard_runner.solve(condition,options,messages);
      for (auto v: result.velocity) require(std::isfinite(v),"Courtyard flow nonfinite");
    }
  }
  BuildingArrays tiny_hole{{},{0},{},{},{}};
  append(tiny_hole,{8,8,8,20,20,20,20,8,8,8, 14.1,14.1,14.3,14.1,14.3,14.3,14.1,14.3,14.1,14.1},10);
  tiny_hole.ring_offsets={0,5,10};
  ModelInputs tiny_input(grid,model,tiny_hole);
  WINDSGeneralData tiny_data(make_domain(tiny_input),tiny_input.buildings,tiny_input.parameterizations,.1);
  auto *tiny_building=dynamic_cast<PolyBuilding*>(tiny_data.allBuildingsV[0]);
  require(!tiny_building->faceExposed(&tiny_data,5,14.2,14.1,3),"Subcell courtyard ray passed through opposite source wall");

  auto modified=rings.parameterizations; modified.streetCanyonFlag=2; modified.upwindCavityFlag=3;
  WINDSGeneralData modified_data(make_domain(rings),rings.buildings,modified,.1);
  rings.set_condition(WindCondition{}); modified_data.applyWindProfile(rings.inflow);
  modified_data.applyParametrizations();
  for (auto v: modified_data.u0) require(std::isfinite(v),"Ring handling failed in modified parameterizations");
  for (auto v: modified_data.v0) require(std::isfinite(v),"Modified canyon ring flow nonfinite");

  auto bad=courtyard;
  bad.ring_offsets={0,4,10}; rejects(bad);
  bad.ring_offsets={0,std::numeric_limits<std::int64_t>::min(),10}; rejects(bad);
  bad=courtyard;
  for (int i=5; i<10; ++i) { bad.vertices[2*i]=courtyard.vertices[2*(14-i)]; bad.vertices[2*i+1]=courtyard.vertices[2*(14-i)+1]; }
  rejects(bad);
  bad=courtyard; bad.vertices[10]=30; rejects(bad);
  bad=courtyard; bad.vertices[14]=8; bad.vertices[15]=20; rejects(bad);

  // An explicit ring ending replaces the old 0.1 m closure heuristic in opt-in mode.
  BuildingArrays close{{},{0},{},{},{}};
  append(close,{8,8,8.04,8.04,8,20,20,20,20,8,8,8},10);
  WindRunner runner; Messages messages; runner.prepare(grid,model,close,messages);
  SolverOptions options; options.max_iterations=3;
  const auto result=runner.solve(WindCondition{},options,messages);
  for (auto v: result.velocity) require(std::isfinite(v),"Near-closure vertex produced nonfinite flow");
}
