"""Project Center Open Folder action regression tests."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture import project_folder_launcher as launcher


def test_open_folder_windows(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.os, "startfile", lambda path: calls.append(path), raising=False)
    launcher.open_project_folder(tmp_path)
    assert calls == [str(tmp_path)]


@pytest.mark.parametrize("platform,program", [("darwin", "open"), ("linux", "xdg-open")])
def test_open_folder_unix(monkeypatch, tmp_path, platform, program):
    calls = []
    monkeypatch.setattr(launcher.sys, "platform", platform)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda argv: calls.append(argv))
    launcher.open_project_folder(tmp_path)
    assert calls == [[program, str(tmp_path)]]


def test_missing_folder_is_not_opened(tmp_path):
    with pytest.raises(FileNotFoundError, match="项目文件夹不存在"):
        launcher.open_project_folder(tmp_path / "missing")


def test_project_center_card_has_folder_action_distinct_from_project_load():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = source.index("    def open_recent_project(self)")
    section = source[start:source.index("\n    @staticmethod", start)]
    assert "add_open_folder_button(actions, root, dialog, exists)" in section
    adapter = (Path(__file__).resolve().parents[1] / "src" /
               "picture_capture" / "project_folder_launcher.py").read_text(encoding="utf-8")
    assert 'text="打开文件夹"' in adapter
    assert "open_project_folder_with_error(root, dialog)" in adapter
    assert 'state="normal" if exists else "disabled"' in adapter
