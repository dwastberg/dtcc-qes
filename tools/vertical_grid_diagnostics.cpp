// Independent, study-only reconstruction of the alpha1 = alpha2 = 1 CPU path.
#include "vertical_grid_diagnostics.h"
#include "model_inputs.h"
#include "divergence.h"
#include "winds/WINDSGeneralData.h"
#include "winds/SolverFactory.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <ostream>
#include <stdexcept>

namespace study {
namespace {
using Index = std::array<int, 3>;
using Faces = std::array<double, 6>; // east, west, north, south, above, below

bool solid(const WINDSGeneralData &a, int i, int j, int k)
{
  const auto &d = a.domain;
  if (i < 0 || i >= d.nx()-1 || j < 0 || j >= d.ny()-1 || k < 1 || k >= d.nz()-1)
    return false;
  const int flag = a.icellflag[d.cell(i,j,k)];
  return flag == 0 || flag == 2;
}

template<class Real, class Multiplier>
Real corrected_face(const WINDSGeneralData &a, const std::vector<Multiplier> &lambda,
                    int axis, int i, int j, int k, bool zero_solids)
{
  const auto &d = a.domain;
  const auto f = d.face(i,j,k);
  const auto &initial = axis == 0 ? a.u0 : axis == 1 ? a.v0 : a.w0;
  Real result = initial[f];
  if (k >= 1 && k < d.nz()-2 && j >= 1 && j < d.ny()-1 && i >= 1 && i < d.nx()-1) {
    const auto c = d.cell(i,j,k);
    const auto neighbour = d.cellAdd(c, axis == 0 ? -1 : 0, axis == 1 ? -1 : 0,
                                   axis == 2 ? -1 : 0);
    const Real coeff = axis == 0 ? a.f[c] : axis == 1 ? a.h[c] : a.n[c];
    const Real spacing = axis == 0 ? d.dx() : axis == 1 ? d.dy() : d.dz_array[k];
    // Real=float reproduces the production operand order; Real=double widens
    // operands BEFORE the subtraction, products and final addition.
    result += Real(0.5) * coeff * spacing * (Real(lambda[c]) - Real(lambda[neighbour]));
  }
  if (zero_solids && (solid(a,i,j,k)
      || solid(a, i-(axis == 0), j-(axis == 1), k-(axis == 2)))) result = 0;
  return result;
}

template<class Function>
Faces faces_at(int i, int j, int k, Function value)
{
  return {value(0,i+1,j,k), value(0,i,j,k), value(1,i,j+1,k), value(1,i,j,k),
          value(2,i,j,k+1), value(2,i,j,k)};
}

Faces stored_faces(const WINDSGeneralData &a, int i, int j, int k, bool initial = false)
{
  return faces_at(i,j,k, [&](int axis, int x, int y, int z) {
    const auto &field = axis == 0 ? (initial ? a.u0 : a.u)
                      : axis == 1 ? (initial ? a.v0 : a.v) : (initial ? a.w0 : a.w);
    return double(field[a.domain.face(x,y,z)]);
  });
}

template<class Real, class Multiplier>
Faces reconstructed(const WINDSGeneralData &a, const std::vector<Multiplier> &lambda,
                    int i, int j, int k, bool zero)
{
  return faces_at(i,j,k, [&](int axis, int x, int y, int z) {
    return double(corrected_face<Real>(a,lambda,axis,x,y,z,zero));
  });
}

double flux(const WINDSGeneralData &a, int i, int j, int k, const Faces &v)
{
  const auto &d = a.domain;
  const auto c = d.cell(i,j,k);
  const double dx = d.dx(), dy = d.dy(), dz = d.dz_array[k];
  // Recover open areas independently from the scaled stencil coefficients.
  const double east = double(a.e[c])*dx*dx, west = double(a.f[c])*dx*dx;
  const double north = double(a.g[c])*dy*dy, south = double(a.h[c])*dy*dy;
  const double above = double(a.m[c])*dz*0.5*(dz+d.dz_array[k+1]);
  const double below = double(a.n[c])*dz*0.5*(dz+d.dz_array[k-1]);
  return ((east*v[0]-west*v[1])*dy*dz + (north*v[2]-south*v[3])*dx*dz
          + (above*v[4]-below*v[5])*dx*dy)/(dx*dy*dz);
}

template<class Real>
double stencil(const WINDSGeneralData &a, const std::vector<Real> &lambda, long c)
{
  const auto &d = a.domain;
  // Difference form avoids cancellation from a second diagnostic's large
  // diagonal product. The underlying coefficients remain the actual floats.
  return double(a.e[c])*(double(lambda[d.cellAdd(c,1,0,0)])-lambda[c])
       + double(a.f[c])*(double(lambda[d.cellAdd(c,-1,0,0)])-lambda[c])
       + double(a.g[c])*(double(lambda[d.cellAdd(c,0,1,0)])-lambda[c])
       + double(a.h[c])*(double(lambda[d.cellAdd(c,0,-1,0)])-lambda[c])
       + double(a.m[c])*(double(lambda[d.cellAdd(c,0,0,1)])-lambda[c])
       + double(a.n[c])*(double(lambda[d.cellAdd(c,0,0,-1)])-lambda[c]);
}

struct Norm {
  double maximum = 0, signed_value = 0, squares = 0, volume = 0;
  std::size_t cells = 0;
  Index index{};
  void add(double value, Index idx, double weight) {
    if (!std::isfinite(value)) throw std::runtime_error("Nonfinite diagnostic value");
    if (std::abs(value) > maximum) { maximum = std::abs(value); signed_value = value; index = idx; }
    squares += weight*value*value; volume += weight; ++cells;
  }
  double rms() const { return volume ? std::sqrt(squares/volume) : 0; }
};

void write_norm(std::ostream &out, const Norm &n, const qes::Domain &d)
{
  out << "{\"max\":" << n.maximum << ",\"rms\":" << n.rms() << ",\"cells\":" << n.cells
      << ",\"signed_at_max\":" << n.signed_value << ",\"ijk\":[" << n.index[0] << ','
      << n.index[1] << ',' << n.index[2] << "]";
  if (n.maximum > 0) out << ",\"xyz\":[" << d.x[n.index[0]] << ',' << d.y[n.index[1]]
                           << ',' << d.z[n.index[2]] << ']';
  out << '}';
}

struct Cell {
  Index index;
  double residual, initial, prediction, stencil_residual, rhs_gap;
};
struct Inspection {
  std::map<std::string, Norm> norms;
  std::vector<Cell> worst;
  double max_face_mismatch = 0;
};

// An isolated warm-start experiment, not a new selectable production solver.
// Preserve coefficients, geometry, boundary conditions and the backend's node
// ordering. Widen multiplier storage, RHS construction and update arithmetic.
void refine(const WINDSGeneralData &a, std::vector<double> &lambda,
            const std::vector<double> &rhs, int sweeps)
{
  const auto &d = a.domain;
  const double omega = double(1.78f);
  for (int iteration = 0; iteration < sweeps; ++iteration) {
#ifdef _OPENMP
    constexpr int colours = 2;
#else
    constexpr int colours = 1;
#endif
    for (int colour = 0; colour < colours; ++colour)
      for (int k = 1; k < d.nz()-2; ++k)
        for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
          if (colours == 2 && (i+j+k)%2 != colour) continue;
          const auto c = d.cell(i,j,k);
          const double diagonal = double(a.e[c])+a.f[c]+a.g[c]+a.h[c]+a.m[c]+a.n[c];
          const double neighbours = double(a.e[c])*lambda[d.cellAdd(c,1,0,0)]
                                  + double(a.f[c])*lambda[d.cellAdd(c,-1,0,0)]
                                  + double(a.g[c])*lambda[d.cellAdd(c,0,1,0)]
                                  + double(a.h[c])*lambda[d.cellAdd(c,0,-1,0)]
                                  + double(a.m[c])*lambda[d.cellAdd(c,0,0,1)]
                                  + double(a.n[c])*lambda[d.cellAdd(c,0,0,-1)];
          lambda[c] = omega/diagonal*(neighbours-rhs[c]) + (1-omega)*lambda[c];
        }
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i)
      lambda[d.cell(i,j,0)] = lambda[d.cell(i,j,1)];
  }
}

