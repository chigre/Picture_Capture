from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "src"))

from picture_capture.bootstrap.core import build_core_services  # noqa: E402


# The compatibility runner validates the composed application/service contract,
# not the intentionally inert bare package import.
build_core_services()

suite = unittest.defaultTestLoader.discover(str(root / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
