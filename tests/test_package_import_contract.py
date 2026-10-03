from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_bare_package_import_loads_no_picture_capture_submodules() -> None:
    code = """
import sys
import picture_capture
assert picture_capture.__version__ == '2.14.2'
loaded = sorted(name for name in sys.modules if name.startswith('picture_capture.'))
assert loaded == [], loaded
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_package_init_contains_metadata_only() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert '__version__ = "2.14.2"' in source
    assert "install_" not in source
    assert "from ." not in source
    assert "import processing" not in source
    assert "import formats" not in source
