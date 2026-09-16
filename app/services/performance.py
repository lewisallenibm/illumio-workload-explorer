"""Opt-in development timing for active UI/repository paths."""

from contextlib import contextmanager
import logging
import os
from time import perf_counter

_LOG = logging.getLogger("illumio.performance")


@contextmanager
def timed(operation):
    """Log elapsed time only when ILLUMIO_PERF_TIMING=true."""
    if os.getenv("ILLUMIO_PERF_TIMING", "false").casefold() != "true":
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        _LOG.info("%s %.1fms", operation, (perf_counter() - started) * 1000)
