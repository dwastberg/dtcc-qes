"""One-answer deadlines without process-memory polling or a memory cap."""
from pathlib import Path
import os
import subprocess
from time import perf_counter


def run_worker(command, log_path, *, deadline):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = log_path.with_suffix(".stdout.log")
    started = perf_counter()
    status = "failed"
    returncode = None
    with stdout_path.open("w") as output, log_path.open("w") as errors:
        try:
            result = subprocess.run(command, stdout=output, stderr=errors,
                env=dict(os.environ, QES_EXPERIMENT_PROGRESS="0", QES_NATIVE_PROGRESS="1",
                         QES_TRACEBACK_PATH=str(log_path.with_suffix(".traceback.log").resolve())),
                timeout=deadline, check=False)
            returncode = result.returncode
            status = "completed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            # subprocess.run kills and reaps its child before raising.
            status = "timeout"
    return dict(status=status, complete=status == "completed", returncode=returncode,
                wall_seconds=perf_counter()-started, deadline_seconds=deadline,
                rss_limit_bytes=None, memory_policy="record worker peak RSS; no memory rejection",
                stdout_path=str(stdout_path), stderr_path=str(log_path))
