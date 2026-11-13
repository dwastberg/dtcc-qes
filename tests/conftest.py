import logging
from pathlib import Path

import pytest

# Qualification evidence ships in git, not in the sdist (pyproject sdist.exclude).
EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "data"


def pytest_configure(config):
    config.addinivalue_line("markers", "evidence: reads the qualification evidence in docs/data")


def pytest_collection_modifyitems(config, items):
    """Skip the tests of archived evidence when docs/data is absent, as in an unpacked sdist.

    A test needs it when its module names docs/data or is marked ``evidence``
    (modules that read it through a tool).
    """
    if EVIDENCE.is_dir():
        return
    skip = pytest.mark.skip(reason="needs the qualification evidence in docs/data (git checkout only)")
    reads = {}
    for item in items:
        module = Path(str(item.fspath))
        if module not in reads:
            reads[module] = "docs/data" in module.read_text(errors="ignore")
        if reads[module] or item.get_closest_marker("evidence"):
            item.add_marker(skip)


@pytest.fixture
def dtcc_logger():
    from dtcc_core.common import get_python_logger

    logger = get_python_logger("dtcc-qes")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.setLevel(logging.DEBUG)
    logger.propagate = True
    yield logger
    logger.handlers, logger.level, logger.propagate = handlers, level, propagate
