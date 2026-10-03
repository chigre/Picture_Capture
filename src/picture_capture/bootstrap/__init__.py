"""Explicit Picture Capture composition-root entrypoints.

GUI startup and multiprocessing detection workers both enter through this
package and share one explicit non-GUI core profile. Process-specific installers
live in dedicated ``gui`` and ``worker`` modules rather than depending on which
legacy entry module happened to be imported first.
"""

from .application import build_application, main
from .core import CoreServices, build_core_services
from .worker import WorkerServices, build_worker_services

__all__ = [
    "CoreServices",
    "WorkerServices",
    "build_application",
    "build_core_services",
    "build_worker_services",
    "main",
]
