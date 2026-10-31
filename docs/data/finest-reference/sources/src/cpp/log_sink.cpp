#include "log_sink.h"
#include "util/QESLog.h"

namespace dtcc_qes {
std::mutex &native_mutex()
{
  static std::mutex mutex;
  return mutex;
}

struct BufferedLogSink::Impl {
  qes::log::ScopedHandler handler;
  explicit Impl(Messages &messages) : handler([&](qes::log::Level level, const std::string &text) {
    // Errors propagate as exceptions. Never log them a second time.
    if (level == qes::log::Level::error || text.empty()) return;
    messages.push_back({level == qes::log::Level::warning ? LogMessage::Level::warning
                                                       : LogMessage::Level::debug, text});
  }) {}
};

BufferedLogSink::BufferedLogSink(Messages &messages) : impl_(std::make_unique<Impl>(messages)) {}
BufferedLogSink::~BufferedLogSink() = default;
}
