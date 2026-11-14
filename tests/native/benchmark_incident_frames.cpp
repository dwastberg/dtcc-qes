#include "symmetry_helpers.h"
#include "winds/PolyBuilding.h"
static void inspect(const GridConfig &g,const BuildingArrays &b,double direction,int wake) {
  ModelSettings m;m.wake_flag=wake;ModelInputs input(g,m,b);input.set_condition({5,direction,10});
  WINDSGeneralData w(make_domain(input),input.buildings,input.parameterizations,input.inflow.site_z0);
  w.applyWindProfile(input.inflow);w.applyParametrizations([&](const char *stage) {
    if(std::string(stage)!="wake")return;
    for(auto *b:w.allBuildingsV) {
      auto f=w.domain.face(b->i_building_cent,b->j_building_cent,b->k_end);
      const double speed=std::hypot(double(w.u0[f]),double(w.v0[f]));
      std::cout<<"fallback "<<b->building_cent_x<<","<<b->building_cent_y<<" "
               <<(speed==0 || speed<.1*std::hypot(b->incident_u,b->incident_v))<<'\n';
    }
  });
  for(auto *building:w.allBuildingsV) {
    const double delta=std::remainder(double(building->upwind_dir-building->incident_dir),2*std::acos(-1));
    auto f=w.domain.face(building->i_building_cent,building->j_building_cent,building->k_end);
    std::cout<<"frame "<<building->building_cent_x<<","<<building->building_cent_y<<" angle "<<delta
             <<" incident "<<std::hypot(building->incident_u,building->incident_v)
             <<" later "<<std::hypot(building->u0_h,building->v0_h)<<'\n';
  }
  for(auto *building:w.allBuildingsV) for(int flag:{9,10}) {
    size_t count=0;double peak=0;
    float xmin=1e9,xmax=-1e9,ymin=1e9,ymax=-1e9;
    for(auto v:building->polygonVertices) {xmin=std::min(xmin,v.x_poly);xmax=std::max(xmax,v.x_poly);
      ymin=std::min(ymin,v.y_poly);ymax=std::max(ymax,v.y_poly);}
    for(int k=1;k<w.domain.nz()-1;++k)for(int j=1;j<w.domain.ny()-2;++j)for(int i=1;i<w.domain.nx()-2;++i)
      if((i+.5)*g.cell_size>=xmin-6 && (i+.5)*g.cell_size<=xmax+6
         && (j+.5)*g.cell_size>=ymin-6 && (j+.5)*g.cell_size<=ymax+6
         && w.icellflag[w.domain.cell(i,j,k)]==flag) {
        auto f=w.domain.face(i,j,k);++count;peak=std::max(peak,std::hypot(double(w.u0[f]),double(w.v0[f])));
      }
    std::cout<<"building "<<building->building_cent_x<<","<<building->building_cent_y<<" zone "<<flag<<" count "<<count<<" peak "<<peak<<'\n';
  }
}
int main() try {
  GridConfig g;g.nx=150;g.ny=100;g.nz=70;g.cell_size=2;
  for(int wake:{2,3})for(int layout=0;layout<6;++layout) {
    auto b=test_fixture::empty_buildings();double direction=270;
    if(layout<2) {
      b=test_fixture::rectangle(100,84,30,32,90);
      double x=layout==0?84:220;
      test_fixture::append(b,{x,94,x,106,x+10,106,x+10,94,x,94},8);
    } else if(layout==2) {
      b=test_fixture::rectangle(60,90,20,20,20);
      test_fixture::append(b,{130,90,130,110,150,110,150,90,130,90},20);
    } else {
      for(int j=0;j<3;++j)for(int i=0;i<3;++i) {
        double x=90+40*i,y=40+40*j;
        test_fixture::append(b,{x,y,x,y+20,x+20,y+20,x+20,y,x,y},20);
      }
      const double angle=(layout-3)*22.5*std::acos(-1)/180;
      for(size_t n=0;n<b.vertices.size();n+=2) {
        double x=b.vertices[n]-140,y=b.vertices[n+1]-90;
        b.vertices[n]=140+x*std::cos(angle)-y*std::sin(angle);
        b.vertices[n+1]=90+x*std::sin(angle)+y*std::cos(angle);
      }
    }
    auto differences=check(g,b,direction,2,wake);
    std::cout<<"layout "<<layout<<" wake "<<wake<<" mirror max/mean initial/final";
    for(double v:differences)std::cout<<" "<<v;std::cout<<std::endl;
    inspect(g,b,direction,wake);
    if(layout==2) {std::cout<<"exposed tandem control\n";inspect(g,test_fixture::rectangle(130,90,20,20,20),direction,wake);}
  }
} catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
