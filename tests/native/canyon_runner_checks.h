#pragma once
#include <cstring>

// Exercise the actual overlay under the native sanitizer target, without Python.
static void canyon_runner_checks() {
  using namespace dtcc_qes;
  for (const double height : {8.,9.5}) {
    GridConfig grid; grid.nx=32;grid.ny=24;grid.nz=20;grid.cell_size=1.;
    if(height>8) {grid.nz=14;grid.dz_layers.assign(14,2.);grid.dz_layers.front()=grid.dz_layers.back()=1.;}
    ModelSettings model;model.sensor_x=model.sensor_y=1.;
    auto geometry=test_fixture::rectangle(6,8,6,8,height);
    test_fixture::append(geometry,{18,8,18,16,24,16,24,8,18,8},height);
    WindRunner runner;Messages messages;runner.prepare(grid,model,geometry,messages);
    SolverOptions options;options.precision="float64";options.max_iterations=200;
    WindCondition condition{5.,270.,10.};
    ExperimentOptions experiment;experiment.canyon_capture=true;
    const auto parent=runner.solve(condition,options,messages,nullptr,{},&experiment);
    for(const auto selector : {CanyonModel::HorizontalReferenceV1,CanyonModel::JoinedV1}) {
      experiment.canyon_model=selector;
      const auto result=runner.solve(condition,options,messages,nullptr,{},&experiment);
      const auto& e=*result.experiment;const auto& p=*parent.experiment;
      require(e.canyon_qualified==1 && e.canyon_changed_faces>0,"Actual canyon overlay inactive");
      require(e.canyon_roof_changes==0 && e.canyon_voxel_roof_changes==0 && e.canyon_W_changes==0,
              "Actual overlay changed protected initialization");
      require(e.canyon_initial_w.size()==p.canyon_initial_w.size() &&
              !std::memcmp(e.canyon_initial_w.data(),p.canyon_initial_w.data(),p.canyon_initial_w.size()*sizeof(float)),
              "Actual complete W initialization changed");
      require(result.cell_flags==parent.cell_flags,"Overlay changed geometry flags");
      for(const auto value:result.velocity) require(std::isfinite(value),"Nonfinite overlay output");
    }
    experiment.wake_composition=1;
    rejects<std::invalid_argument>([&]{runner.solve(condition,options,messages,nullptr,{},&experiment);});
    experiment.wake_composition=0;experiment.canyon_model=CanyonModel::Legacy;
    const auto restored=runner.solve(condition,options,messages,nullptr,{},&experiment);
    require(restored.velocity==parent.velocity,"Rejected canyon option contaminated reused geometry");
    require(restored.experiment->canyon_changed_faces==0,"Canyon counters escaped solve scope");
  }
}
