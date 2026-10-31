// Study-only JSON for the public monitor values consumed by S7 replay.
#pragma once
#include "api/monitor_types.h"
#include <iostream>
namespace dtcc_qes::policy_study {
inline void number(std::optional<double> v) {if(v && std::isfinite(*v))std::cout<<*v;else std::cout<<"null";}
inline void norm(const MonitorNorm &n) {std::cout<<"{\"p95\":";number(n.p95);std::cout<<",\"maximum\":";number(n.maximum);std::cout<<'}';}
inline void window(const MonitorWindow &w) {
  std::cout<<"{\"available\":"<<w.available<<",\"from_iteration\":"<<w.from_iteration<<",\"to_iteration\":"<<w.to_iteration
    <<",\"common_valid\":"<<w.common_valid<<",\"validity_changes\":"<<w.validity_changes<<",\"vector\":";
  norm(w.vector_over_uref);std::cout<<",\"speed\":";norm(w.speed_factor_change);
  std::cout<<",\"ratios\":[";number(w.ratios.vector_p95);std::cout<<',';number(w.ratios.vector_max);std::cout<<',';
  number(w.ratios.speed_p95);std::cout<<',';number(w.ratios.speed_max);
  std::cout<<"],\"hotspots\":[";
  for(int n=0;n<2;++n){if(n)std::cout<<',';const auto &h=w.hotspots[n];
    std::cout<<"{\"present\":"<<h.present<<",\"before_valid\":"<<h.before.valid<<",\"current_valid\":"<<h.current.valid
      <<",\"vector_change\":";number(h.vector_change);std::cout<<",\"speed_change\":";number(h.speed_change);std::cout<<'}';}
  std::cout<<"]}";
}
inline void checkpoint(const MonitorCheckpoint &c) {
  std::cout<<"{\"required_valid\":"<<c.required_receptors_valid<<",\"heights\":[";
  for(std::size_t i=0;i<c.heights.size();++i){if(i)std::cout<<',';auto &h=c.heights[i];
    std::cout<<"{\"valid\":"<<h.valid<<",\"short\":";window(h.short_change);std::cout<<",\"long\":";window(h.long_change);std::cout<<'}';}
  std::cout<<"],\"receptors\":[";
  for(std::size_t i=0;i<c.receptors.size();++i){if(i)std::cout<<',';auto &r=c.receptors[i];
    std::cout<<"{\"required\":"<<r.required<<",\"valid\":"<<r.sample.valid<<",\"short\":";window(r.short_change);
    std::cout<<",\"long\":";window(r.long_change);std::cout<<'}';}
  std::cout<<"],\"regional_mass\":[";
  for(std::size_t i=0;i<c.mass.size();++i){if(i)std::cout<<',';auto &d=c.mass[i].divergence;
    std::cout<<"{\"maximum\":"<<d.interior_max<<",\"rms\":"<<d.interior_rms<<",\"cells\":"<<d.cells<<'}';}
  std::cout<<"]}";
}
}
