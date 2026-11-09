#include "turbulence.h"
#include "api/turbulence_reference.h"
#include "model_inputs.h"
#include "stress_validity.h"
#include "winds/TURBGeneralData.h"
#include "winds/WINDSGeneralData.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace dtcc_qes {
MonitorReceptorRecord::TurbulenceSample turbulence_sample(const TURBGeneralData &turb,
    const WINDSGeneralData &wind, MonitorLocation point)
{
  using Sample = MonitorReceptorRecord::TurbulenceSample;
  Sample out;
  const auto invalid = [] { Sample sample;sample.stress.fill(std::numeric_limits<double>::quiet_NaN());
    sample.gradient.fill(std::numeric_limits<double>::quiet_NaN());return sample; };
  struct Support {int lo=0,hi=0;double weight=0;bool valid=false;};
  const auto bracket=[](const auto &axis,double value,int begin) {
    Support s;
    if(!std::isfinite(value) || value<axis[begin] || value>axis.back())return s;
    auto at=std::lower_bound(axis.begin()+begin,axis.end(),value,[](float a,double b){return double(a)<b;});
    s.hi=int(at-axis.begin());s.lo=s.hi;s.valid=true;
    if(double(*at)!=value){s.lo=s.hi-1;s.weight=(value-axis[s.lo])/(double(axis[s.hi])-axis[s.lo]);}
    return s;
  };
  const auto &d=wind.domain;
  const auto x=bracket(d.x,point.x,0),y=bracket(d.y,point.y,0),z=bracket(d.z,point.height_agl,1);
  if(!x.valid || !y.valid || !z.valid)return invalid();
  const std::vector<float> *gradients[]={&turb.Gxx,&turb.Gxy,&turb.Gxz,&turb.Gyx,&turb.Gyy,&turb.Gyz,
                                       &turb.Gzx,&turb.Gzy,&turb.Gzz};
  const float bound=turb.getUpperBound()*turb.getFrictionVelocity()*turb.getFrictionVelocity();
  out.computed=out.contributors_valid=true;
  for(int kk=0;kk<(z.lo==z.hi?1:2);++kk)for(int jj=0;jj<(y.lo==y.hi?1:2);++jj)
    for(int ii=0;ii<(x.lo==x.hi?1:2);++ii) {
      const double weight=(ii?x.weight:(x.lo==x.hi?1:1-x.weight))
        *(jj?y.weight:(y.lo==y.hi?1:1-y.weight))*(kk?z.weight:(z.lo==z.hi?1:1-z.weight));
      if(!(weight>0))continue;
      const auto c=d.cell(ii?x.hi:x.lo,jj?y.hi:y.lo,kk?z.hi:z.lo);
      // Same computed range as TURBGeneralData (exclude the physical shell).
      const int i=ii?x.hi:x.lo,j=jj?y.hi:y.lo,k=kk?z.hi:z.lo;
      if(i<1 || i>=d.nx()-2 || j<1 || j>=d.ny()-2 || k<1 || k>=d.nz()-2
          || wind.icellflag[c]==0 || wind.icellflag[c]==2)return invalid();
      StressTensor stress{turb.txx[c],turb.txy[c],turb.txz[c],turb.tyy[c],turb.tyz[c],turb.tzz[c]};
      out.contributors_valid &= stress_validity(stress).valid;
      const float sxx=turb.Gxx[c],syy=turb.Gyy[c],szz=turb.Gzz[c];
      const float sxy=.5f*(turb.Gxy[c]+turb.Gyx[c]),sxz=.5f*(turb.Gxz[c]+turb.Gzx[c]),syz=.5f*(turb.Gyz[c]+turb.Gzy[c]);
      const float ss=sxx*sxx+syy*syy+szz*szz+2.f*(sxy*sxy+sxz*sxz+syz*syz);
      const float lm=turb.Lm[c],nu=lm*lm*std::sqrt(2.f*ss);
      const float uncapped=std::pow(nu/(.55f*lm),2.f);
      out.mixing_length+=weight*lm;out.tke+=weight*turb.tke[c];out.uncapped_tke+=weight*uncapped;
      out.capped |= bound>0 && turb.tke[c]>=bound;
      for(int n=0;n<6;++n){out.stress[n]+=weight*stress[n];out.capped |= bound>0 && std::abs(stress[n])>=bound;}
      for(int n=0;n<9;++n)out.gradient[n]+=weight*(*gradients[n])[c];
    }
  StressTensor stress;
  for(int n=0;n<6;++n)stress[n]=float(out.stress[n]);
  out.valid=out.contributors_valid && stress_validity(stress).valid;
  return out;
}

void configure_turbulence(TurbulenceConfig &params, const TurbulenceSettings &settings)
{
  if (settings.mixing_length_method != 0 && settings.mixing_length_method != 1)
    throw std::invalid_argument("Unsupported turbulence mixing-length method: "
      + std::to_string(settings.mixing_length_method) + "; supported methods are 0 (height) and 1 (wall distance)");
  // Method 1 passed Task 1B's bounds, height-invariant and geometry gates.
  // Keep every other model choice at the audited QES defaults.
  params.methodLocalMixing = settings.mixing_length_method;
  params.sigConst.reset();
  params.flagNonLocalMixing = false;
  params.buildingWallFlag = params.terrainWallFlag = 2;
  params.turbUpperBound = 20;
  params.backgroundMixing = 0;
}

