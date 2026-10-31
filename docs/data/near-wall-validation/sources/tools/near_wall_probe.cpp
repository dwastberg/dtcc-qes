// Reuse the frozen study setup and original sampler without altering its source.
// This separate diagnostic executable never changes the production API/kernel.
#define main frozen_vertical_grid_main
#include "vertical_grid_study.cpp"
#undef main

static void write_patch(std::ostream &out, const WINDSGeneralData &a,
                        double x, double y, double height, bool initial)
{
  const auto &d = a.domain;
  const int cx = int(x / d.dx()), cy = int(y / d.dy());
  const int cz = int(std::lower_bound(d.z.begin()+1, d.z.end(), height)-d.z.begin());
  const int i0=std::max(0,cx-2), i1=std::min(d.nx()-2,cx+2);
  const int j0=std::max(0,cy-2), j1=std::min(d.ny()-2,cy+2);
  const int k0=std::max(1,cz-2), k1=std::min(d.nz()-2,cz+2);
  const auto &u = initial ? a.u0 : a.u;
  const auto &v = initial ? a.v0 : a.v;
  const auto &w = initial ? a.w0 : a.w;
  auto flag = [&](int i,int j,int k) {
    return i>=0 && i<d.nx()-1 && j>=0 && j<d.ny()-1 && k>=1 && k<d.nz()-1
      ? a.icellflag[d.cell(i,j,k)] : -1;
  };
  out << "{\"local_point\":[" << x << ',' << y << ',' << height << "],\"cells\":[";
  bool first=true;
  for(int k=k0;k<=k1;++k) for(int j=j0;j<=j1;++j) for(int i=i0;i<=i1;++i) {
    const auto f=d.face(i,j,k);
    out << (first ? "" : ",") << "{\"position\":[" << d.x[i] << ',' << d.y[j] << ',' << d.z[k]
        << "],\"flag\":" << flag(i,j,k) << ",\"velocity\":["
        << .5f*(u[f]+u[f+1]) << ',' << .5f*(v[f]+v[f+d.nx()]) << ','
        << .5f*(w[f]+w[f+d.nx()*d.ny()]) << "]}";
    first=false;
  }
  out << "],\"faces\":[";
  for(int c=0;c<3;++c) {
    out << (c ? ",[" : "["); first=true;
    for(int k=k0;k<=k1+(c==2);++k) for(int j=j0;j<=j1+(c==1);++j)
      for(int i=i0;i<=i1+(c==0);++i) {
        const auto f=d.face(i,j,k);
        out << (first ? "" : ",") << "{\"position\":["
            << (c==0 ? i*d.dx() : d.x[i]) << ','
            << (c==1 ? j*d.dy() : d.y[j]) << ','
            << (c==2 ? d.z_face[k] : d.z[k]) << "],\"value\":"
            << (c==0 ? u[f] : c==1 ? v[f] : w[f]) << ",\"flags\":["
            << flag(i-(c==0),j-(c==1),k-(c==2)) << ',' << flag(i,j,k) << "]}";
        first=false;
      }
    out << ']';
  }
  out << "],\"query_flag\":" << flag(cx,cy,int(std::upper_bound(d.z_face.begin(),d.z_face.end(),height)-d.z_face.begin())-1) << '}';
}

static void write_stage(std::ostream &out,const WINDSGeneralData &data,
                        const HorizontalControl &control,const std::vector<double> &heights,bool initial)
{
  auto ii=support_indices(data.domain.x,control.ox), jj=support_indices(data.domain.y,control.oy);
  out << "{\"planes\":"; write_planes(out,data,heights,ii,jj,initial);
  out << ",\"patches\":[";
  bool first=true;
  for(double h:heights) for(const auto &p:std::vector<std::array<double,2>>{{27,21},{21,23},{51,35}}) {
    out << (first ? "" : ","); first=false;
    write_patch(out,data,p[0]-control.ox,p[1]-control.oy,h,initial);
  }
  out << "]}";
}

int main(int argc,char **argv) try {
  if(argc!=4) throw std::invalid_argument("Usage: near_wall_probe direction fixed_sweeps max_cells < horizontal_input");
  const double direction=std::stod(argv[1]);
  const int sweeps=std::stoi(argv[2]);
  if(sweeps<0 || sweeps>100000) throw std::invalid_argument("Invalid sweep budget");
#ifdef _OPENMP
  omp_set_dynamic(0); omp_set_num_threads(2);
#endif
  const std::lock_guard<std::mutex> lock(native_mutex());
  Messages messages; const BufferedLogSink sink(messages);
  GridConfig grid; BuildingArrays buildings; std::vector<double> heights;
  const auto control=read_horizontal(grid,buildings,heights);
  grid.max_cells=std::stoll(argv[3]);
  ModelSettings model; model.sensor_x=5-control.ox; model.sensor_y=5-control.oy;
  if(control.disabled&1) model.rooftop_flag=0;
  if(control.disabled&2) model.upwind_cavity_flag=0;
  if(control.disabled&4) model.street_canyon_flag=0;
  if(control.disabled&8) model.wake_flag=0;
  if(control.disabled&16) model.sidewall_flag=0;
  auto start=Clock::now();
  QESInputs inputs(grid,model,buildings); inputs.set_condition({5,direction,10});
  WINDSGeneralData data(&inputs.input,make_domain(inputs),CPU_Type);
  data.applyWindProfile(&inputs.input,0,CPU_Type);
  std::ostringstream out; out << std::setprecision(17);
  out << "{\"backend\":\"" << backend << "\",\"direction\":" << direction
      << ",\"resolution\":" << grid.cell_size << ",\"origin\":[" << control.ox << ',' << control.oy
      << "],\"extent\":[" << control.lx << ',' << control.ly << "],\"disabled_mask\":" << control.disabled
      << ",\"cells\":" << std::int64_t(grid.nx)*grid.ny*grid.nz << ",\"start\":\"zero\",\"z_faces\":[";
  for(int k=1;k<data.domain.z_face.size();++k) out << (k==1 ? "" : ",") << data.domain.z_face[k];
  out << "],\"stages\":{\"profile\":"; write_stage(out,data,control,heights,true);
  data.applyParametrizations(&inputs.input);
  out << ",\"initial\":"; write_stage(out,data,control,heights,true);
  const double preparation=elapsed(start);
  DivergenceStats residual; double solve_time=0;
  if(sweeps) {
    PrecisionSolver solver(data.domain,1e-12); start=Clock::now();
    solver.solve(&data,sweeps,true); solve_time=elapsed(start); residual=divergence_stats(data);
    out << ",\"final\":"; write_stage(out,data,control,heights,false);
  }
  struct rusage usage; getrusage(RUSAGE_SELF,&usage);
  out << "},\"iterations\":" << sweeps << ",\"preparation_seconds\":" << preparation
      << ",\"solve_seconds\":" << solve_time << ",\"max_divergence\":" << residual.interior_max
      << ",\"rms_divergence\":" << residual.interior_rms << ",\"assessed_cells\":" << residual.cells
      << ",\"peak_rss_bytes\":" << usage.ru_maxrss
#ifndef __APPLE__
      *1024
#endif
      << "}\n";
  std::cout << out.str(); return 0;
} catch(const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
