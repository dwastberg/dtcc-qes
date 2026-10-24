import logging

import pytest


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
