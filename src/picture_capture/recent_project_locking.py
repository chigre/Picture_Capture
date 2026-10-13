from __future__ import annotations

"""OS-level advisory mutex guarding the entire recent-project read/modify/write.

A persistent one-byte lock file survives crashes safely: the OS releases locks
when a process exits. No stale PID or timeout-based lock stealing is needed.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import time
from typing import Iterator


@contextmanager
def recent_registry_lock(path: Path, *, timeout: float = 15.0) -> Iterator[None]:
    lock = Path(path).with_name(Path(path).name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with lock.open("a+b") as handle:
        # Never read/write the byte while another Windows process owns its
        # lock: reading a locked region raises PermissionError on Windows.
        # Windows and POSIX byte-range locking allow a region beyond EOF.
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            def acquire() -> None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            def release() -> None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire() -> None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release() -> None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        while True:
            try:
                acquire()
                break
            except (BlockingIOError, PermissionError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"最近项目记录被其他进程占用：{lock}")
                time.sleep(0.025)
        try:
            yield
        finally:
            release()
