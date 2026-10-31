// S0 study instrumentation, injected ONLY into an isolated source snapshot.
// No solver arithmetic or production targets include this header.
#pragma once
#include <chrono>
#include <map>
#include <string>
#include <vector>
#include <sys/resource.h>
#ifdef _OPENMP
#include <omp.h>
#endif

namespace solver_profile {
using Clock = std::chrono::steady_clock;
inline std::map<std::string, double> seconds, passes;
inline std::map<std::string, std::size_t> bytes, capacity_bytes, rss;
inline Clock::time_point last = Clock::now(), pass_last = last;
inline std::string phase = "idle", pass = "idle";
inline int actual_threads = 1;
inline void mark(const char *name) {
  const auto now = Clock::now();
  if (phase != "idle") seconds[phase] += std::chrono::duration<double>(now-last).count();
  phase = name; last = now;
}
// Called only by the OpenMP master, after existing worksharing barriers.
// These pass estimates include scheduling/barrier time and can overlap phases.
inline void sweep_mark(const char *name) {
  const auto now = Clock::now();
  if (pass != "idle") passes[pass] += std::chrono::duration<double>(now-pass_last).count();
  pass = name; pass_last = now;
#ifdef _OPENMP
  if (omp_in_parallel()) actual_threads = omp_get_num_threads();
#endif
}
template<class T> void array(const char *name, const std::vector<T> &a) {
  bytes[name] = a.size()*sizeof(T); capacity_bytes[name] = a.capacity()*sizeof(T);
}
inline void resident(const char *name) {
  rusage usage{}; getrusage(RUSAGE_SELF, &usage);
#ifdef __APPLE__
  rss[name] = usage.ru_maxrss;
#else
  rss[name] = std::size_t(usage.ru_maxrss)*1024;
#endif
}
inline void reset() {
  seconds.clear(); passes.clear(); bytes.clear(); capacity_bytes.clear(); rss.clear();
  phase = pass = "idle"; actual_threads = 1; last = pass_last = Clock::now();
}
}
