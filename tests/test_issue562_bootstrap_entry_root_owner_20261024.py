"""Issue #562: the CLI and launcher have one physical bootstrap owner."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from picture_capture.bootstrap import cli, launcher


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/picture_capture"


def test_no_root_launcher_or_cli_and_same_console_command():
    assert not (PACKAGE / "launcher.py").exists()
    assert not (PACKAGE / "cli.py").exists()
    assert importlib.util.find_spec("picture_capture.launcher") is None
    assert importlib.util.find_spec("picture_capture.cli") is None
    assert Path(cli.__file__).resolve() == PACKAGE / "bootstrap/cli.py"
    assert Path(launcher.__file__).resolve() == PACKAGE / "bootstrap/launcher.py"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'picture-capture-cli = "picture_capture.bootstrap.cli:main"' in pyproject
    assert 'picture-capture = "picture_capture.bootstrap.application:main"' in pyproject
    assert len(tuple(PACKAGE.glob("*.py"))) == 10


def test_cli_parser_keeps_inspect_draw_ocr_and_crop_actions():
    parser = cli.build_parser()
    for command in ("inspect", "autodraw", "ocr", "split-lines", "split-whole"):
        opts = parser.parse_args(["/tmp/example-project", command])
        assert opts.command == command
    assert parser.parse_args(["/tmp/example-project", "ocr", "--page", "008"]).page == "008"


def test_launcher_forwards_to_shared_bootstrap_at_call_time(monkeypatch):
    from picture_capture.bootstrap import application
    marker = object()
    monkeypatch.setattr(application, "build_application", lambda: marker)
    monkeypatch.setattr(application, "main", lambda: 7)
    assert launcher.prepare_app_module() is marker
    assert launcher.main() == 7
