#pragma once
#include "api/read_only_trace_types.h"
#include "winds/WINDSGeneralData.h"
#include "winds/TURBGeneralData.h"
#include "util/QESException.h"
#include <algorithm>
#include <limits>
#include <set>
#include <unordered_map>

namespace dtcc_qes {
class ReadOnlyTraceRecorder {
  WINDSGeneralData &wind_;
  ReadOnlyTraceData &out_;
  std::size_t maximum_frames_;
  std::size_t maximum_decisions_;
  bool building_frames_;
  std::unordered_map<int,std::size_t> tensor_indices_;
  std::set<std::pair<int,std::size_t>> observed_faces_;
public:
  ReadOnlyTraceRecorder(const ReadOnlyTraceOptions &spec,WINDSGeneralData &wind,ReadOnlyTraceData &out)
    :wind_(wind),out_(out),maximum_frames_(spec.maximum_frames),maximum_decisions_(spec.maximum_decisions),building_frames_(spec.building_frames) {
    if(spec.cells.size()>512 || spec.tensor_cells.size()>4096 || !maximum_frames_ || maximum_frames_>1024
        || !maximum_decisions_ || maximum_decisions_>100000
        || (spec.cells.empty() && spec.tensor_cells.empty()))
      throw qes::InputError("Read-only trace exceeds bounded capture limits or has no cells");
    const auto &d=wind_.domain;
    const auto validate=[&](const auto &cells) {
      std::set<std::array<int,3>> unique;
      for(const auto &c:cells) {
        if(c[0]<0 || c[0]>=d.nx()-1 || c[1]<0 || c[1]>=d.ny()-1 || c[2]<0 || c[2]>=d.nz()-2)
          throw qes::InputError("Read-only trace cell is outside the physical domain");
        if(!unique.insert(c).second)throw qes::InputError("Duplicate read-only trace cell");
      }
    };
    validate(spec.cells);validate(spec.tensor_cells);
    std::set<int> actors;
    for(int id:spec.canyon_buildings)
      if(id<0 || std::size_t(id)>=wind_.allBuildingsV.size() || !actors.insert(id).second)
        throw qes::InputError("Invalid or duplicate canyon trace actor");
    out_.cells=spec.cells;out_.tensor_cells=spec.tensor_cells;
    const float nan=std::numeric_limits<float>::quiet_NaN();
    const auto n=spec.tensor_cells.size();
    out_.tensors.assign(3*n*6,nan);out_.found.assign(3*n,0);
    out_.properties.assign(n*14,nan);out_.uncapped_constitutive.assign(n*6,nan);
    out_.orientations.assign(n*5,std::numeric_limits<double>::quiet_NaN());
    out_.tensor_flags.assign(n,-1);out_.wall_flags.assign(n,-1);out_.neighbour_flags.assign(n*6,-1);
    for(const auto &c:spec.cells) {
      out_.cell_coordinates.insert(out_.cell_coordinates.end(),{d.x[c[0]],d.y[c[1]],d.z[c[2]+1]});
      const auto f=d.face(c[0],c[1],c[2]+1);
      observed_faces_.insert({0,f});observed_faces_.insert({0,f+1});
      observed_faces_.insert({1,f});observed_faces_.insert({1,f+d.nx()});
      observed_faces_.insert({2,f});observed_faces_.insert({2,f+d.nx()*d.ny()});
    }
    for(std::size_t row=0;row<n;++row) {
      const auto &c=spec.tensor_cells[row];
      tensor_indices_.emplace(d.cell(c[0],c[1],c[2]+1),row);
      out_.tensor_coordinates.insert(out_.tensor_coordinates.end(),{d.x[c[0]],d.y[c[1]],d.z[c[2]+1]});
    }
    for(std::size_t index=0;index<wind_.allBuildingsV.size();++index) {
      const auto &b=*wind_.allBuildingsV[index];
      double xmin=INFINITY,ymin=INFINITY,xmax=-INFINITY,ymax=-INFINITY;
      for(const auto &v:b.polygonVertices) {
        xmin=std::min(xmin,double(v.x_poly));xmax=std::max(xmax,double(v.x_poly));
        ymin=std::min(ymin,double(v.y_poly));ymax=std::max(ymax,double(v.y_poly));
      }
      out_.buildings.insert(out_.buildings.end(),{double(index),double(b.ID),b.building_cent_x,b.building_cent_y,
        double(b.i_building_cent),double(b.j_building_cent),xmin,ymin,xmax,ymax,b.H});
    }
  }
  void frame(const char *stage,int building=-1,bool projected=false) {
    if(out_.cells.empty() || (building>=0 && !building_frames_))return;
    if(out_.frames.size()>=maximum_frames_)throw qes::InputError("Read-only trace frame limit reached");
    ReadOnlyTraceFrame row;row.stage=stage;row.building=building;
    const auto &d=wind_.domain;
    const auto &u=projected?wind_.u:wind_.u0;
    const auto &v=projected?wind_.v:wind_.v0;
    const auto &w=projected?wind_.w:wind_.w0;
    row.faces.reserve(out_.cells.size()*6);row.flags.reserve(out_.cells.size());
    for(const auto &c:out_.cells) {
      const auto f=d.face(c[0],c[1],c[2]+1);
      row.faces.insert(row.faces.end(),{u[f],u[f+1],v[f],v[f+d.nx()],w[f],w[f+d.nx()*d.ny()]});
      row.flags.push_back(wind_.icellflag[d.cell(c[0],c[1],c[2]+1)]);
    }
    out_.frames.push_back(std::move(row));
  }
  void stress(int stage,int cell,const std::array<float,6> &values) {
    const auto at=tensor_indices_.find(cell);if(at==tensor_indices_.end())return;
    const auto row=std::size_t(stage)*out_.tensor_cells.size()+at->second;
    std::copy(values.begin(),values.end(),out_.tensors.begin()+6*row);out_.found[row]=1;
  }
  void production(int cell,float viscosity,float uncapped) {
    const auto at=tensor_indices_.find(cell);if(at==tensor_indices_.end())return;
    out_.properties[at->second*14+10]=viscosity;
    out_.properties[at->second*14+12]=uncapped;
  }
  void orientation(int cell,double c,double s) {
    const auto at=tensor_indices_.find(cell);if(at==tensor_indices_.end())return;
    out_.orientations[at->second*5]=c;out_.orientations[at->second*5+1]=s;
  }
  void canyon(const char *code,int actor,const std::array<double,16> &values) {
    const std::string name(code);
    if(name.rfind("write_",0)==0) {
      const int component=name.back()=='u'?0:name.back()=='v'?1:2;
      if(!observed_faces_.count({component,std::size_t(values[5])}))return;
    }
    if(out_.canyon_events.size()>=maximum_decisions_)throw qes::InputError("Canyon decision trace limit reached");
    out_.canyon_events.push_back(name);out_.canyon_actors.push_back(actor);
    out_.canyon_values.insert(out_.canyon_values.end(),values.begin(),values.end());
  }
  void properties(const TURBGeneralData &turb) {
    const auto &d=wind_.domain;
    const float bound=turb.getUpperBound()*turb.getFrictionVelocity()*turb.getFrictionVelocity();
    for(const auto &entry:tensor_indices_) {
      const auto c=entry.first;const auto row=entry.second;
      out_.tensor_flags[row]=wind_.icellflag[c];out_.wall_flags[row]=turb.iturbflag[c];
      const auto &physical=out_.tensor_cells[row];
      const std::array<std::array<int,3>,6> shifts={{{-1,0,0},{1,0,0},{0,-1,0},{0,1,0},{0,0,-1},{0,0,1}}};
      for(int q=0;q<6;++q) {
        const int i=physical[0]+shifts[q][0],j=physical[1]+shifts[q][1],k=physical[2]+1+shifts[q][2];
        if(i>=0 && i<d.nx()-1 && j>=0 && j<d.ny()-1 && k>=0 && k<d.nz()-1)
          out_.neighbour_flags[row*6+q]=wind_.icellflag[d.cell(i,j,k)];
      }
      if(!out_.found[row])continue;
      out_.orientations[row*5+2]=turb.sigUConst;
      out_.orientations[row*5+3]=turb.sigVConst;
      out_.orientations[row*5+4]=turb.sigWConst;
      const float xx=turb.Gxx[c],yy=turb.Gyy[c],zz=turb.Gzz[c];
      const float xy=.5f*(turb.Gxy[c]+turb.Gyx[c]),xz=.5f*(turb.Gxz[c]+turb.Gzx[c]),yz=.5f*(turb.Gyz[c]+turb.Gzy[c]);
      const float lm=turb.Lm[c],nu=turb.nuT[c];
      const float uncapped=out_.properties[row*14+12];
      const std::array<float,14> values={turb.Gxx[c],turb.Gxy[c],turb.Gxz[c],turb.Gyx[c],turb.Gyy[c],turb.Gyz[c],
        turb.Gzx[c],turb.Gzy[c],turb.Gzz[c],lm,nu,turb.tke[c],uncapped,bound};
      std::copy(values.begin(),values.end(),out_.properties.begin()+row*14);
      // Explicitly labelled reconstruction, not an extra executed physical stage.
      const std::array<float,6> raw={float((2.0/3.0)*uncapped-2.0*(nu*xx)),float(-2.0*(nu*xy)),
        float(-2.0*(nu*xz)),float((2.0/3.0)*uncapped-2.0*(nu*yy)),float(-2.0*(nu*yz)),
        float((2.0/3.0)*uncapped-2.0*(nu*zz))};
      std::copy(raw.begin(),raw.end(),out_.uncapped_constitutive.begin()+row*6);
    }
  }
};
}