std::vector<double> double_rhs(const WINDSGeneralData &a)
{
  const auto &d = a.domain;
  std::vector<double> rhs(d.numCellCentered(),0);
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i)
      rhs[d.cell(i,j,k)] = -2*flux(a,i,j,k,stored_faces(a,i,j,k,true));
  return rhs;
}

std::map<std::string,Norm> precision_norms(const WINDSGeneralData &a,
                                        const std::vector<double> &lambda)
{
  const auto &d = a.domain;
  std::map<std::string,Norm> result;
  for (int k = 1; k < d.nz()-2; ++k)
    for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
      if (solid(a,i,j,k)) continue;
      const auto exact = reconstructed<double>(a,lambda,i,j,k,true);
      auto rounded = exact;
      // Cast only the completed face correction, retaining double multipliers.
      for (auto &value : rounded) value = float(value);
      const double volume = double(d.dx())*d.dy()*d.dz_array[k];
      if (k == d.nz()-3) {
        result["top_band_double_flux"].add(flux(a,i,j,k,exact),{i,j,k},volume);
        result["top_band_cast_float_flux"].add(flux(a,i,j,k,rounded),{i,j,k},volume);
        continue;
      }
      result["double_flux"].add(flux(a,i,j,k,exact),{i,j,k},volume);
      result["cast_float_flux"].add(flux(a,i,j,k,rounded),{i,j,k},volume);
      const double initial = flux(a,i,j,k,stored_faces(a,i,j,k,true));
      const double prediction = initial+0.5*stencil(a,lambda,d.cell(i,j,k));
      result["operator_flux_gap"].add(flux(a,i,j,k,exact)-prediction,{i,j,k},volume);
    }
  return result;
}

