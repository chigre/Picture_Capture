from __future__ import annotations

"""Training archive publication with cancellation and atomic final replacement.

Own the v2/v3 shared ZIP publisher. The historical training_export public
module re-exports the very same exception type and callable. Restore their
original module path for third-party pickle compatibility without an import
cycle: their implementations physically live in this import-light package.
"""

from pathlib import Path
from typing import Callable
import uuid
import zipfile


class TrainingExportCancelled(RuntimeError):
    """Raised when a training-package build is cooperatively stopped."""


def make_training_zip(
    staging_root: Path,
    zip_path: Path,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> Path:
    """Create the training ZIP off to the side and publish it only when complete."""
    staging_root = Path(staging_root)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temp_zip = zip_path.with_name(f".{zip_path.name}.{uuid.uuid4().hex}.tmp")

    def check_stop() -> None:
        if should_stop is not None and should_stop():
            raise TrainingExportCancelled("训练标记包导出已停止")

    try:
        temp_zip.unlink(missing_ok=True)
        paths = sorted(staging_root.rglob("*"), key=lambda p: p.as_posix().casefold())
        check_stop()
        with zipfile.ZipFile(
            temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
        ) as zf:
            for path in paths:
                check_stop()
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(staging_root).as_posix())
        check_stop()
        temp_zip.replace(zip_path)
    except Exception:
        temp_zip.unlink(missing_ok=True)
        raise
    return zip_path

# Keep pickled exception / function references valid at their historical public
# names. training_export re-exports these exact objects without a wrapper.
TrainingExportCancelled.__module__ = "picture_capture.training_export"
make_training_zip.__module__ = "picture_capture.training_export"
