from pathlib import Path
import multiprocessing
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from picture_capture.app import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
