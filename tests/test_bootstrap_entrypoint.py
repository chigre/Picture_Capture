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
        "import picture_capture.bootstrap; "
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


def test_gui_composition_is_owned_by_bootstrap_and_launcher_is_only_a_facade() -> None:
    application = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "application.py"
    ).read_text(encoding="utf-8")
    gui = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    launcher = (
        ROOT / "src" / "picture_capture" / "launcher.py"
    ).read_text(encoding="utf-8")

    assert "from .gui import prepare_gui_application" in application
    assert "return prepare_gui_application()" in application
    assert "def prepare_gui_application()" in gui
    assert "install_ui_terminology()" not in gui
    assert "install_spawn_detection_runtime" not in gui
    assert "from .bootstrap.application import build_application" in launcher
    assert "from .bootstrap.application import main as bootstrap_main" in launcher
    assert "install_ui_terminology()" not in launcher
    assert "install_spawn_detection_runtime" not in launcher


def test_gui_and_worker_profiles_share_one_core_composition_root() -> None:
    bootstrap_init = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "__init__.py"
    ).read_text(encoding="utf-8")
    gui = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    worker = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "worker.py"
    ).read_text(encoding="utf-8")

    assert "from .core import CoreServices, build_core_services" in bootstrap_init
    assert "from .core import build_core_services" in gui
    assert "core_services = build_core_services()" in gui
    assert "from .core import build_core_services" in worker
    assert "core_services = build_core_services()" in worker


def test_spawn_detection_routes_through_worker_composition_root() -> None:
    bootstrap_init = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "__init__.py"
    ).read_text(encoding="utf-8")
    worker = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "worker.py"
    ).read_text(encoding="utf-8")
    processing = (
        ROOT / "src" / "picture_capture" / "processing.py"
    ).read_text(encoding="utf-8")

    assert "from .worker import WorkerServices, build_worker_services" in bootstrap_init
    assert "def build_worker_services()" in worker
    assert "from .bootstrap.worker import build_worker_services" in processing
    assert "services = build_worker_services()" in processing
    assert "install_spawn_detection_runtime" not in processing