std::vector<double> pedestrian_changes(const WINDSGeneralData &a,
                                       const std::vector<double> &lambda)
{
  const auto &d = a.domain;
  const auto upper = std::lower_bound(d.z.begin()+1,d.z.end(),1.5);
  if (upper == d.z.end() || upper == d.z.begin()+1)
    throw std::invalid_argument("Precision probe requires a bracketed 1.5 m plane");
  const int hi = upper-d.z.begin(), lo = *upper == 1.5 ? hi : hi-1;
  const double weight = lo == hi ? 0 : (1.5-d.z[lo])/(d.z[hi]-d.z[lo]);
  std::vector<double> changes;
  for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
    if (solid(a,i,j,lo) || solid(a,i,j,hi)) continue;
    std::array<double,3> delta{};
    for (int k : {lo,hi}) {
      const auto stored = stored_faces(a,i,j,k);
      const auto corrected = reconstructed<double>(a,lambda,i,j,k,true);
      const double w = k == lo ? 1-weight : weight;
      for (int axis = 0; axis < 3; ++axis) {
        const float before = 0.5f*(float(stored[2*axis])+float(stored[2*axis+1]));
        const float after = 0.5f*(float(corrected[2*axis])+float(corrected[2*axis+1]));
        delta[axis] += w*(double(after)-before);
      }
      if (lo == hi) break;
    }
    changes.push_back(std::sqrt(delta[0]*delta[0]+delta[1]*delta[1]+delta[2]*delta[2])/5);
  }
  if (changes.empty()) throw std::runtime_error("No valid precision-probe samples");
  std::sort(changes.begin(),changes.end());
  return changes;
}

Inspection inspect(const WINDSGeneralData &a, const std::vector<float> &lambda,
                   const std::vector<float> &rhs)
{
  const auto &d = a.domain;
  if (lambda.size() != std::size_t(d.numCellCentered()) || rhs.size() != lambda.size())
    throw std::invalid_argument("Diagnostic multiplier/RHS size mismatch");
  Inspection result;
  for (int k = 1; k < d.nz()-3; ++k)
    for (int j = 1; j < d.ny()-2; ++j) for (int i = 1; i < d.nx()-2; ++i) {
      if (solid(a,i,j,k)) continue;
      const Index index{i,j,k};
      const auto c = d.cell(i,j,k);
      const double volume = double(d.dx())*d.dy()*d.dz_array[k];
      const auto stored = stored_faces(a,i,j,k);
      const auto f_before = reconstructed<float>(a,lambda,i,j,k,false);
      const auto f_after = reconstructed<float>(a,lambda,i,j,k,true);
      const auto d_before = reconstructed<double>(a,lambda,i,j,k,false);
      const auto d_after = reconstructed<double>(a,lambda,i,j,k,true);
      const double initial = flux(a,i,j,k,stored_faces(a,i,j,k,true));
      const double actual = flux(a,i,j,k,stored);
      const double predicted = initial + 0.5*stencil(a,lambda,c);
      const double stencil_residual = 0.5*(stencil(a,lambda,c)-rhs[c]);
      const double rhs_gap = initial + 0.5*rhs[c];
      auto add = [&](const char *name, double value) { result.norms[name].add(value,index,volume); };
      add("stored_flux",actual);
      add("float_before_zero",flux(a,i,j,k,f_before));
      add("float_after_zero",flux(a,i,j,k,f_after));
      add("double_before_zero",flux(a,i,j,k,d_before));
      add("double_after_zero",flux(a,i,j,k,d_after));
      add("stencil_prediction",predicted);
      add("stencil_residual",stencil_residual);
      add("rhs_rounding",rhs_gap);
      add("operator_flux_gap",flux(a,i,j,k,d_before)-predicted);
      add("solid_zeroing_effect",flux(a,i,j,k,d_after)-flux(a,i,j,k,d_before));
      add("float_reconstruction_gap",flux(a,i,j,k,f_after)-actual);
      add("float_correction_effect",flux(a,i,j,k,f_after)-flux(a,i,j,k,d_after));
      bool near_solid = false;
      for (Index delta : {Index{1,0,0}, {-1,0,0}, {0,1,0}, {0,-1,0}, {0,0,1}, {0,0,-1}})
        near_solid = near_solid || solid(a,i+delta[0],j+delta[1],k+delta[2]);
      add(near_solid ? "stored_adjacent_solid" : "stored_away_from_solid",actual);
      const bool edge = i == 1 || i == d.nx()-3 || j == 1 || j == d.ny()-3 || k == 1;
      add(edge ? "stored_boundary_adjacent" : "stored_away_from_boundary",actual);
      for (int face = 0; face < 6; ++face)
        result.max_face_mismatch = std::max(result.max_face_mismatch,std::abs(stored[face]-f_after[face]));
      result.worst.push_back({index,actual,initial,predicted,stencil_residual,rhs_gap});
    }
  std::partial_sort(result.worst.begin(),result.worst.begin()+std::min<std::size_t>(8,result.worst.size()),
                    result.worst.end(),[](const Cell &x, const Cell &y) {
                      return std::abs(x.residual) > std::abs(y.residual);
                    });
  result.worst.resize(std::min<std::size_t>(8,result.worst.size()));
  return result;
}
} // namespace

