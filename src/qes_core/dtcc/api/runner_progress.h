#pragma once
#include <cstdint>

namespace dtcc_qes {
struct RunnerProgress {
  std::uint64_t operation_id = 0, revision = 0;
  // Static phase names keep failure reporting independent of heap allocation.
  const char *operation = "idle", *phase = "idle", *last_completed_stage = "";
  int completed_sweeps = 0, last_checkpoint = 0;
  double started_at = 0, phase_started_at = 0, observed_at = 0;
  bool finished = true;
};
}
