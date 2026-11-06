#pragma once
// Scoped ownership accounting, not an allocator profiler or an RSS estimate.
#include <algorithm>
#include <array>
#include <cstddef>
#include <mutex>

namespace dtcc_qes {
enum class ResourceKind : std::size_t { WindGrid, Operator, Workspace };
struct ResourceCounter {
  std::size_t objects = 0, bytes = 0, peak_objects = 0, peak_bytes = 0;
};
struct ResourceUsage {
  std::array<ResourceCounter,3> categories{};
};
namespace resource_detail {
struct Registry { std::mutex mutex; ResourceUsage usage; };
inline Registry &registry() { static Registry value; return value; }
}
inline ResourceUsage resource_usage() {
  auto &r=resource_detail::registry();
  const std::lock_guard<std::mutex> lock(r.mutex);
  return r.usage;
}
// Starts a measurement interval without resetting any live ownership counts.
inline void reset_resource_peaks() {
  auto &r=resource_detail::registry();
  const std::lock_guard<std::mutex> lock(r.mutex);
  for (auto &c : r.usage.categories) { c.peak_objects=c.objects; c.peak_bytes=c.bytes; }
}
class ResourceAccount {
public:
  explicit ResourceAccount(ResourceKind kind) : kind_(std::size_t(kind)) {
    auto &r=resource_detail::registry();
    const std::lock_guard<std::mutex> lock(r.mutex);
    auto &c=r.usage.categories[kind_];
    c.peak_objects=std::max(c.peak_objects,++c.objects);
  }
  ~ResourceAccount() {
    auto &r=resource_detail::registry();
    const std::lock_guard<std::mutex> lock(r.mutex);
    auto &c=r.usage.categories[kind_]; --c.objects; c.bytes-=bytes_;
  }
  ResourceAccount(const ResourceAccount &)=delete;
  ResourceAccount &operator=(const ResourceAccount &)=delete;
  void set_bytes(std::size_t bytes) {
    auto &r=resource_detail::registry();
    const std::lock_guard<std::mutex> lock(r.mutex);
    auto &c=r.usage.categories[kind_];
    c.bytes=c.bytes-bytes_+bytes; bytes_=bytes;
    c.peak_bytes=std::max(c.peak_bytes,c.bytes);
  }
private:
  std::size_t kind_, bytes_=0;
};
}