void write_solver_diagnostics(std::ostream &out, const WINDSGeneralData &a,
                              const std::vector<float> &lambda,
                              const std::vector<float> &previous,
                              const std::vector<float> &rhs)
{
  if (previous.size() != lambda.size()) throw std::invalid_argument("Previous multiplier size mismatch");
  const auto result = inspect(a,lambda,rhs);
  const auto oracle = dtcc_qes::divergence_stats(a);
  const auto &actual = result.norms.at("stored_flux");
  if (actual.cells != oracle.cells || std::abs(actual.maximum-oracle.interior_max) > 1e-12
      || std::abs(actual.rms()-oracle.interior_rms) > 1e-12)
    throw std::runtime_error("Diagnostic flux differs from production divergence oracle");
  out << "{\"max_face_reconstruction_gap\":" << result.max_face_mismatch << ",\"norms\":{";
  bool first = true;
  for (const auto &[name,norm] : result.norms) {
    out << (first ? "" : ",") << '"' << name << "\":";
    write_norm(out,norm,a.domain); first = false;
  }
  out << "},\"worst_stored_cells\":[";
  first = true;
  for (const auto &cell : result.worst) {
    const auto [i,j,k] = cell.index;
    const auto &d = a.domain;
    const auto c = d.cell(i,j,k);
    out << (first ? "" : ",") << "{\"ijk\":[" << i << ',' << j << ',' << k
        << "],\"xyz\":[" << d.x[i] << ',' << d.y[j] << ',' << d.z[k]
        << "],\"flag\":" << a.icellflag[c] << ",\"stored_flux\":" << cell.residual
        << ",\"initial_flux\":" << cell.initial << ",\"stencil_prediction\":" << cell.prediction
        << ",\"stencil_residual\":" << cell.stencil_residual << ",\"rhs_rounding\":" << cell.rhs_gap
        << ",\"rhs\":" << rhs[c] << ",\"lambda\":" << lambda[c]
        << ",\"lambda_update\":" << double(lambda[c])-previous[c]
        << ",\"lambda_ulp\":" << double(std::nextafter(lambda[c],std::numeric_limits<float>::infinity()))-lambda[c]
        << ",\"neighbour_flags\":[";
    bool next = false;
    for (Index delta : {Index{1,0,0}, {-1,0,0}, {0,1,0}, {0,-1,0}, {0,0,1}, {0,0,-1}}) {
      out << (next ? "," : "") << a.icellflag[d.cellAdd(c,delta[0],delta[1],delta[2])]; next = true;
    }
    out << "],\"coefficients\":[" << a.e[c] << ',' << a.f[c] << ',' << a.g[c] << ',' << a.h[c]
        << ',' << a.m[c] << ',' << a.n[c] << "]}";
    first = false;
  }
  out << "]}";
}

