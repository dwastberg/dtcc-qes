#include "dtcc/api/reference_sampling.h"
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace dtcc_qes;
using Vector = std::array<double,3>;
static void require(bool value) { if (!value) throw std::runtime_error("Reference support contract failed"); }
template<class F> static void rejects(F operation, const char *message) {
  try { operation(); } catch (const std::invalid_argument &e) {
    require(std::string(e.what()).find(message) != std::string::npos); return;
  }
  throw std::runtime_error("Unsupported reference accepted");
}
int main() {
  try {
    const std::vector<float> centres{.125f,.375f,.875f};
    // Four columns represent mixed roofs: below, between, above both brackets,
    // and terrain. The two sources must both be fluid to enter the population.
    const auto sample=[](int k,std::size_t c) {
      return std::make_pair(c==0 || (c==1 && k>0), Vector{1+2.*k,2,0});
    };
    const auto mixed=sample_reference(centres,.25,4,sample);
    require(mixed.lower==0 && mixed.upper==1 && mixed.upper_weight==.5);
    require(mixed.valid_columns==1 && mixed.excluded_columns==3);
    require(std::abs(mixed.mean_speed-std::sqrt(8.))<1e-14);
    const auto exact=sample_reference(centres,.375,4,sample);
    require(exact.lower==exact.upper && exact.upper_weight==0 && exact.valid_columns==2);
    // Reversing vectors cancel before magnitude; interpolating speed is wrong.
    const auto turning=sample_reference(centres,.25,1,[](int k,std::size_t) {
      return std::make_pair(true,Vector{k? -1.:1.,0,0});
    });
    require(turning.mean_speed==0);
    const auto constant=[](int,std::size_t) { return std::make_pair(true,Vector{1.312345,-.2,.3}); };
    const auto many=sample_reference(centres,.25,45056,constant);
    const double oracle=std::sqrt(1.312345*1.312345+.04+.09);
    require(std::abs(many.mean_speed-oracle)<2e-12);
    rejects([&]{sample_reference(centres,.01,4,sample);},"physical cell centres");
    rejects([&]{sample_reference(centres,1.,4,sample);},"physical cell centres");
    rejects([&]{sample_reference(centres,.25,0,sample);},"no complete fluid columns");
    rejects([&]{sample_reference(centres,.25,4,[](int,std::size_t) {
      return std::make_pair(false,Vector{});
    });},"no complete fluid columns");
    rejects([&]{sample_reference(centres,.25,4,[](int,std::size_t) {
      return std::make_pair(true,Vector{std::numeric_limits<double>::quiet_NaN(),0,0});
    });},"nonfinite fluid velocity");
    // Nonfinite values in excluded solid support do not enter the reduction.
    const auto solid=sample_reference(centres,.25,2,[](int,std::size_t c) {
      return std::make_pair(c==0,Vector{c?std::numeric_limits<double>::quiet_NaN():1.,0,0});
    });
    require(solid.mean_speed==1 && solid.valid_columns==1 && solid.excluded_columns==1);
  } catch (const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
