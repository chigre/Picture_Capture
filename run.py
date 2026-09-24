"""Picture Capture launcher."""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC = _PROJECT_ROOT / "src"


def main() -> int:
    sys.path.insert(0, str(_SRC))
    from picture_capture.app import main as app_main

    return app_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
