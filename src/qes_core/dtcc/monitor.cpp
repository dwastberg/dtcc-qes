#include "monitor.h"
#include "util/QESException.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <type_traits>

namespace dtcc_qes {
namespace {
std::size_t add(std::size_t a,std::size_t b) {
  if (b > std::numeric_limits<std::size_t>::max()-a) throw qes::InputError("Monitor memory estimate overflow");
  return a+b;
}
std::size_t mul(std::size_t a,std::size_t b) {
  if (b && a > std::numeric_limits<std::size_t>::max()/b) throw qes::InputError("Monitor memory estimate overflow");
  return a*b;
}
MonitorSample invalid() {
  const double n = std::numeric_limits<double>::quiet_NaN();
  return {{n,n,n},false};
}
double speed(const MonitorSample &a) { return std::hypot(a.velocity[0],a.velocity[1],a.velocity[2]); }
double distance(const MonitorSample &a,const MonitorSample &b) {
  return std::hypot(a.velocity[0]-b.velocity[0],a.velocity[1]-b.velocity[1],a.velocity[2]-b.velocity[2]);
}
MonitorNorm norm(std::vector<double> &v) {
  if (v.empty()) return {};
  const double maximum = *std::max_element(v.begin(),v.end());
  const double p = .95*double(v.size()-1);
  const auto lo = std::size_t(p), hi = std::min(lo+1,v.size()-1);
  std::nth_element(v.begin(),v.begin()+lo,v.end());
  const double lower = v[lo];
  const double upper = hi == lo ? lower : *std::min_element(v.begin()+hi,v.end());
  return {{lower+(p-double(lo))*(upper-lower)},{maximum}};
}
MonitorNorm normalized(MonitorNorm n,double uref) {
  if (!(uref > 0)) return {};
  if (n.p95) { *n.p95 /= uref; if (!std::isfinite(*n.p95)) n.p95.reset(); }
  if (n.maximum) { *n.maximum /= uref; if (!std::isfinite(*n.maximum)) n.maximum.reset(); }
  return n;
}
std::optional<double> ratio(std::optional<double> now,std::optional<double> before) {
  if (!now || !before || !(*before > 0)) return {};
  const double result = *now / *before;
  return std::isfinite(result) ? std::optional<double>(result) : std::nullopt;
}
MonitorFlux flux_record(const solver::MassDiagnostics::Flux &a) {
  return {a.net_cell_flux,a.boundary_flux,a.absolute_cell_flux,a.throughflow,
          a.low_flow_cells,a.resolved_cells,a.unassessed_cells,a.relative_max,a.relative_rms};
}
template<class A> Monitor::Support bracket(const A &axis,double point) {
  if (point < double(axis.front()) || point > double(axis.back())) return {};
  const auto at = std::lower_bound(axis.begin(),axis.end(),point,[](float a,double b) { return double(a)<b; });
  const int hi = int(at-axis.begin());
  if (at != axis.end() && double(*at) == point) return {hi,hi,0};
  return {hi-1,hi,(point-double(axis[hi-1]))/(double(axis[hi])-double(axis[hi-1]))};
}
}

Monitor::Monitor(const qes::Domain &domain,const void *state,std::uint64_t epoch,MonitorSpec spec)
  : spec_(std::move(spec)),domain_(domain),state_(state),epoch_(epoch) {
  if (spec_.frame != MonitorFrame::Local && spec_.frame != MonitorFrame::World)
    throw qes::InputError("Unknown monitor coordinate frame");
  if (!std::isfinite(spec_.reference_speed) || spec_.reference_speed < 0
      || !std::all_of(spec_.origin.begin(),spec_.origin.end(),[](double x) { return std::isfinite(x); })
      || (spec_.low_flow_fraction && (!std::isfinite(*spec_.low_flow_fraction) || *spec_.low_flow_fraction <= 0)))
    throw qes::InputError("Monitor scales and origin must be finite; Uref is nonnegative and flow fraction positive");
  if (!spec_.short_window || spec_.long_window <= spec_.short_window
      || spec_.history_limit < add(spec_.long_window,1) || !spec_.memory_limit_bytes
      || (spec_.heights.empty() && spec_.receptors.empty()))
    throw qes::InputError("Monitor requires observables, bounded history and two ordered positive windows");
  const double ox = spec_.frame == MonitorFrame::World ? spec_.origin[0] : 0;
  const double oy = spec_.frame == MonitorFrame::World ? spec_.origin[1] : 0;
  auto r = spec_.region;
  r.x_first -= ox; r.x_last -= ox; r.y_first -= oy; r.y_last -= oy;
  if (!std::isfinite(r.x_first) || !std::isfinite(r.x_last) || !std::isfinite(r.y_first) || !std::isfinite(r.y_last)
      || r.x_first < 0 || r.y_first < 0 || r.x_first >= r.x_last || r.y_first >= r.y_last
      || r.x_last > double(domain.dx())*(domain.nx()-1) || r.y_last > double(domain.dy())*(domain.ny()-1))
    throw qes::InputError("Monitor region must be an explicit half-open rectangle inside the physical domain");
  const auto lower = [](const auto &a,double v) {
    return int(std::lower_bound(a.begin(),a.end(),v,[](float x,double y) { return double(x)<y; })-a.begin());
  };
  i_first_ = lower(domain.x,r.x_first); i_last_ = lower(domain.x,r.x_last);
  j_first_ = lower(domain.y,r.y_first); j_last_ = lower(domain.y,r.y_last);
  plane_points_ = mul(std::size_t(i_last_-i_first_),std::size_t(j_last_-j_first_));
  std::set<double> unique_heights;
  std::set<int> layers;
  const auto include = [&](Support s) { if (s.lo >= 0) { layers.insert(s.lo); layers.insert(s.hi); } };
  for (double height : spec_.heights) {
    if (!unique_heights.insert(height).second) throw qes::InputError("Duplicate monitor height");
    const auto s = vertical(height); heights_.push_back(s); include(s);
  }
  std::set<std::string> ids;
  for (const auto &receptor : spec_.receptors) {
    if (receptor.id.empty() || !ids.insert(receptor.id).second
        || !std::isfinite(receptor.location.x) || !std::isfinite(receptor.location.y))
      throw qes::InputError("Receptors require unique IDs and finite coordinates");
    ReceptorSupport compiled;
    compiled.vertical = vertical(receptor.location.height_agl); include(compiled.vertical);
    const auto x = bracket(domain.x,receptor.location.x-ox), y = bracket(domain.y,receptor.location.y-oy);
    if (x.lo >= 0 && y.lo >= 0) {
      for (int yy = 0; yy < (y.lo == y.hi ? 1 : 2); ++yy)
        for (int xx = 0; xx < (x.lo == x.hi ? 1 : 2); ++xx) {
          const double weight = (xx ? x.weight : (x.lo == x.hi ? 1 : 1-x.weight))
                              * (yy ? y.weight : (y.lo == y.hi ? 1 : 1-y.weight));
          if (!(weight > 0)) continue;
          compiled.cells[compiled.count] = std::size_t(xx ? x.hi : x.lo)
            + std::size_t(yy ? y.hi : y.lo)*(domain.nx()-1);
          compiled.weights[compiled.count++] = weight;
        }
    }
    receptors_.push_back(compiled);
  }
  for (int layer : layers) {
    if (!slabs_.empty() && slabs_.back().layers.last == layer) ++slabs_.back().layers.last;
    else slabs_.push_back({{layer,layer+1},domain.nx()-1,domain.ny()-1,{}, {}});
  }
  std::set<std::string> names;
  const auto region = [&](std::string name,int i0,int i1,int j0,int j1,int k0,int k1) {
    if (!names.insert(name).second) throw qes::InputError("Duplicate monitor mass region");
    const int nx = domain.nx()-1, ny = domain.ny()-1, nz = domain.nz()-2;
    const auto requested_xy = mul(std::size_t(i1-i0),std::size_t(j1-j0));
    const int first_i = std::clamp(i0,1,nx-1), last_i = std::clamp(i1,first_i,nx-1);
    const int first_j = std::clamp(j0,1,ny-1), last_j = std::clamp(j1,first_j,ny-1);
    const int first_k = std::clamp(k0,0,nz-1), last_k = std::clamp(k1,first_k,nz-1);
    const auto assessed_xy = mul(std::size_t(last_i-first_i),std::size_t(last_j-first_j));
    regions_.push_back({std::move(name),{first_i,last_i,first_j,last_j,first_k,last_k},
      mul(requested_xy-assessed_xy,std::size_t(k1-k0)),mul(assessed_xy,std::size_t(k1-k0-(last_k-first_k)))});
  };
  if (spec_.global_mass) region("global",0,domain.nx()-1,0,domain.ny()-1,0,domain.nz()-2);
  for (std::size_t h = 0; h < heights_.size(); ++h) {
    const auto s = heights_[h];
    region("height:"+std::to_string(h),i_first_,i_last_,j_first_,j_last_,s.lo < 0 ? 0 : s.lo,s.hi < 0 ? 0 : s.hi+1);
  }
  for (const auto &q : spec_.mass_regions) {
    const int i1 = q.i_last == -1 ? domain.nx()-2 : q.i_last;
    const int j1 = q.j_last == -1 ? domain.ny()-2 : q.j_last;
    const int k1 = q.k_last == -1 ? domain.nz()-3 : q.k_last;
    if (q.name.empty() || q.i_first < 0 || i1 < q.i_first || i1 > domain.nx()-1
        || q.j_first < 0 || j1 < q.j_first || j1 > domain.ny()-1
        || q.k_first < 0 || k1 < q.k_first || k1 > domain.nz()-2)
      throw qes::InputError("Invalid physical monitor mass region");
    region(q.name,q.i_first,i1,q.j_first,j1,q.k_first,k1);
  }
  // Check the complete slab/ring/scratch/history estimate before their allocation.
  const auto points = add(mul(plane_points_,heights_.size()),receptors_.size());
  const auto frames = add(spec_.long_window,1);
  planned_bytes_ = allocated_bytes();
  for (const auto &slab : slabs_)
    planned_bytes_ = add(planned_bytes_,mul(mul(std::size_t(slab.layers.last-slab.layers.first),
      std::size_t(domain.numHorizontalCellCentered())),3*sizeof(float)+sizeof(std::int32_t)));
  planned_bytes_ = add(planned_bytes_,mul(frames,add(sizeof(Frame),add(mul(points,sizeof(MonitorSample)),mul(heights_.size(),sizeof(MonitorPeak))))));
  const auto children = add(mul(heights_.size(),sizeof(MonitorHeightRecord)),
    add(mul(receptors_.size(),sizeof(MonitorReceptorRecord)),mul(regions_.size(),sizeof(MonitorMassRecord))));
  planned_bytes_ = add(planned_bytes_,mul(spec_.history_limit,add(sizeof(MonitorCheckpoint),children)));
  planned_bytes_ = add(planned_bytes_,mul(std::max<std::size_t>(1,plane_points_),2*sizeof(double)));
  if (planned_bytes_ > spec_.memory_limit_bytes) throw qes::InputError("Monitor slab/window/history memory exceeds configured limit");
  for (auto &slab : slabs_) {
    const auto count = std::size_t(slab.layers.last-slab.layers.first)*domain.numHorizontalCellCentered();
    slab.velocity.resize(count*3); slab.cell_flags.resize(count);
  }
  frames_.resize(frames);
  for (auto &f : frames_) { f.samples.resize(points); f.peaks.resize(heights_.size()); }
  history_.resize(spec_.history_limit);
  for (auto &c : history_) { c.heights.resize(heights_.size()); c.receptors.resize(receptors_.size()); c.mass.resize(regions_.size()); }
  vector_scratch_.reserve(std::max<std::size_t>(1,plane_points_));
  speed_scratch_.reserve(std::max<std::size_t>(1,plane_points_));
  if (allocated_bytes() > spec_.memory_limit_bytes) throw qes::InputError("Allocated monitor capacity exceeds configured limit");
}

Monitor::Support Monitor::vertical(double height) const {
  if (!std::isfinite(height) || height < 0 || height > double(domain_.z_face.back()))
    throw qes::InputError("Monitor height must be finite and inside the physical domain");
  if (height < double(domain_.z[1]) || height > double(domain_.z.back())) return {};
  const auto at = std::lower_bound(domain_.z.begin()+1,domain_.z.end(),height,[](float a,double b) { return double(a)<b; });
  const int hi = int(at-(domain_.z.begin()+1));
  if (at != domain_.z.end() && double(*at) == height) return {hi,hi,0};
  return {hi-1,hi,(height-double(domain_.z[hi]))/(double(domain_.z[hi+1])-double(domain_.z[hi]))};
}
MonitorLocation Monitor::location(std::size_t point,double height) const {
  const auto width = std::size_t(i_last_-i_first_);
  const int i = i_first_+int(point%width), j = j_first_+int(point/width);
  return {double(domain_.x[i])+(spec_.frame == MonitorFrame::World ? spec_.origin[0] : 0),
          double(domain_.y[j])+(spec_.frame == MonitorFrame::World ? spec_.origin[1] : 0),height};
}
MonitorSample Monitor::sample(const Support &support,std::size_t cell) const {
  if (support.lo < 0) return invalid();
  const auto value = [&](int k) {
    for (const auto &slab : slabs_) if (k >= slab.layers.first && k < slab.layers.last) {
      const auto c = std::size_t(k-slab.layers.first)*domain_.numHorizontalCellCentered()+cell;
      if (slab.cell_flags[c] == 0 || slab.cell_flags[c] == 2) return invalid();
      MonitorSample s{{double(slab.velocity[3*c]),double(slab.velocity[3*c+1]),double(slab.velocity[3*c+2])},true};
      if (!std::all_of(s.velocity.begin(),s.velocity.end(),[](double v) { return std::isfinite(v); })) return invalid();
      return s;
    }
    throw qes::RuntimeError("Missing compiled monitor slab");
  };
  auto lo = value(support.lo);
  if (!lo.valid || support.lo == support.hi) return lo;
  const auto hi = value(support.hi);
  if (!hi.valid) return invalid();
  for (int c = 0; c < 3; ++c) {
    const double delta = support.weight*(hi.velocity[c]-lo.velocity[c]);
    lo.velocity[c] += delta;
  }
  return lo;
}
MonitorSample Monitor::receptor_sample(const ReceptorSupport &s) const {
  if (!s.count) return invalid();
  MonitorSample result{{0,0,0},true};
  for (std::size_t n = 0; n < s.count; ++n) {
    const auto v = sample(s.vertical,s.cells[n]);
    if (!v.valid) return invalid();
    for (int c = 0; c < 3; ++c) {
      const double weighted = s.weights[n]*v.velocity[c];
      result.velocity[c] += weighted;
    }
  }
  return result;
}
const Monitor::Frame &Monitor::previous_frame(std::size_t back) const {
  return frames_[(next_frame_+frames_.size()-back)%frames_.size()];
}
MonitorWindow Monitor::window(std::size_t offset,std::size_t count,std::size_t span,
                              const Frame &now,const MonitorWindow *previous) {
  MonitorWindow out;
  if (frame_count_ < span) return out;
  const auto &before = previous_frame(span);
  out.available = true; out.from_iteration = before.iteration; out.to_iteration = now.iteration;
  vector_scratch_.clear(); speed_scratch_.clear();
  for (std::size_t n = offset; n < offset+count; ++n) {
    bool common = now.samples[n].valid, changed = now.samples[n].valid != before.samples[n].valid;
    for (std::size_t back = 1; back <= span; ++back) {
      const bool v = previous_frame(back).samples[n].valid;
      common = common && v; changed = changed || (v != before.samples[n].valid);
    }
    out.validity_changes += changed;
    if (common) {
      ++out.common_valid;
      vector_scratch_.push_back(distance(now.samples[n],before.samples[n]));
      speed_scratch_.push_back(std::abs(speed(now.samples[n])-speed(before.samples[n])));
    }
  }
  out.vector_change = norm(vector_scratch_); out.speed_change = norm(speed_scratch_);
  out.vector_over_uref = normalized(out.vector_change,spec_.reference_speed);
  out.speed_factor_change = normalized(out.speed_change,spec_.reference_speed);
  if (previous && previous->available && !out.validity_changes && !previous->validity_changes
      && out.common_valid == previous->common_valid
      && out.to_iteration-out.from_iteration == previous->to_iteration-previous->from_iteration) {
    out.ratios = {ratio(out.vector_change.p95,previous->vector_change.p95),ratio(out.vector_change.maximum,previous->vector_change.maximum),
                  ratio(out.speed_change.p95,previous->speed_change.p95),ratio(out.speed_change.maximum,previous->speed_change.maximum)};
  }
  return out;
}

const MonitorCheckpoint &Monitor::capture_impl(const void *state,std::uint64_t epoch,int iteration,double elapsed,
  const std::function<void(solver::LayerRange,solver::CenteredDestination)> &observe,
  const std::function<solver::MassDiagnostics(solver::MassRegion,solver::FluxOptions)> &diagnose,
  std::optional<solver::ResidualTrend> trend) {
  if (failed_ || state != state_ || epoch != epoch_ || !observe || !diagnose || iteration < 0)
    throw qes::InputError("Monitor belongs to a different or failed condition/source");
  const auto *previous = history_count_ ? &history_at(history_count_-1) : nullptr;
  if (!std::isfinite(elapsed) || elapsed < 0 || (previous && (iteration <= previous->iteration || elapsed < previous->elapsed_seconds)))
    throw qes::InputError("Monitor checkpoints require increasing completed sweeps and monotone elapsed time");
  for (auto &slab : slabs_) {
    observe(slab.layers,{slab.velocity,slab.cell_flags});
    const auto count = std::size_t(slab.layers.last-slab.layers.first)*domain_.numHorizontalCellCentered();
    if (slab.velocity.size() != count*3 || slab.cell_flags.size() != count)
      throw qes::InputError("Backend monitor slab has the wrong length");
  }
  auto &f = frames_[next_frame_]; f.iteration = iteration;
  auto &record = history_[next_history_];
  record.iteration = iteration; record.initial = iteration == 0; record.elapsed_seconds = elapsed;
  record.required_receptors_valid = true; record.residual_trend.reset();
  if (trend && trend->iteration == iteration)
    record.residual_trend = MonitorResidualTrend{trend->iteration,trend->maximum,trend->volume_weighted_rms,trend->fluid_cells};
  for (std::size_t h = 0; h < heights_.size(); ++h) {
    MonitorHeightRecord out; out.height_agl = spec_.heights[h]; out.points = plane_points_;
    for (std::size_t point = 0; point < plane_points_; ++point) {
      const auto cell = std::size_t(i_first_)+point%std::size_t(i_last_-i_first_)
        + (std::size_t(j_first_)+point/std::size_t(i_last_-i_first_))*(domain_.nx()-1);
      auto &s = f.samples[h*plane_points_+point]; s = sample(heights_[h],cell);
      if (!s.valid) continue;
      ++out.valid;
      const double v = speed(s);
      if (!out.peak.valid || v > out.peak.speed)
        out.peak = {true,point,location(point,out.height_agl),v,ratio(v,spec_.reference_speed)};
    }
    f.peaks[h] = out.peak;
    if (iteration > 0) {
      out.short_change = window(h*plane_points_,plane_points_,spec_.short_window,f,previous ? &previous->heights[h].short_change : nullptr);
      out.long_change = window(h*plane_points_,plane_points_,spec_.long_window,f,previous ? &previous->heights[h].long_change : nullptr);
      for (auto pair : {std::pair<MonitorWindow *,std::size_t>{&out.short_change,spec_.short_window},{&out.long_change,spec_.long_window}}) {
        if (!pair.first->available) continue;
        const auto &old = previous_frame(pair.second);
        const MonitorPeak peaks[] = {out.peak,old.peaks[h]};
        for (int n = 0; n < 2; ++n) if (peaks[n].valid) {
          const auto p = peaks[n].point, index = h*plane_points_+p;
          auto &tracked = pair.first->hotspots[n];
          tracked.present = true; tracked.point = p; tracked.location = location(p,out.height_agl);
          tracked.before = old.samples[index]; tracked.current = f.samples[index];
          if (tracked.before.valid && tracked.current.valid) {
            tracked.vector_change = distance(tracked.current,tracked.before);
            tracked.speed_change = std::abs(speed(tracked.current)-speed(tracked.before));
          }
        }
      }
    }
    record.heights[h] = out;
  }
  for (std::size_t n = 0; n < receptors_.size(); ++n) {
    const auto index = heights_.size()*plane_points_+n;
    auto &s = f.samples[index]; s = receptor_sample(receptors_[n]);
    MonitorReceptorRecord out; out.receptor = n; out.required = spec_.receptors[n].required;
    out.location = spec_.receptors[n].location; out.sample = s;
    if (s.valid) { out.speed = speed(s); out.speed_factor = ratio(*out.speed,spec_.reference_speed); }
    else if (out.required) record.required_receptors_valid = false;
    if (iteration > 0) {
      out.short_change = window(index,1,spec_.short_window,f,previous ? &previous->receptors[n].short_change : nullptr);
      out.long_change = window(index,1,spec_.long_window,f,previous ? &previous->receptors[n].long_change : nullptr);
    }
    record.receptors[n] = out;
  }
  const solver::FluxOptions options{true,spec_.reference_speed,spec_.low_flow_fraction};
  for (std::size_t n = 0; n < regions_.size(); ++n) {
    const auto mass = diagnose(regions_[n].bounds,options);
    record.mass[n] = {n,{mass.interior_max,mass.interior_rms,mass.top_band_max,mass.cells,mass.top_band_cells},
                      flux_record(mass.interior_flux),flux_record(mass.top_band_flux)};
  }
  latest_frame_ = next_frame_;
  if (iteration > 0) { next_frame_ = (next_frame_+1)%frames_.size(); frame_count_ = std::min(frame_count_+1,frames_.size()); }
  next_history_ = (next_history_+1)%history_.size(); history_count_ = std::min(history_count_+1,history_.size());
  return record;
}
const MonitorCheckpoint &Monitor::history_at(std::size_t n) const {
  if (failed_ || n >= history_count_) throw qes::InputError("Monitor history index is unavailable");
  return history_[(next_history_+history_.size()-history_count_+n)%history_.size()];
}
const std::vector<MonitorSample> &Monitor::samples() const {
  if (failed_ || !history_count_) throw qes::InputError("Capture a valid checkpoint before reading monitor samples");
  return frames_[latest_frame_].samples;
}
std::size_t Monitor::allocated_bytes() const {
  std::size_t bytes = sizeof(*this);
  const auto count = [&](const auto &v) { return mul(v.capacity(),sizeof(typename std::decay_t<decltype(v)>::value_type)); };
  for (const auto *v : {&domain_.x,&domain_.y,&domain_.z,&domain_.z_face,&domain_.dz_array}) bytes = add(bytes,count(*v));
  bytes = add(bytes,count(spec_.heights)); bytes = add(bytes,count(spec_.receptors)); bytes = add(bytes,count(spec_.mass_regions));
  bytes = add(bytes,spec_.crs.capacity());
  for (const auto &r : spec_.receptors) bytes = add(bytes,r.id.capacity());
  for (const auto &r : spec_.mass_regions) bytes = add(bytes,r.name.capacity());
  bytes = add(bytes,count(heights_)); bytes = add(bytes,count(receptors_)); bytes = add(bytes,count(regions_));
  for (const auto &r : regions_) bytes = add(bytes,r.name.capacity());
  bytes = add(bytes,count(slabs_));
  for (const auto &s : slabs_) { bytes = add(bytes,count(s.velocity)); bytes = add(bytes,count(s.cell_flags)); }
  bytes = add(bytes,count(frames_));
  for (const auto &f : frames_) { bytes = add(bytes,count(f.samples)); bytes = add(bytes,count(f.peaks)); }
  bytes = add(bytes,count(history_));
  for (const auto &r : history_) { bytes = add(bytes,count(r.heights)); bytes = add(bytes,count(r.receptors)); bytes = add(bytes,count(r.mass)); }
  bytes = add(bytes,count(vector_scratch_)); bytes = add(bytes,count(speed_scratch_));
  return bytes;
}
}
