#pragma once

#include <mutex>
#include <memory>
#include <string>
#include <vector>

namespace dtcc_qes {
struct LogMessage {
  enum class Level { debug, warning };
  Level level;
  std::string text;
};
using Messages = std::vector<LogMessage>;

// QES has process-global diagnostic state. Every native operation, including
// destruction, takes this lock; no Python interaction occurs while it is held.
std::mutex &native_mutex();

// Construct only while holding native_mutex(). No Python callbacks are stored.
class BufferedLogSink {
  struct Impl;
  std::unique_ptr<Impl> impl_;
public:
  explicit BufferedLogSink(Messages &);
  ~BufferedLogSink();
  BufferedLogSink(const BufferedLogSink &) = delete;
  BufferedLogSink &operator=(const BufferedLogSink &) = delete;
};
}
