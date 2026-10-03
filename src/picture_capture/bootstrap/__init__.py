"""Explicit Picture Capture composition-root entrypoints.

GUI startup and multiprocessing detection workers both enter through this
package.  Their concrete installers live in dedicated ``gui`` and ``worker``
modules so process-specific composition is explicit rather than determined by
which legacy entry module happened to be imported first.
"""

from .application import build_application, main
from .worker import WorkerServices, build_worker_services

__all__ = [
    "WorkerServices",
    "build_application",
    "build_worker_services",
    "main",
]