void check_turbulence_margin(const ModelInputs &inputs, const WINDSGeneralData &wind,
                             const GridConfig &grid)
{
  const auto &faces = wind.domain.z_face;
  // Match TURBGeneralData's float32 mean in QES's sorted building order.
  // Check before constructing turbulence: its own reference-plane guards
  // otherwise throw before we can explain how to obtain a sufficient grid.
  std::vector<float> heights;
  for (const auto *building : wind.allBuildingsV) heights.push_back(building->H);
  const float reference = turbulence_reference(std::move(heights), inputs.turbulence.site_z0).reference_height;
  const std::vector<float> physical(faces.begin()+1,faces.end());
  const auto index = std::lower_bound(faces.begin(), faces.end(), reference) - faces.begin();
  if (reference < wind.domain.z[1])
    throw std::invalid_argument("Turbulence reference height zRef is below the first physical cell centre; refine the first layer");
  if (turbulence_margin(physical,reference)) return;

  std::ostringstream message;
  message << std::setprecision(std::numeric_limits<float>::max_digits10);
  message << "Turbulence domain top " << faces.back() << " m is insufficient for zRef "
          << reference << " m and the 15 m rotation reference; layer margin requires two physical layers "
          << "above the sampled layer (reference index " << index << ", maximum " << grid.nz - 2 << "). ";
  // Report an actual sufficient top for an unchanged prefix with a constant
  // tail, using QES float32 accumulation. Never suggest zRef+3*min(dz) as a
  // sufficient top for an arbitrary nonuniform grid. This check never grows it.
  const float thickness = static_cast<float>(grid.dz_layers.empty() ? grid.cell_size : grid.dz_layers.back());
  const auto extension = turbulence_extension(physical,reference,thickness,grid.nx,grid.ny,grid.max_cells);
  const auto &extended=extension.faces;
  const auto &limit=extension.limit;
  const int layers=grid.nz+extension.added_layers;
  if (limit.empty())
    message << "Appending " << layers-grid.nz << " layers of " << thickness
            << " m while preserving the existing layers gives a sufficient top of " << extended.back() << " m.";
  else
    message << "A constant-thickness tail of " << thickness << " m cannot satisfy the margin within the " << limit << ".";
  throw std::invalid_argument(message.str());
}

TurbulenceData turbulence_fields(const TURBGeneralData &turb, const GridConfig &grid)
{
  if (grid.nx != turb.domain.nx()-1 || grid.ny != turb.domain.ny()-1 || grid.nz != turb.domain.nz()-2)
    throw std::invalid_argument("Turbulence extraction grid does not match the native domain");
  const auto count = std::size_t(grid.nx) * grid.ny * grid.nz;
  const auto plane = std::size_t(grid.nx) * grid.ny;
  const float nan = std::numeric_limits<float>::quiet_NaN();
  TurbulenceData result;
  result.stress.assign(6*count, nan);
  result.tke.assign(count, nan);
  result.co_eps.assign(count, nan);
  result.mixing_length.assign(count, nan);
  result.state.assign(count, 0);
  result.stress_valid.assign(count, 0);
  result.friction_velocity = turb.getFrictionVelocity();
  result.reference_speed = turb.getReferenceSpeed();
  result.reference_height = turb.getReferenceHeight();
  result.reference_sampling = turb.getReferenceSampling();
  --result.reference_sampling.lower;
  --result.reference_sampling.upper; // Export physical zero-based cell indices.
  result.roughness_length = turb.getRoughnessLength();
  result.displacement_height = turb.getDisplacementHeight();
  result.upper_bound = turb.getUpperBound();
  result.rotation_fallback_columns = turb.getRotationFallbackColumns();
  // Match QES's float32 operation order. Zero bound in calm wind is not a cap.
  const float bound = turb.getUpperBound() * turb.getFrictionVelocity() * turb.getFrictionVelocity();
  for (int source : turb.icellfluid) {
    // The wind mapping removes only the ground ghost layer: (k-1,j,i).
    const auto cell = std::size_t(source) - plane;
    const StressTensor stress{turb.txx[source], turb.txy[source], turb.txz[source],
                              turb.tyy[source], turb.tyz[source], turb.tzz[source]};
    std::copy(stress.begin(), stress.end(), result.stress.begin()+6*cell);
    result.tke[cell] = turb.tke[source];
    result.co_eps[cell] = turb.CoEps[source];
    result.mixing_length[cell] = turb.Lm[source];
    bool capped = false;
    if (bound > 0) {
      capped = turb.tke[source] >= bound;
      for (float component : stress) capped = capped || std::abs(component) >= bound;
    }
    result.state[cell] = capped ? 2 : 1;
    result.stress_valid[cell] = stress_validity(stress).valid;
    ++result.computed_cells;
    if (capped) ++result.capped_cells;
    if (!result.stress_valid[cell]) ++result.invalid_stress_cells;
  }
  return result;
}
}