void write_precision_probe(std::ostream &out, const WINDSGeneralData &a,
                           const std::vector<float> &starting_lambda)
{
  std::vector<double> lambda(starting_lambda.begin(),starting_lambda.end());
  const auto rhs = double_rhs(a);
  int completed = 0;
  out << "{\"warm_start\":true,\"parallel_updates\":false,\"checkpoints\":[";
  for (int target : {0,100,1000}) {
    refine(a,lambda,rhs,target-completed);
    completed = target;
    const auto norms = precision_norms(a,lambda);
    const auto changes = pedestrian_changes(a,lambda);
    const double p = 0.95*(changes.size()-1);
    const auto lower = std::size_t(p), upper = std::min(lower+1,changes.size()-1);
    const double p95 = changes[lower]+(p-lower)*(changes[upper]-changes[lower]);
    out << (target ? "," : "") << "{\"additional_sweeps\":" << target
        << ",\"max_pedestrian_vector_change_over_Uref\":" << changes.back()
        << ",\"p95_pedestrian_vector_change_over_Uref\":" << p95
        << ",\"valid_samples\":" << changes.size() << ",\"norms\":{";
    bool first = true;
    for (const auto &[name,norm] : norms) {
      out << (first ? "" : ",") << '"' << name << "\":";
      write_norm(out,norm,a.domain); first = false;
    }
    out << "}}";
  }
  out << "]}";
}

void diagnostics_self_test()
{
  using namespace dtcc_qes;
  GridConfig grid; grid.nx = grid.ny = 8; grid.nz = 8;
  grid.dz_layers.assign(grid.nz,0.5);
  ModelSettings model; model.sensor_x = model.sensor_y = 5;
  ModelInputs inputs(grid,model,BuildingArrays{{},{0},{},{},{}});
  WINDSGeneralData a(make_domain(inputs), inputs.buildings, inputs.parameterizations, inputs.inflow.site_z0);
  const auto &d = a.domain;
  std::fill(a.icellflag.begin(),a.icellflag.end(),1);
  for (auto *field : {&a.u0,&a.v0,&a.w0}) std::fill(field->begin(),field->end(),0);
  for (auto *coeff : {&a.e,&a.f,&a.g,&a.h})
    std::fill(coeff->begin(),coeff->end(),1/(d.dx()*d.dx()));
  for (auto *coeff : {&a.m,&a.n}) std::fill(coeff->begin(),coeff->end(),4);
  std::vector<float> lambda(d.numCellCentered()), rhs(lambda.size(),0);
  for (int k = 0; k < d.nz()-1; ++k)
    for (int j = 0; j < d.ny()-1; ++j) for (int i = 0; i < d.nx()-1; ++i)
      lambda[d.cell(i,j,k)] = d.x[i]*d.x[i];
  for (int k = 0; k < d.nz(); ++k)
    for (int j = 0; j < d.ny(); ++j) for (int i = 0; i < d.nx(); ++i) {
      a.u[d.face(i,j,k)] = corrected_face<float>(a,lambda,0,i,j,k,true);
      a.v[d.face(i,j,k)] = corrected_face<float>(a,lambda,1,i,j,k,true);
      a.w[d.face(i,j,k)] = corrected_face<float>(a,lambda,2,i,j,k,true);
    }
  auto require = [](bool ok) { if (!ok) throw std::runtime_error("Solver diagnostics self-test failed"); };
  const auto result = inspect(a,lambda,rhs);
  // lambda=x^2 gives 0.5*laplacian(lambda)=1, independently of resolution.
  require(std::abs(result.norms.at("stored_flux").maximum-1) < 1e-12);
  require(std::abs(result.norms.at("stencil_prediction").rms()-1) < 1e-12);
  require(result.norms.at("operator_flux_gap").maximum < 1e-12);
  require(result.max_face_mismatch == 0);
  // Homogeneous equation, fixed lateral/top multipliers: refining the x^2
  // starting guess must reduce its known unit residual without changing edges.
  std::vector<double> precise(lambda.begin(),lambda.end());
  const auto precise_rhs = double_rhs(a);
  refine(a,precise,precise_rhs,200);
  const auto refined = precision_norms(a,precise);
  require(refined.at("double_flux").maximum < 1e-8);
  require(refined.at("cast_float_flux").maximum < 1e-5);
  require(refined.at("operator_flux_gap").maximum < 1e-12);
  require(precise[d.cell(0,3,3)] == lambda[d.cell(0,3,3)]);
  a.u[d.face(3,3,3)] += 0.125f;
  require(inspect(a,lambda,rhs).max_face_mismatch == 0.125);
  // Both building and terrain flags must zero either side of a face.
  for (int flag : {0,2}) {
    a.icellflag[d.cell(3,3,3)] = flag;
    require(corrected_face<double>(a,lambda,0,3,3,3,true) == 0);
    require(corrected_face<double>(a,lambda,0,4,3,3,true) == 0);
    require(corrected_face<double>(a,lambda,0,4,3,3,false) != 0);
  }
}
} // namespace study
