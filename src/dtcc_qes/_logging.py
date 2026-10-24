"""Forward buffered diagnostics through DTCC's ordinary Python logger.

Called only after native work has released its mutex and reacquired the GIL.
The callback API from ``init_logging`` is unsuitable: its error callback raises.
"""

from dtcc_core.common import get_python_logger


def _forward_native_messages(messages):
    logger = get_python_logger("dtcc-qes")
    for level, message in messages:
        logger.log(level, message.rstrip())


def _log_solve(result):
    nz, ny, nx, _ = result["velocity"].shape
    diagnostics = result["diagnostics"]
    get_python_logger("dtcc-qes").info(
        "Wind grid %d x %d x %d, %d buildings: %d iterations, converged=%s",
        nx, ny, nz, result["building_count"], diagnostics["iterations"], diagnostics["converged"],
    )
