from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_all_supported_gui_entrypoints_route_through_bootstrap() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_main = (
        ROOT / "src" / "picture_capture" / "__main__.py"
    ).read_text(encoding="utf-8")
    source_runner = (ROOT / "run.py").read_text(encoding="utf-8")
    gui_smoke = (ROOT / "scripts" / "gui_smoke.py").read_text(encoding="utf-8")

    assert (
        'picture-capture = "picture_capture.bootstrap.application:main"'
        in pyproject
    )
    assert "from .bootstrap.application import main" in package_main
    assert (
        "from picture_capture.bootstrap.application import main as app_main"
        in source_runner
    )
    assert (
        "from picture_capture.bootstrap.application import build_application"
        in gui_smoke
    )


def test_importing_bootstrap_does_not_import_gui_app_module() -> None:
    code = (
        "import sys; "
        "import picture_capture.bootstrap.application; "
        "assert 'picture_capture.app' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
